"""ROS side of the control backend: every write path the web UI can reach.

Deliberately a separate process from the dashboard. autoware_health_ui creates no
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

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
LAUNCH_SCRIPT = os.path.join(REPO, "autoware_kashiwa.sh")

# Teleop is deliberately slower than the vehicle interface's own cap. Driving by
# thumb on a tablet is not the case to reach the chassis's 3.56 m/s in.
DEFAULT_MAX_SPEED = 0.5
HARD_MAX_SPEED = 1.5
TURN_RATE = 0.6          # rad/s commanded for a left/right hold


class ControlBackend(Node):
    def __init__(self) -> None:
        super().__init__("autoware_web_control")

        self.lock = threading.Lock()
        self.autoware_proc: subprocess.Popen | None = None
        self.remote_enabled = False
        self.max_speed = DEFAULT_MAX_SPEED
        self.control_mode = None
        self._last_drive = 0.0
        self._drive = (0.0, 0.0)

        cmd_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.pub_control = self.create_publisher(Control, "/control/command/control_cmd", cmd_qos)
        self.cli_mode = self.create_client(ControlModeCommand, "/control/control_mode_request")
        self.create_subscription(ControlModeReport, "/vehicle/status/control_mode",
                                 lambda m: setattr(self, "control_mode", m.mode), 1)

        # 20 Hz: fast enough that the interface's 0.5 s watchdog never trips while a
        # direction is genuinely held, slow enough to be nothing on the network.
        self.create_timer(0.05, self._tick)

    # ------------------------------------------------------------ Autoware

    def autoware_running(self) -> bool:
        with self.lock:
            return self.autoware_proc is not None and self.autoware_proc.poll() is None

    def start_autoware(self) -> tuple[bool, str]:
        if self.autoware_running():
            return False, "already running"
        if not os.path.exists(LAUNCH_SCRIPT):
            return False, f"launch script missing: {LAUNCH_SCRIPT}"
        with self.lock:
            # start_new_session so the whole launch tree can be signalled as a group.
            # ros2 launch spawns many children; killing only the shell orphans them.
            self.autoware_proc = subprocess.Popen(
                ["bash", LAUNCH_SCRIPT], cwd=REPO,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
        self.get_logger().warn("Autoware launch started from the web UI")
        return True, "started"

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

    def drive(self, direction: str, speed: float) -> tuple[bool, str]:
        if not self.remote_enabled:
            return False, "remote drive is not armed"
        v = max(0.0, min(HARD_MAX_SPEED, float(speed)))
        if direction == "fwd":
            self._drive = (v, 0.0)
        elif direction == "back":
            self._drive = (-v, 0.0)
        elif direction == "left":
            self._drive = (0.0, TURN_RATE)
        elif direction == "right":
            self._drive = (0.0, -TURN_RATE)
        else:
            self._drive = (0.0, 0.0)
        self._last_drive = time.time()
        return True, "ok"

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
        else:
            # Turning on the spot cannot be expressed as a steering angle at zero
            # speed. Creep forward so the yaw rate is representable at all.
            creep = 0.05
            m.longitudinal.velocity = creep if angular != 0.0 else 0.0
            m.lateral.steering_tire_angle = (
                float(math.atan(angular * wheel_base / creep)) if angular else 0.0)
        self.pub_control.publish(m)

    def state(self) -> dict:
        return {
            "autoware_running": self.autoware_running(),
            "remote": {"enabled": self.remote_enabled, "max_speed": self.max_speed},
            "control_mode": self.control_mode,
            "goals": {"points": [], "mode": "step", "repeat": False},
        }
