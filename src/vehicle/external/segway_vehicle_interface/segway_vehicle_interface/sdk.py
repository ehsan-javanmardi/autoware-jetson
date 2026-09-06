"""ctypes binding for the Segway RMP vendor library.

Kept separate from the ROS node so it can be exercised without a ROS graph, and so the
one place that talks to the closed-source library is small enough to audit.

The library is ``libctrl_arm64-v8a.so``, shipped with the ``segway_rmp`` branch of
adeeb10abbas/segway_ros2. It is aarch64 and unstripped, but the wire protocol lives
inside it and cannot be inspected, so every constant below comes from the vendor headers
rather than from observation.
"""
from __future__ import annotations

import ctypes
import os

# From comm_ctrl_navigation.h. The chassis reports speeds as scaled integers.
LINE_SPEED_TRANS_GAIN_MPS = 3600.0      # 3600 raw == 1 m/s
ANGULAR_SPEED_TRANS_GAIN_RADPS = 1000.0  # 1000 raw == 1 rad/s

COMU_SERIAL = 0
COMU_CAN = 1

NO_REPLY = 0xFFFF  # what every getter returns when the chassis has not answered

DEFAULT_LIB = "/home/tlab/workspace/segway_ros2/segwayrmp/lib/libctrl_arm64-v8a.so"

# (name, restype, argtypes). Only what this interface uses; the library exports far more.
_SIGNATURES = [
    ("set_smart_car_serial", None, [ctypes.c_char_p]),
    ("set_comu_interface", None, [ctypes.c_int]),
    ("init_control_ctrl", ctypes.c_int, []),
    ("exit_control_ctrl", None, []),
    # --- status, read-only -------------------------------------------------
    ("get_chassis_central_version", ctypes.c_int, []),
    ("get_chassis_motor_version", ctypes.c_int, []),
    ("get_host_version", ctypes.c_int, []),
    ("get_bat_soc", ctypes.c_int, []),
    ("get_bat_mvol", ctypes.c_int, []),
    ("get_chassis_mode", ctypes.c_int, []),
    ("get_ctrl_cmd_src", ctypes.c_int, []),
    ("get_vehicle_meter", ctypes.c_int, []),
    ("get_err_state", ctypes.c_int, []),
    ("get_fbk_speed_forward", ctypes.c_int16, []),
    # Four wheels, not two. The vendor header also declares get_encode_speed_L/R, which
    # the library does not export -- treat comm_ctrl_navigation.h as documentation of
    # intent, not of the ABI, and check with nm before binding anything new.
    ("get_encode_speed_FL", ctypes.c_int16, []),
    ("get_encode_speed_FR", ctypes.c_int16, []),
    ("get_encode_speed_RL", ctypes.c_int16, []),
    ("get_encode_speed_RR", ctypes.c_int16, []),
    ("get_rotate_switch_stat", ctypes.c_uint8, []),
    ("get_rotate_scheme_cfg", ctypes.c_uint8, []),
    # --- motion, write ------------------------------------------------------
    ("set_cmd_vel", None, [ctypes.c_double, ctypes.c_double]),
    ("set_enable_ctrl", ctypes.c_uint8, [ctypes.c_uint16]),
    # In-situ rotation. A different control pattern from set_cmd_vel: the enable
    # is called ONCE to start a spin, not streamed, and cancelled explicitly.
    ("enable_rotate_switch", ctypes.c_int16, [ctypes.c_uint8]),
    ("cfg_rotate_scheme_switch", None, [ctypes.c_uint8]),
    ("set_vel_of_rotation", None, [ctypes.c_double]),
    ("enable_chassis_in_situ_rotation", ctypes.c_int32, [ctypes.c_uint8]),
    # The SDK exports this misspelled. Using the correct spelling fails to bind.
    ("disable_chassis_in_situ_ratotion", None, []),
]

# Names that can cause motion. Nothing outside SegwaySdk.set_cmd_vel and
# SegwaySdk.set_enable_ctrl may call these, and both refuse unless allow_control
# was passed at construction.
_WRITE_PATHS = frozenset({
    "set_cmd_vel", "set_enable_ctrl",
    "enable_rotate_switch", "cfg_rotate_scheme_switch", "set_vel_of_rotation",
    "enable_chassis_in_situ_rotation", "disable_chassis_in_situ_ratotion",
})


class SegwaySdkError(RuntimeError):
    pass


