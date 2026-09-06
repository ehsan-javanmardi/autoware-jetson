"""Autoware vehicle interface for the Segway RMP Plus 401.

Autoware speaks a bicycle model: a steering tire angle and a longitudinal velocity. The
RMP is a differential-drive base that takes linear and angular velocity. The conversion

    angular_z = linear_x * tan(steering_tire_angle) / wheelbase

is the bicycle model solved for yaw rate, with ``wheelbase`` a *virtual* dimension -- the
RMP has no steered axle. It sets how sharply a given steering command turns the base, and
must match the ``wheel_base`` in the vehicle description or Autoware's controller and the
chassis will disagree about what a command means.

Safety, in the order it matters:

* Motors are enabled only on an explicit transition to AUTONOMOUS, never at startup.
* A watchdog zeroes the command if Autoware stops publishing. A differential base holds
  its last velocity indefinitely otherwise, so a crashed planner means a robot that keeps
  going.
* Leaving AUTONOMOUS, and shutting down, both zero the command and disable the motors.
"""
from __future__ import annotations

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from autoware_control_msgs.msg import Control
from autoware_vehicle_msgs.msg import (
    ControlModeReport, GearCommand, GearReport, SteeringReport, VelocityReport,
)
from autoware_vehicle_msgs.srv import ControlModeCommand

from .sdk import SegwaySdk, SegwaySdkError


