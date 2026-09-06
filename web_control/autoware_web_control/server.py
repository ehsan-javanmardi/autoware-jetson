"""HTTP front for the control backend.

Stdlib only, matching the dashboard and v2x_web_monitor. Every route here is a write,
which is the whole reason this is a separate process on a separate port.

CORS is open because the page is served from :8842 and posts here on :8843. That is a
same-machine origin split, not a public API; bind to 127.0.0.1 if this ever runs
somewhere the network is not trusted.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def make_handler(backend):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, status=200):
            body = json.dumps(obj, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.end_headers()

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return {}

        def do_GET(self):
            if self.path.startswith("/api/state"):
                return self._send(backend.state())
            return self._send({"error": "not found"}, 404)

        def do_POST(self):
            body = self._body()

            if self.path.startswith("/api/drive"):
                ok, msg = backend.drive(body.get("dir", "stop"),
                                        body.get("speed", 0.0),
                                        body.get("turn", 0.0))
                return self._send({"ok": ok, "error": None if ok else msg})

            if not self.path.startswith("/api/action"):
                return self._send({"error": "not found"}, 404)

            action = body.get("action")
            # The e-stop is checked first and takes no arguments, so nothing in the
            # dispatch below can delay or fail it.
            if action == "estop":
                ok, msg = backend.estop()
            elif action == "autoware_start":
                ok, msg = backend.start_autoware()
            elif action == "autoware_stop":
                ok, msg = backend.stop_autoware()
            elif action == "mode_auto":
                ok, msg = backend.request_mode(True)
            elif action in ("mode_manual", "disengage"):
                ok, msg = backend.request_mode(False)
            elif action == "engage":
                ok, msg = backend.request_mode(True)
            elif action == "remote_toggle":
                ok, msg = backend.set_remote(not backend.remote_enabled)
            elif action == "drive_halt":
                ok, msg = backend.drive("stop", 0.0)
            elif action == "mode_ackermann":
                ok, msg = backend.set_steering_mode(False)
            elif action == "mode_in_situ":
                ok, msg = backend.set_steering_mode(True)
            elif action == "set_max_speed":
                backend.max_speed = max(0.1, min(1.5, float(body.get("value", 0.5))))
                ok, msg = True, "ok"
            else:
                ok, msg = False, f"unknown action {action!r}"

            return self._send({"ok": ok, "error": None if ok else msg})

    return Handler


def serve(backend, host="0.0.0.0", port=8843):
    httpd = ThreadingHTTPServer((host, port), make_handler(backend))
    httpd.daemon_threads = True
    return httpd
