"""ROS side of the control backend: every write path the web UI can reach.

Deliberately a separate process from the dashboard. segway_web_ui creates no
publishers and no service clients at all, so it cannot command the vehicle even if
something in it misbehaves; everything that can move the robot lives here instead.

Three groups of writes:

* Autoware lifecycle -- start and stop the launch script, as a process group.
* Operation -- engage, and the AUTONOMOUS/MANUAL control mode.
* Teleop -- hold-to-drive velocity, arm/disarm, e-stop.

Teleop is the one that needs care. It publishes the same Control message Autoware's
controller does, so the vehicle interface treats both identically and its 0.5 s watchdog
covers a dropped phone exactly as it covers a crashed planner. Nothing latches here: the
browser must keep sending, or the robot stops on its own.
"""
from __future__ import annotations

import math
import os
import signal
import subprocess
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from autoware_control_msgs.msg import Control
from autoware_vehicle_msgs.msg import ControlModeReport
from autoware_vehicle_msgs.srv import ControlModeCommand
from std_srvs.srv import SetBool

from .managed import Managed

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
LAUNCH_SCRIPT = os.path.join(REPO, "autoware_kashiwa.sh")

# Teleop is deliberately slower than the vehicle interface's own cap. Driving by
# thumb on a tablet is not the case to reach the chassis's 3.56 m/s in.
DEFAULT_MAX_SPEED = 0.5
HARD_MAX_SPEED = 1.5
TURN_RATE = 0.6          # rad/s commanded for a left/right hold in in-situ mode

# Ackermann is the default and is what the chassis does natively: the RMP steers its
# front wheels and cannot turn tighter than a 1.36 m radius. A left/right hold
# therefore has to DRIVE while steering - there is no such thing as turning in place
# in this mode, and commanding one produces a crawl in a straight line, which is
# exactly what the first version of this did.
TURN_SPEED = 0.35        # m/s while steering in Ackermann mode
MAX_STEER = 0.70         # rad, matches max_steer_angle in segway_description