class SegwayVehicleInterface(Node):
    def __init__(self) -> None:
        super().__init__("segway_vehicle_interface")

        self.declare_parameter("serial_port", "ttyUSB0")
        self.declare_parameter("library_path", "")
        self.declare_parameter("allow_control", False)
        self.declare_parameter("wheel_base", 0.55)
        self.declare_parameter("max_linear_mps", 1.0)
        self.declare_parameter("max_angular_radps", 1.0)
        self.declare_parameter("command_timeout_s", 0.5)
        self.declare_parameter("status_rate_hz", 50.0)

        g = self.get_parameter
        self.wheel_base = float(g("wheel_base").value)
        self.max_linear = float(g("max_linear_mps").value)
        self.max_angular = float(g("max_angular_radps").value)
        self.command_timeout_s = float(g("command_timeout_s").value)
        self.allow_control = bool(g("allow_control").value)

        lib = g("library_path").value or None
        self.sdk = SegwaySdk(serial=g("serial_port").value, lib_path=lib,
                             allow_control=self.allow_control)
        try:
            self.sdk.connect()
        except SegwaySdkError as exc:
            self.get_logger().fatal(str(exc))
            raise

        if not self.allow_control:
            self.get_logger().warn(
                "allow_control is false: publishing status only. The SDK write paths are "
                "not even bound, so this node cannot command motion.")

        self._autonomous = False
        self._last_cmd_time: rclpy.time.Time | None = None
        self._last_steer = 0.0
        self._gear = GearReport.DRIVE

        # Autoware publishes control commands best-effort at high rate.
        cmd_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)

        self.create_subscription(Control, "/control/command/control_cmd",
                                 self._on_control_cmd, cmd_qos)
        self.create_subscription(GearCommand, "/control/command/gear_cmd",
                                 self._on_gear_cmd, 1)
        self.create_service(ControlModeCommand, "/control/control_mode_request",
                            self._on_control_mode_request)

        self.pub_velocity = self.create_publisher(VelocityReport, "/vehicle/status/velocity_status", 1)
        self.pub_steering = self.create_publisher(SteeringReport, "/vehicle/status/steering_status", 1)
        self.pub_mode = self.create_publisher(ControlModeReport, "/vehicle/status/control_mode", 1)
        self.pub_gear = self.create_publisher(GearReport, "/vehicle/status/gear_status", 1)

        period = 1.0 / float(g("status_rate_hz").value)
        self.create_timer(period, self._publish_status)
        self.create_timer(0.1, self._watchdog)

        v = self.sdk.versions()
        self.get_logger().info(
            f"connected: central 0x{v['central']:04x} motor 0x{v['motor']:04x} "
            f"host 0x{v['host']:04x}, battery {self.sdk.battery_soc()}%")
        if not self.sdk.responding():
            self.get_logger().error(
                "chassis is not replying (versions read 0xffff). The serial link is open "
                "but nothing is answering; check power and the converter wiring.")

    # ------------------------------------------------------------- callbacks

    def _on_control_cmd(self, msg: Control) -> None:
        self._last_cmd_time = self.get_clock().now()
        self._last_steer = float(msg.lateral.steering_tire_angle)
        if not (self._autonomous and self.allow_control):
            return

        linear = max(-self.max_linear, min(self.max_linear,
                                           float(msg.longitudinal.velocity)))
        # tan() rather than the small-angle approximation: Autoware can command a large
        # steering angle at low speed, where the two differ substantially.
        angular = linear * math.tan(self._last_steer) / self.wheel_base
        angular = max(-self.max_angular, min(self.max_angular, angular))
        self.sdk.set_cmd_vel(linear, angular)

    def _on_gear_cmd(self, msg: GearCommand) -> None:
        self._gear = msg.command

    def _on_control_mode_request(self, req, resp):
        want_auto = req.mode == ControlModeCommand.Request.AUTONOMOUS
        if want_auto and not self.allow_control:
            self.get_logger().error("AUTONOMOUS refused: this node was started read-only")
            resp.success = False
            return resp

        if want_auto and not self._autonomous:
            self.sdk.set_enable_ctrl(True)
            self._autonomous = True
            self.get_logger().warn("AUTONOMOUS: motors enabled, the base can now move")
        elif not want_auto and self._autonomous:
            self._stop()
            self.get_logger().info("MANUAL: motors disabled")
        resp.success = True
        return resp

    # ----------------------------------------------------------------- loops

    def _watchdog(self) -> None:
        """Zero the command if Autoware goes quiet.

        Without this the chassis holds its last velocity, so a crashed or paused planner
        leaves the base driving.
        """
        if not (self._autonomous and self.allow_control):
            return
        if self._last_cmd_time is None:
            return
        age = (self.get_clock().now() - self._last_cmd_time).nanoseconds / 1e9
        if age > self.command_timeout_s:
            self.sdk.set_cmd_vel(0.0, 0.0)
            self.get_logger().warn(
                f"no control_cmd for {age:.2f}s, commanding zero velocity",
                throttle_duration_sec=2.0)

    def _publish_status(self) -> None:
        now = self.get_clock().now().to_msg()
        speed = self.sdk.speed_mps()
        left, right = self.sdk.side_speeds_mps()

        v = VelocityReport()
        v.header.stamp = now
        v.header.frame_id = "base_link"
        v.longitudinal_velocity = speed
        v.lateral_velocity = 0.0
        # Yaw rate from the wheel-speed difference. The chassis reports no yaw rate of
        # its own, and the track width is folded into wheel_base here as an approximation;
        # the IMU is the better source once the EKF is running.
        v.heading_rate = (right - left) / self.wheel_base
        self.pub_velocity.publish(v)

        s = SteeringReport()
        s.stamp = now
        # The RMP has no steered axle and reports no steering angle. Echoing the command
        # keeps Autoware's controller from integrating an error against a constant zero.
        s.steering_tire_angle = self._last_steer
        self.pub_steering.publish(s)

        m = ControlModeReport()
        m.stamp = now
        m.mode = ControlModeReport.AUTONOMOUS if self._autonomous else ControlModeReport.MANUAL
        self.pub_mode.publish(m)

        gr = GearReport()
        gr.stamp = now
        gr.report = self._gear
        self.pub_gear.publish(gr)

    # ---------------------------------------------------------------- teardown

    def _stop(self) -> None:
        self._autonomous = False
        if self.allow_control:
            try:
                self.sdk.set_cmd_vel(0.0, 0.0)
                self.sdk.set_enable_ctrl(False)
            except SegwaySdkError:
                pass

    def destroy_node(self) -> bool:
        self._stop()
        self.sdk.close()
        return super().destroy_node()


def main(argv=None) -> None:
    rclpy.init(args=argv)
    node = SegwayVehicleInterface()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
