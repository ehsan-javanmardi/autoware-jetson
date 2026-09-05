#!/usr/bin/env python3
"""Live web dashboard and remote control for the Segway RMP chassis.

Talks to the chassis through the vendor SDK (libctrl_arm64-v8a.so) via ctypes and
serves a dashboard plus a JSON API.

Motion control is OFF unless --allow-control is passed. Without it this process binds
only status getters and physically cannot command motion.

Usage:
    sudo ./server.py --lib /path/to/libctrl_arm64-v8a.so                  # read-only
    sudo ./server.py --lib ... --allow-control                            # drivable

Root is required because the SDK shells out to `sudo chmod`/`stty` on the serial port
during init. See README.md.
"""

import argparse
import ctypes
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))

# --- Safety constants -------------------------------------------------------------
# The chassis itself declares communication failure if it receives no velocity command
# for 150ms while in control mode (manual, Appendix 4, set_cmd_vel). We transmit well
# inside that, and stop transmitting entirely if the browser goes quiet.
CMD_TX_HZ = 20.0            # rate we push set_cmd_vel() to the chassis
CLIENT_TIMEOUT_S = 0.40     # browser must refresh its command within this or we zero it
DEFAULT_MAX_LINEAR = 0.5    # m/s   - conservative cap for phone/tablet driving
DEFAULT_MAX_ANGULAR = 0.8   # rad/s

CHASSIS_MODE = {
    0: ("Lock", "Wheels held, speed commands ignored"),
    1: ("Vehicle control", "Closed loop, accepting control commands"),
    2: ("Pushing", "Free-wheeling / push mode"),
    3: ("Emergency stop", "E-stop engaged, wheels unpowered"),
    4: ("Error", "Unrecoverable fault, see error state"),
}
CTRL_SRC = {0: "Remote control", 1: "Host computer"}
WORK_MODEL = {0: "Wheels unpowered", 1: "Wheels powered"}
LOAD_STATE = {0: "No load", 1: "Full load"}
VERSION_MATCH = {
    0x0000: ("match", "Library and chassis firmware match"),
    0x0001: ("chassis-older", "Chassis firmware is older than the library"),
    0x0002: ("host-older", "Library is older than the chassis firmware"),
    0xFFFF: ("timeout", "No reply from chassis"),
}
NO_REPLY = 0xFFFF
BOARDS = {"host": 1, "central": 2, "motor_front": 3, "motor_rear": 4, "bms": 7}


class Sdk:
    """ctypes binding for the vendor SDK.

    Motion entry points are bound only when allow_control is true, so a read-only
    server has no callable path to set_cmd_vel/set_enable_ctrl at all.
    """

    READ_SIG = [
        ("set_smart_car_serial", None, [ctypes.c_char_p]),
        ("set_comu_interface", None, [ctypes.c_int]),
        ("init_control_ctrl", ctypes.c_int, []),
        ("exit_control_ctrl", None, []),
        ("get_bat_soc", ctypes.c_int16, []),
        ("get_bat_charging", ctypes.c_int16, []),
        ("get_bat_mvol", ctypes.c_int32, []),
        ("get_bat_mcurrent", ctypes.c_int32, []),
        ("get_bat_temp", ctypes.c_int16, []),
        ("get_chassis_mode", ctypes.c_uint16, []),
        ("get_chassis_work_model", ctypes.c_int16, []),
        ("get_chassis_load_state", ctypes.c_uint8, []),
        ("get_ctrl_cmd_src", ctypes.c_int16, []),
        ("get_vehicle_meter", ctypes.c_int32, []),
        ("get_host_version", ctypes.c_uint16, []),
        ("get_chassis_central_version", ctypes.c_uint16, []),
        ("get_chassis_motor_version", ctypes.c_uint16, []),
        ("get_err_state", ctypes.c_uint32, [ctypes.c_int]),
        ("get_line_forward_max_vel_fb", ctypes.c_int16, []),
        ("get_line_backward_max_vel_fb", ctypes.c_int16, []),
        ("get_angular_max_vel_fb", ctypes.c_int16, []),
        ("check_version_matched_with_fw", ctypes.c_uint16, []),
    ]
    WRITE_SIG = [
        ("set_cmd_vel", None, [ctypes.c_double, ctypes.c_double]),
        ("set_enable_ctrl", ctypes.c_uint8, [ctypes.c_uint16]),
    ]

    def __init__(self, lib_path, serial_name, allow_control=False):
        self.lib = ctypes.CDLL(lib_path)
        self.serial_name = serial_name
        self.allow_control = allow_control
        self.ready = False
        self.init_error = None
        sigs = self.READ_SIG + (self.WRITE_SIG if allow_control else [])
        for name, restype, argtypes in sigs:
            fn = getattr(self.lib, name)
            fn.restype = restype
            fn.argtypes = argtypes

    def connect(self):
        self.lib.set_smart_car_serial(self.serial_name.encode())
        self.lib.set_comu_interface(0)  # comu_serial
        if self.lib.init_control_ctrl() == -1:
            self.init_error = f"init_control_ctrl() failed (could not open /dev/{self.serial_name})"
            return False
        self.ready = True
        return True

    def read(self):
        lib = self.lib
        central = lib.get_chassis_central_version()
        mode_raw = lib.get_chassis_mode()
        mode_name, mode_desc = CHASSIS_MODE.get(mode_raw, ("Unknown", f"Undocumented value {mode_raw}"))
        match_raw = lib.check_version_matched_with_fw()
        match_key, match_desc = VERSION_MATCH.get(match_raw, ("unknown", f"Undocumented 0x{match_raw:04x}"))
        errors = {n: lib.get_err_state(v) for n, v in BOARDS.items()}
        return {
            "timestamp": time.time(),
            "link": {
                "port": f"/dev/{self.serial_name}",
                "baud": 921600,
                "port_open": self.ready,
                "chassis_responding": central != NO_REPLY,
            },
            "mode": {
                "raw": mode_raw,
                "name": mode_name,
                "description": mode_desc,
                "wheels": WORK_MODEL.get(lib.get_chassis_work_model(), "Unknown"),
                "control_source": CTRL_SRC.get(lib.get_ctrl_cmd_src(), "Unknown"),
                "load_state": LOAD_STATE.get(lib.get_chassis_load_state(), "Unknown"),
            },
            "battery": {
                "soc": lib.get_bat_soc(),
                "millivolts": lib.get_bat_mvol(),
                "milliamps": lib.get_bat_mcurrent(),
                "temperature": lib.get_bat_temp(),
                "charging": bool(lib.get_bat_charging()),
            },
            "odometry": {"meters": lib.get_vehicle_meter()},
            "limits": {
                "forward_max": lib.get_line_forward_max_vel_fb(),
                "backward_max": lib.get_line_backward_max_vel_fb(),
                "angular_max": lib.get_angular_max_vel_fb(),
            },
            "versions": {
                "host": f"0x{lib.get_host_version():04x}",
                "central": f"0x{central:04x}",
                "motor": f"0x{lib.get_chassis_motor_version():04x}",
                "match": match_key,
                "match_description": match_desc,
            },
            "errors": {k: f"0x{v:08x}" for k, v in errors.items()},
            "any_error": any(errors.values()),
        }