class SegwaySdk:
    """Thin wrapper. Read paths are always available; write paths are opt-in.

    ``allow_control=False`` does not merely decline to call the write functions -- it
    never binds them, so there is no callable path to motion in the object at all.
    """

    def __init__(self, serial: str = "ttyUSB0", lib_path: str | None = None,
                 allow_control: bool = False) -> None:
        self.lib_path = lib_path or os.environ.get("SEGWAY_SDK_LIB", DEFAULT_LIB)
        self.serial = serial
        self.allow_control = allow_control
        self._connected = False

        try:
            self._lib = ctypes.CDLL(self.lib_path)
        except OSError as exc:
            raise SegwaySdkError(f"cannot load {self.lib_path}: {exc}") from exc

        for name, restype, argtypes in _SIGNATURES:
            if name in _WRITE_PATHS and not allow_control:
                continue
            try:
                fn = getattr(self._lib, name)
            except AttributeError as exc:
                raise SegwaySdkError(
                    f"{self.lib_path} does not export {name!r}. The vendor headers "
                    f"declare functions the library omits; verify with "
                    f"`nm -D --defined-only <lib>` before binding.") from exc
            fn.restype = restype
            fn.argtypes = argtypes

    # ------------------------------------------------------------------ link

    def connect(self, timeout_s: float = 3.0) -> None:
        self._lib.set_smart_car_serial(self.serial.encode())
        self._lib.set_comu_interface(COMU_SERIAL)
        if self._lib.init_control_ctrl() == -1:
            raise SegwaySdkError(f"init_control_ctrl failed (cannot open /dev/{self.serial})")
        self._connected = True

    def close(self) -> None:
        if self._connected:
            self._lib.exit_control_ctrl()
            self._connected = False

    def responding(self) -> bool:
        """True once the chassis answers. Versions read 0xffff until it does."""
        return self._lib.get_chassis_central_version() not in (NO_REPLY, -1)

    # ---------------------------------------------------------------- status

    def speed_mps(self) -> float:
        return self._lib.get_fbk_speed_forward() / LINE_SPEED_TRANS_GAIN_MPS

    def wheel_speeds_mps(self) -> tuple[float, float, float, float]:
        """Front-left, front-right, rear-left, rear-right, in m/s."""
        g = LINE_SPEED_TRANS_GAIN_MPS
        return (self._lib.get_encode_speed_FL() / g,
                self._lib.get_encode_speed_FR() / g,
                self._lib.get_encode_speed_RL() / g,
                self._lib.get_encode_speed_RR() / g)

    def side_speeds_mps(self) -> tuple[float, float]:
        """Left and right side speeds, averaged over each side's two wheels."""
        fl, fr, rl, rr = self.wheel_speeds_mps()
        return ((fl + rl) / 2.0, (fr + rr) / 2.0)

    def battery_soc(self) -> int:
        return self._lib.get_bat_soc()

    def battery_mvol(self) -> int:
        return self._lib.get_bat_mvol()

    def chassis_mode(self) -> int:
        return self._lib.get_chassis_mode()

    def ctrl_cmd_src(self) -> int:
        return self._lib.get_ctrl_cmd_src()

    def odometer(self) -> int:
        return self._lib.get_vehicle_meter()

    def versions(self) -> dict[str, int]:
        return {
            "central": self._lib.get_chassis_central_version(),
            "motor": self._lib.get_chassis_motor_version(),
            "host": self._lib.get_host_version(),
        }

    # ----------------------------------------------------------------- write

    def set_cmd_vel(self, linear_x: float, angular_z: float) -> None:
        if not self.allow_control:
            raise SegwaySdkError("set_cmd_vel called on a read-only SegwaySdk")
        self._lib.set_cmd_vel(float(linear_x), float(angular_z))

    def set_enable_ctrl(self, enable: bool) -> int:
        if not self.allow_control:
            raise SegwaySdkError("set_enable_ctrl called on a read-only SegwaySdk")
        return self._lib.set_enable_ctrl(1 if enable else 0)

    # ------------------------------------------------------ in-situ rotation
    #
    # The RMP steers its front wheels: a normal turn is set_cmd_vel with a yaw rate,
    # and the chassis cannot turn tighter than its 1.36 m minimum radius. Spinning on
    # the spot is a separate chassis mode with a separate API.
    #
    # The manual is blunt about the cost: "the current of the rear wheel will be too
    # large, which may cause abnormality of the chassis and the motor", with a
    # locked-rotor alarm after about 5 seconds. Treat it as a manoeuvre, not a mode
    # to sit in.

    def rotation_available(self) -> tuple[bool, bool]:
        """(switch enabled, new scheme configured) as the chassis reports them."""
        return bool(self._lib.get_rotate_switch_stat()), bool(self._lib.get_rotate_scheme_cfg())

    def prepare_in_situ(self) -> None:
        """Arm the chassis for in-situ rotation. Idempotent; call before spinning."""
        if not self.allow_control:
            raise SegwaySdkError("prepare_in_situ called on a read-only SegwaySdk")
        self._lib.cfg_rotate_scheme_switch(1)
        self._lib.enable_rotate_switch(1)

    def start_in_situ(self, left: bool, rate_radps: float) -> int:
        """Begin spinning. Called ONCE per spin, not streamed like set_cmd_vel."""
        if not self.allow_control:
            raise SegwaySdkError("start_in_situ called on a read-only SegwaySdk")
        self._lib.set_vel_of_rotation(abs(float(rate_radps)))
        return self._lib.enable_chassis_in_situ_rotation(0 if left else 1)

    def stop_in_situ(self) -> None:
        if not self.allow_control:
            raise SegwaySdkError("stop_in_situ called on a read-only SegwaySdk")
        self._lib.disable_chassis_in_situ_ratotion()
