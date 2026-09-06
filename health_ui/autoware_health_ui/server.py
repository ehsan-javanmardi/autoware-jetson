"""HTTP + Server-Sent Events front door.

Read-only by construction: every route is a GET and nothing here can publish a
topic or call a service. SSE rather than WebSocket because the data only ever
flows server -> browser, and SSE needs no dependency beyond the standard library.
"""

import json
import mimetypes
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .resources import frontend_dir

FRONTEND = frontend_dir()


class Context:
    """Shared handles the request threads read from."""

    def __init__(self, model, cfg, prober):
        self.model = model
        self.cfg = cfg
        self.prober = prober
        self.bridge = None
        self.started = time.time()
        self.stream_hz = float(cfg.get("settings", {}).get("stream_hz", 2.0))

    def rates(self):
        return self.bridge.rates() if self.bridge else {}

    def node_names(self):
        return self.bridge.node_names if self.bridge else []

    def header(self):
        return dict(self.bridge.header) if self.bridge else {}

    def devices(self):
        rates = self.rates()
        probes = self.prober.results()
        out = []
        for group in self.cfg.get("groups", []):
            for dev in group.get("devices", []):
                ip = dev.get("ip")
                reachable, rtt, probe_t = probes.get(ip, (None, None, None))
                topics = []
                for t in dev.get("topics", []):
                    hz, seen, age, bps, warming = rates.get(
                        t["topic"], (0.0, False, None, 0.0, True))
                    topics.append({
                        "topic": t["topic"], "hz": round(hz, 2),
                        "expect_hz": t.get("expect_hz"), "seen": seen,
                        "warming": warming,
                        "age": round(age, 2) if age is not None else None,
                        "kbps": round(bps / 1000.0, 1),
                    })
                out.append({
                    "group": group.get("label", group["key"]),
                    "group_key": group["key"],
                    "name": dev["name"], "ip": ip,
                    "probe": dev.get("probe", "icmp"),
                    "profile": dev.get("profile"),
                    "reachable": reachable, "rtt_ms": round(rtt, 1) if rtt else None,
                    "probe_age": round(time.time() - probe_t, 1) if probe_t else None,
                    "topics": topics,
                })
        host = dict(self.cfg.get("host", {}))
        if host.get("ip"):
            r, rtt, pt = probes.get(host["ip"], (None, None, None))
            host.update({"reachable": r, "rtt_ms": round(rtt, 1) if rtt else None})
        return {"host": host, "devices": out,
                "window_s": self.cfg.get("settings", {}).get("rate_window_s", 10.0)}


def make_handler(ctx):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "autoware-health-ui"

        def log_message(self, fmt, *args):
            pass  # the console belongs to the ROS logs

        # ------------------------------------------------------------ helpers

        def _json(self, payload, code=200):
            body = json.dumps(payload, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _static(self, name):
            path = os.path.normpath(os.path.join(FRONTEND, name))
            if not path.startswith(FRONTEND) or not os.path.isfile(path):
                self._json({"error": "not found"}, 404)
                return
            with open(path, "rb") as fh:
                body = fh.read()
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def _stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            period = 1.0 / max(0.2, ctx.stream_hz)
            try:
                while True:
                    payload = ctx.model.stream_json()
                    payload["header"] = ctx.header()
                    payload["ros_nodes"] = len(ctx.node_names())
                    chunk = "data: %s\n\n" % json.dumps(payload, default=str)
                    self.wfile.write(chunk.encode())
                    self.wfile.flush()
                    time.sleep(period)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

        # --------------------------------------------------------------- GET

        def do_GET(self):
            url = urlparse(self.path)
            route, qs = url.path, parse_qs(url.query)

            if route == "/":
                return self._static("index.html")
            if route in ("/app.js", "/styles.css", "/favicon.ico"):
                return self._static(route.lstrip("/"))

            if route == "/api/struct":
                return self._json(ctx.model.struct_json())
            if route == "/api/snapshot":
                snap = ctx.model.stream_json()
                snap["header"] = ctx.header()
                return self._json(snap)
            if route == "/api/stream":
                return self._stream()
            if route == "/api/devices":
                return self._json(ctx.devices())
            if route == "/api/detail":
                item = (qs.get("id") or [""])[0]
                return self._json({"id": item,
                                   "detail": ctx.model.detail_of(item),
                                   "history": ctx.model.history_of(item)})
            if route == "/api/history":
                item = (qs.get("id") or [""])[0]
                return self._json({"id": item, "history": ctx.model.history_of(item)})
            if route == "/api/ros_nodes":
                return self._json({"nodes": ctx.node_names()})

            return self._json({"error": "not found", "path": route}, 404)

    return Handler


def serve(ctx, host, port):
    httpd = ThreadingHTTPServer((host, port), make_handler(ctx))
    httpd.daemon_threads = True
    return httpd