class Controller:
    """Owns the drive loop and the deadman watchdog.

    The browser sets a target; this thread retransmits it at CMD_TX_HZ. If the browser
    stops refreshing (tab closed, WiFi dropped, phone locked), the target is zeroed
    after CLIENT_TIMEOUT_S and the chassis is disabled. The chassis's own 150ms
    comms-failure watchdog is the backstop underneath that.
    """

    def __init__(self, sdk, max_linear, max_angular):
        self.sdk = sdk
        self.max_linear = max_linear
        self.max_angular = max_angular
        self.lock = threading.Lock()
        self.enabled = False
        self.linear = 0.0
        self.angular = 0.0
        self.last_client_ms = 0.0
        self.timed_out = False
        self.last_error = None

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _clamp(self, v, limit):
        return max(-limit, min(limit, float(v)))

    def set_target(self, linear, angular):
        with self.lock:
            self.linear = self._clamp(linear, self.max_linear)
            self.angular = self._clamp(angular, self.max_angular)
            self.last_client_ms = time.monotonic()
            self.timed_out = False
            return self.linear, self.angular

    def set_enabled(self, on):
        with self.lock:
            self.linear = self.angular = 0.0
            self.last_client_ms = time.monotonic()
            try:
                self.sdk.lib.set_enable_ctrl(1 if on else 0)
                self.enabled = bool(on)
                self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
            return self.enabled

    def estop(self):
        """Zero the target and drop the enable. Not a substitute for the hardware button."""
        with self.lock:
            self.linear = self.angular = 0.0
            try:
                self.sdk.lib.set_cmd_vel(0.0, 0.0)
                self.sdk.lib.set_enable_ctrl(0)
            except Exception as exc:
                self.last_error = str(exc)
            self.enabled = False
            return True

    def _loop(self):
        period = 1.0 / CMD_TX_HZ
        while True:
            with self.lock:
                if self.enabled:
                    age = time.monotonic() - self.last_client_ms
                    if age > CLIENT_TIMEOUT_S:
                        # Client went quiet - stop, then drop out of control mode.
                        if not self.timed_out:
                            self.timed_out = True
                            self.linear = self.angular = 0.0
                            try:
                                self.sdk.lib.set_cmd_vel(0.0, 0.0)
                                self.sdk.lib.set_enable_ctrl(0)
                            except Exception as exc:
                                self.last_error = str(exc)
                            self.enabled = False
                    else:
                        try:
                            self.sdk.lib.set_cmd_vel(self.linear, self.angular)
                        except Exception as exc:
                            self.last_error = str(exc)
            time.sleep(period)

    def snapshot(self):
        with self.lock:
            return {
                "available": True,
                "enabled": self.enabled,
                "linear": round(self.linear, 3),
                "angular": round(self.angular, 3),
                "max_linear": self.max_linear,
                "max_angular": self.max_angular,
                "client_timeout_s": CLIENT_TIMEOUT_S,
                "timed_out": self.timed_out,
                "error": self.last_error,
            }


