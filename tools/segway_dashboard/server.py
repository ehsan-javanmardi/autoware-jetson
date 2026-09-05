#!/usr/bin/env python3
"""Live web dashboard for the Segway RMP chassis.

Talks to the chassis through the vendor SDK (libctrl_arm64-v8a.so) via ctypes and
serves a small dashboard plus a JSON status endpoint.

Read-only: this process never calls set_cmd_vel() or set_enable_ctrl(), so it cannot
command motion.

Usage:
    sudo ./server.py --lib /path/to/libctrl_arm64-v8a.so [--port 8080] [--serial ttyUSB0]

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

# get_chassis_mode() -> finite state machine, per manual Appendix 4
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

# check_version_matched_with_fw()
VERSION_MATCH = {
    0x0000: ("match", "Library and chassis firmware match"),
    0x0001: ("chassis-older", "Chassis firmware is older than the library"),
    0x0002: ("host-older", "Library is older than the chassis firmware"),
    0xFFFF: ("timeout", "No reply from chassis"),
}

NO_REPLY = 0xFFFF

# get_err_state(board_name) - board enum from comm_ctrl_navigation.h
BOARDS = {"host": 1, "central": 2, "motor_front": 3, "motor_rear": 4, "bms": 7}


class Sdk:
    """ctypes binding for the parts of the vendor SDK we read."""

    def __init__(self, lib_path, serial_name):
        self.lib_path = lib_path
        self.serial_name = serial_name
        self.lib = ctypes.CDLL(lib_path)
        self._bind()
        self.ready = False
        self.init_error = None

    def _bind(self):
        lib = self.lib
        sig = [
            # (name, restype, argtypes)
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
        for name, restype, argtypes in sig:
            fn = getattr(lib, name)
            fn.restype = restype
            fn.argtypes = argtypes

    def connect(self):
        self.lib.set_smart_car_serial(self.serial_name.encode())
        self.lib.set_comu_interface(0)  # comu_serial
        rc = self.lib.init_control_ctrl()
        if rc == -1:
            self.init_error = f"init_control_ctrl() failed (could not open /dev/{self.serial_name})"
            return False
        self.ready = True
        return True

    def read(self):
        """Snapshot every polled value. Returns a plain dict."""
        lib = self.lib
        central = lib.get_chassis_central_version()
        responding = central != NO_REPLY

        mode_raw = lib.get_chassis_mode()
        mode_name, mode_desc = CHASSIS_MODE.get(mode_raw, ("Unknown", f"Undocumented value {mode_raw}"))

        match_raw = lib.check_version_matched_with_fw()
        match_key, match_desc = VERSION_MATCH.get(match_raw, ("unknown", f"Undocumented code 0x{match_raw:04x}"))

        errors = {name: lib.get_err_state(num) for name, num in BOARDS.items()}

        return {
            "timestamp": time.time(),
            "link": {
                "port": f"/dev/{self.serial_name}",
                "baud": 921600,
                "port_open": self.ready,
                "chassis_responding": responding,
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
            "odometry": {
                "meters": lib.get_vehicle_meter(),
            },
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


class State:
    """Holds the most recent snapshot, refreshed by a background thread."""

    def __init__(self, sdk, interval=0.5):
        self.sdk = sdk
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
                    self.snapshot = snap
                    self.error = None
            except Exception as exc:  # keep serving even if a read blows up
                with self.lock:
                    self.error = str(exc)
            time.sleep(self.interval)

    def get(self):
        with self.lock:
            if self.snapshot is None:
                return {
                    "link": {"port_open": False, "chassis_responding": False},
                    "error": self.error or self.sdk.init_error or "waiting for first read",
                }
            snap = dict(self.snapshot)
            if self.error:
                snap["error"] = self.error
            return snap


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, content_type):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/status":
                self._send(200, json.dumps(state.get()).encode(), "application/json")
            elif path in ("/", "/index.html"):
                try:
                    with open(os.path.join(HERE, "index.html"), "rb") as fh:
                        self._send(200, fh.read(), "text/html; charset=utf-8")
                except FileNotFoundError:
                    self._send(500, b"index.html missing", "text/plain")
            else:
                self._send(404, b"not found", "text/plain")

        def log_message(self, *args):
            pass  # keep the console clean for SDK output

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Segway RMP live dashboard")
    ap.add_argument("--lib", required=True, help="path to libctrl_arm64-v8a.so")
    ap.add_argument("--serial", default="ttyUSB0", help="serial device name under /dev (default: ttyUSB0)")
    ap.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    ap.add_argument("--host", default="0.0.0.0", help="bind address (default: all interfaces)")
    args = ap.parse_args()

    if not os.path.exists(args.lib):
        sys.exit(f"SDK library not found: {args.lib}")

    if os.geteuid() != 0:
        print("warning: not running as root; the SDK may fail to configure the serial port",
              file=sys.stderr)

    sdk = Sdk(args.lib, args.serial)
    print(f"[dashboard] connecting to /dev/{args.serial} ...")
    if not sdk.connect():
        print(f"[dashboard] {sdk.init_error}", file=sys.stderr)
        print("[dashboard] serving anyway so the UI can show the fault", file=sys.stderr)

    state = State(sdk)
    state.start()

    server = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print(f"[dashboard] http://{args.host}:{args.port}/  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[dashboard] stopping")
    finally:
        if sdk.ready:
            sdk.lib.exit_control_ctrl()


if __name__ == "__main__":
    main()