class ControlBackend(Node):
    def __init__(self) -> None:
        super().__init__("segway_web_control")

        self.lock = threading.Lock()
        self.autoware_proc: subprocess.Popen | None = None
        self.autoware_log = os.path.expanduser("~/.segway/logs/autoware.log")
        self.remote_enabled = False
        self.in_situ = False
        self.max_speed = DEFAULT_MAX_SPEED
        self.control_mode = None
        self._last_drive = 0.0
        self._drive = (0.0, 0.0)

        # Supervised launches. The patterns match the real processes, so Stop works on
        # what segway.sh started as well as on what this backend started.
        #
        # Named `managed`, not `services`: rclpy.Node.services is a read-only property
        # listing the node's own ROS services, and assigning to it raises AttributeError
        # at construction.
        self.managed = {
            "sensing": Managed(
                self.get_logger(), "sensor drivers",
                ["ros2", "launch", "segway_sensor_kit_launch",
                 "platform_sensors.launch.xml"],
                REPO, "platform_sensors.launch.xml", "sensors.log"),
            "vehicle": Managed(
                self.get_logger(), "vehicle interface",
                ["ros2", "launch", "segway_vehicle_interface",
                 "segway_vehicle_interface.launch.xml", "allow_control:=true"],
                REPO, "segway_vehicle_interface", "vehicle.log"),
        }

        cmd_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.pub_control = self.create_publisher(Control, "/control/command/control_cmd", cmd_qos)
        self.cli_mode = self.create_client(ControlModeCommand, "/control/control_mode_request")
        self.cli_in_situ = self.create_client(
            SetBool, "/segway_vehicle_interface/set_in_situ_mode")
        self.create_subscription(ControlModeReport, "/vehicle/status/control_mode",
                                 lambda m: setattr(self, "control_mode", m.mode), 1)

        # 20 Hz: fast enough that the interface's 0.5 s watchdog never trips while a
        # direction is genuinely held, slow enough to be nothing on the network.
        self.create_timer(0.05, self._tick)

    # ------------------------------------------------------------ Autoware

    def autoware_running(self) -> bool:
        with self.lock:
            return self.autoware_proc is not None and self.autoware_proc.poll() is None

    # Node-name prefixes that belong to Autoware rather than to the platform. Used to
    # answer "is Autoware REALLY gone", which the launch process exiting does not settle:
    # ros2 launch can exit while orphaned nodes keep running.
    _PLATFORM_NODES = ("segway_web_ui", "segway_web_control", "segway_vehicle_interface",
                       "livox", "ublox", "ntrip", "foxglove_bridge", "launch_ros",
                       # The ros2 CLI daemon comes and goes with any ros2 command and is
                       # nobody's node. Counting it meant "fully stopped" was never true.
                       "ros2cli", "rosout")

    # Namespaces that belong to Autoware. Used to decide what may be force-killed, and
    # it is an ALLOW list on purpose: Autoware and the platform both run
    # rclcpp_components/component_container processes, so the binary cannot tell them
    # apart. An earlier version matched on the binary and killed the Livox and GNSS
    # containers along with Autoware's.
    _AUTOWARE_NS = ("/perception", "/planning", "/control", "/localization", "/map",
                    "/system", "/simulation", "/awapi", "/api", "/diagnostics")

    def autoware_nodes(self) -> list[str]:
        out = []
        for name, ns in self.get_node_names_and_namespaces():
            full = (ns.rstrip("/") + "/" + name) if ns != "/" else "/" + name
            if any(k in full for k in self._PLATFORM_NODES):
                continue
            if ns.startswith("/sensing") or ns.startswith("/gnss"):
                # Sensing chain nodes belong to Autoware, but the platform's own drivers
                # live there too; the prefix filter above has already removed those.
                out.append(full)
            elif ns != "/" or name not in ("rosout",):
                out.append(full)
        return sorted(out)

    def stop_autoware_fully(self) -> tuple[bool, str]:
        """Stop the launch, then kill anything of Autoware's that outlived it.

        ros2 launch exiting is not the same as Autoware being gone: a node that ignores
        SIGINT is simply orphaned, and the UI would then claim Autoware had stopped while
        its nodes were still publishing.
        """
        self.stop_autoware()
        time.sleep(2.0)
        left = self.autoware_nodes()
        if not left:
            return True, "fully stopped"
        killed = self._kill_autoware_processes()
        time.sleep(2.0)
        left = self.autoware_nodes()
        if left:
            return False, f"{len(left)} node(s) still running: {', '.join(left[:4])}"
        self.get_logger().warn(f"Autoware fully stopped ({killed} process(es) killed)")
        return True, f"fully stopped ({killed} killed)"

    def _kill_autoware_processes(self) -> int:
        """SIGKILL Autoware's surviving processes, and only Autoware's.

        Decided per process by the __ns: it is passed to, not by the executable. Autoware
        and the platform both run rclcpp_components/component_container, so a
        binary-based match cannot distinguish them and would take the Livox and GNSS
        containers down with Autoware.
        """
        killed = 0
        try:
            out = subprocess.run(["ps", "-eo", "pid,args", "--no-headers"],
                                 capture_output=True, text=True)
        except OSError:
            return 0
        me = os.getpid()
        for line in out.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            head, _, args = line.partition(" ")
            try:
                pid = int(head)
            except ValueError:
                continue
            if pid == me:
                continue
            ns = None
            for tok in args.split():
                if tok.startswith("__ns:="):
                    ns = tok[len("__ns:="):]
                    break
            if ns is None or not any(ns.startswith(a) for a in self._AUTOWARE_NS):
                continue
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
                killed += 1
            except (ProcessLookupError, PermissionError):
                pass
        return killed

    def _hardware_already_up(self) -> bool:
        """Is something else already driving the sensors and the chassis?

        segway.sh owns them for the life of the platform. If it does, Autoware must
        not bring up its own: a second vehicle interface cannot share the chassis
        serial port, and a second Livox driver fights for the same UDP ports.
        """
        names = {n for n, _ in self.get_node_names_and_namespaces()}
        return "segway_vehicle_interface" in names

    def start_autoware(self) -> tuple[bool, str]:
        if self.autoware_running():
            return False, "already running"
        if not os.path.exists(LAUNCH_SCRIPT):
            return False, f"launch script missing: {LAUNCH_SCRIPT}"

        cmd = ["bash", LAUNCH_SCRIPT]
        layered = self._hardware_already_up()
        if layered:
            # Autonomy only. The platform keeps the sensors and the chassis, so
            # starting and stopping Autoware from the UI leaves them untouched -
            # which is the whole reason the two are separate processes.
            cmd += ["launch_sensing_driver:=false", "launch_vehicle_interface:=false"]

        # Not DEVNULL. Autoware started from a button has no terminal, so discarding
        # its output means a failed launch reports nothing at all - which is how a
        # robot_state_publisher crash went unnoticed here until the ROS launch log was
        # read by hand.
        log_dir = os.path.expanduser("~/.segway/logs")
        os.makedirs(log_dir, exist_ok=True)
        self.autoware_log = os.path.join(log_dir, "autoware.log")
        with self.lock:
            # start_new_session so the whole launch tree can be signalled as a group.
            # ros2 launch spawns many children; killing only the shell orphans them.
            fh = open(self.autoware_log, "wb")
            self.autoware_proc = subprocess.Popen(
                cmd, cwd=REPO, stdout=fh, stderr=subprocess.STDOUT,
                start_new_session=True)
        self.get_logger().warn(
            "Autoware started from the web UI" +
            (" (autonomy only; the platform keeps the sensors and the chassis)"
             if layered else " (with its own sensor drivers and vehicle interface)"))
        return True, "started (layered)" if layered else "started (standalone)"

    def stop_autoware(self) -> tuple[bool, str]:
        if not self.autoware_running():
            return False, "not running"
        with self.lock:
            pgid = os.getpgid(self.autoware_proc.pid)
            os.killpg(pgid, signal.SIGINT)      # SIGINT so ros2 launch shuts nodes down
        for _ in range(100):
            if not self.autoware_running():
                return True, "stopped"
            time.sleep(0.1)
        with self.lock:
            os.killpg(pgid, signal.SIGTERM)
        return True, "stopped (forced)"

    # ----------------------------------------------------------- operation

    def request_mode(self, autonomous: bool) -> tuple[bool, str]:
        if not self.cli_mode.wait_for_service(timeout_sec=2.0):
            return False, "vehicle interface is not running"
        req = ControlModeCommand.Request()
        req.mode = (ControlModeCommand.Request.AUTONOMOUS if autonomous
                    else ControlModeCommand.Request.MANUAL)
        fut = self.cli_mode.call_async(req)
        for _ in range(50):
            if fut.done():
                break
            time.sleep(0.05)
        if not fut.done() or fut.result() is None:
            return False, "no response from the vehicle interface"
        return bool(fut.result().success), "ok" if fut.result().success else "refused"

    # -------------------------------------------------------------- teleop

    def set_remote(self, enabled: bool) -> tuple[bool, str]:
        if enabled:
            ok, msg = self.request_mode(True)
            if not ok:
                return False, f"could not enter AUTONOMOUS: {msg}"
        self.remote_enabled = enabled
        self._drive = (0.0, 0.0)
        if not enabled:
            self._publish(0.0, 0.0)
            self.request_mode(False)
        self.get_logger().warn(f"remote drive {'ARMED' if enabled else 'disarmed'}")
        return True, "ok"

    def drive(self, direction: str, speed: float, turn: float = 0.0) -> tuple[bool, str]:
        """Set the held command. `turn` is -1..1 from the joystick's x axis."""
        if not self.remote_enabled:
            return False, "remote drive is not armed"
        v = max(0.0, min(HARD_MAX_SPEED, float(speed)))
        turn = max(-1.0, min(1.0, float(turn)))

        if direction == "stop":
            self._drive = (0.0, 0.0)
        elif self.in_situ and direction in ("left", "right"):
            # Spin on the spot: zero linear, yaw only. The vehicle interface routes
            # this to the chassis's in-situ API rather than to set_cmd_vel.
            self._drive = (0.0, TURN_RATE if direction == "left" else -TURN_RATE)
        elif direction == "left":
            self._drive = (TURN_SPEED, TURN_SPEED * math.tan(MAX_STEER) / 0.456)
        elif direction == "right":
            self._drive = (TURN_SPEED, -TURN_SPEED * math.tan(MAX_STEER) / 0.456)
        elif direction == "fwd":
            self._drive = (v, v * math.tan(turn * MAX_STEER) / 0.456)
        elif direction == "back":
            self._drive = (-v, -v * math.tan(turn * MAX_STEER) / 0.456)
        else:
            self._drive = (0.0, 0.0)
        self._last_drive = time.time()
        return True, "ok"

    def set_steering_mode(self, in_situ: bool) -> tuple[bool, str]:
        if not self.cli_in_situ.wait_for_service(timeout_sec=2.0):
            return False, "vehicle interface is not running"
        self._drive = (0.0, 0.0)
        req = SetBool.Request(); req.data = bool(in_situ)
        fut = self.cli_in_situ.call_async(req)
        for _ in range(50):
            if fut.done():
                break
            time.sleep(0.05)
        if not fut.done() or fut.result() is None:
            return False, "no response"
        if fut.result().success:
            self.in_situ = bool(in_situ)
        return bool(fut.result().success), fut.result().message

    def estop(self) -> tuple[bool, str]:
        """Stop now. Zero the command, drop the arm, and hand back to MANUAL."""
        self._drive = (0.0, 0.0)
        self.remote_enabled = False
        for _ in range(5):
            self._publish(0.0, 0.0)
            time.sleep(0.02)
        self.request_mode(False)
        self.get_logger().error("E-STOP from the web UI")
        return True, "stopped"

    def _tick(self) -> None:
        if not self.remote_enabled:
            return
        # The browser must keep asking. Half a second of silence and this stops
        # publishing, which lets the vehicle interface's own watchdog take over.
        if time.time() - self._last_drive > 0.5:
            self._drive = (0.0, 0.0)
        self._publish(*self._drive)

    def _publish(self, linear: float, angular: float) -> None:
        m = Control()
        m.stamp = self.get_clock().now().to_msg()
        m.longitudinal.velocity = float(linear)
        m.longitudinal.acceleration = 0.0
        # The interface converts steering to yaw with tan(steer)/wheel_base, so a
        # requested yaw rate has to be inverted back through the same geometry.
        wheel_base = 0.456
        if abs(linear) > 1e-3:
            m.lateral.steering_tire_angle = float(math.atan(angular * wheel_base / linear))
        elif angular != 0.0:
            # Zero speed with a yaw rate means spin on the spot. There is no steering
            # angle that expresses this, so the angle only carries the DIRECTION and
            # the vehicle interface routes it to the chassis's in-situ API. An earlier
            # version crept forward at 0.05 m/s instead, which on a chassis with a
            # 1.36 m minimum turning radius is a yaw rate of 0.04 rad/s - visually a
            # straight line, which is what it looked like.
            m.lateral.steering_tire_angle = 0.5 if angular > 0 else -0.5
        else:
            m.lateral.steering_tire_angle = 0.0
        self.pub_control.publish(m)

    def state(self) -> dict:
        return {
            "autoware_running": self.autoware_running(),
            "hardware_owned_by_platform": self._hardware_already_up(),
            "autoware_log": self.autoware_log,
            "autoware_node_count": len(self.autoware_nodes()),
            "services": {k: v.state() for k, v in self.managed.items()},
            "remote": {"enabled": self.remote_enabled, "max_speed": self.max_speed,
                       "in_situ": self.in_situ},
            "control_mode": self.control_mode,
            "goals": {"points": [], "mode": "step", "repeat": False},
        }