class State:
    def __init__(self, sdk, controller, interval=0.5):
        self.sdk = sdk
        self.controller = controller
        self.interval = interval
        self.lock = threading.Lock()
        self.snapshot = None
        self.error = None

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                snap = self.sdk.read()
                with self.lock:
                    self.snapshot, self.error = snap, None
            except Exception as exc:
                with self.lock:
                    self.error = str(exc)
            time.sleep(self.interval)

    def get(self):
        with self.lock:
            base = dict(self.snapshot) if self.snapshot else {
                "link": {"port_open": False, "chassis_responding": False},
                "error": self.error or self.sdk.init_error or "waiting for first read",
            }
            if self.error:
                base["error"] = self.error
        base["control"] = (self.controller.snapshot() if self.controller
                           else {"available": False, "reason": "server started read-only"})
        return base


def make_handler(state, controller):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                return json.loads(self.rfile.read(n))
            except Exception:
                return {}

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/status":
                self._json(200, state.get())
            elif path in ("/", "/index.html"):
                try:
                    with open(os.path.join(HERE, "index.html"), "rb") as fh:
                        self._send(200, fh.read(), "text/html; charset=utf-8")
                except FileNotFoundError:
                    self._send(500, b"index.html missing", "text/plain")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            path = self.path.split("?")[0]
            if not path.startswith("/api/"):
                return self._send(404, b"not found", "text/plain")
            if controller is None:
                return self._json(403, {"ok": False,
                                        "error": "control disabled; start the server with --allow-control"})
            body = self._body()
            if path == "/api/cmd_vel":
                lin, ang = controller.set_target(body.get("linear", 0.0), body.get("angular", 0.0))
                self._json(200, {"ok": True, "linear": lin, "angular": ang})
            elif path == "/api/enable":
                self._json(200, {"ok": True, "enabled": controller.set_enabled(bool(body.get("on")))})
            elif path == "/api/estop":
                controller.estop()
                self._json(200, {"ok": True, "enabled": False})
            else:
                self._send(404, b"not found", "text/plain")

        def log_message(self, *a):
            pass

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Segway RMP dashboard and remote control")
    ap.add_argument("--lib", required=True, help="path to libctrl_arm64-v8a.so")
    ap.add_argument("--serial", default="ttyUSB0", help="device name under /dev")
    ap.add_argument("--port", type=int, default=8080, help="HTTP port")
    ap.add_argument("--host", default="0.0.0.0", help="bind address")
    ap.add_argument("--allow-control", action="store_true",
                    help="enable motion control endpoints (off by default)")
    ap.add_argument("--max-linear", type=float, default=DEFAULT_MAX_LINEAR,
                    help=f"linear speed cap in m/s (default {DEFAULT_MAX_LINEAR})")
    ap.add_argument("--max-angular", type=float, default=DEFAULT_MAX_ANGULAR,
                    help=f"angular speed cap in rad/s (default {DEFAULT_MAX_ANGULAR})")
    args = ap.parse_args()

    if not os.path.exists(args.lib):
        sys.exit(f"SDK library not found: {args.lib}")
    if os.geteuid() != 0:
        print("warning: not running as root; the SDK may fail to configure the serial port",
              file=sys.stderr)

    sdk = Sdk(args.lib, args.serial, allow_control=args.allow_control)
    print(f"[dashboard] connecting to /dev/{args.serial} ...")
    if not sdk.connect():
        print(f"[dashboard] {sdk.init_error}", file=sys.stderr)
        print("[dashboard] serving anyway so the UI can show the fault", file=sys.stderr)

    controller = None
    if args.allow_control:
        controller = Controller(sdk, args.max_linear, args.max_angular)
        controller.start()
        print(f"[dashboard] CONTROL ENABLED - caps {args.max_linear} m/s, {args.max_angular} rad/s")
        print(f"[dashboard] deadman: target zeroed and chassis disabled after "
              f"{CLIENT_TIMEOUT_S}s without a client command")
    else:
        print("[dashboard] read-only (pass --allow-control to drive)")

    state = State(sdk, controller)
    state.start()

    server = ThreadingHTTPServer((args.host, args.port), make_handler(state, controller))
    print(f"[dashboard] http://{args.host}:{args.port}/  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[dashboard] stopping")
    finally:
        if controller:
            controller.estop()
        if sdk.ready:
            sdk.lib.exit_control_ctrl()


if __name__ == "__main__":
    main()
