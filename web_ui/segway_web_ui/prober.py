"""Device reachability probing.

Runs in its own thread so a hanging network probe can never stall the ROS
executor or the HTTP server. Probes go out in parallel: nine devices at a
one-second timeout would otherwise take longer than the probe interval.
"""

import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor


def _ping(ip, timeout_s=1.0):
    t0 = time.time()
    try:
        rc = subprocess.run(
            ["ping", "-c", "1", "-W", str(int(max(1, timeout_s))), ip],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=timeout_s + 1.5).returncode
    except Exception:
        return False, None
    # No round-trip time when the host did not answer - the elapsed time is
    # just the timeout, and reporting it as an RTT would be a lie.
    return (True, (time.time() - t0) * 1000.0) if rc == 0 else (False, None)


def _tcp(ip, port, timeout_s=1.0):
    t0 = time.time()
    try:
        with socket.create_connection((ip, port), timeout=timeout_s):
            return True, (time.time() - t0) * 1000.0
    except Exception:
        return False, None


class DeviceProber:
    def __init__(self, cfg):
        s = cfg.get("settings", {})
        self.interval = float(s.get("probe_interval_s", 10.0))
        self.targets = []
        for group in cfg.get("groups", []):
            for dev in group.get("devices", []):
                probe = dev.get("probe", "icmp")
                if probe == "none" or not dev.get("ip"):
                    continue
                self.targets.append((dev["ip"], probe))
        host = cfg.get("host", {})
        if host.get("ip"):
            self.targets.append((host["ip"], "icmp"))

        self._results = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def _probe_one(self, target):
        ip, probe = target
        if probe.startswith("tcp:"):
            ok, rtt = _tcp(ip, int(probe.split(":", 1)[1]))
        else:
            ok, rtt = _ping(ip)
        return ip, (ok, rtt, time.time())

    def _run(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            while not self._stop.is_set():
                for ip, res in pool.map(self._probe_one, self.targets):
                    with self._lock:
                        self._results[ip] = res
                self._stop.wait(self.interval)

    def start(self):
        if not self.targets:
            return
        self._thread = threading.Thread(target=self._run, name="prober", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def results(self):
        with self._lock:
            return dict(self._results)
