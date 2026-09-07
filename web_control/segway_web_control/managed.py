"""Start, stop and restart the platform's long-running launches.

The web UI needs to cycle the sensor drivers and the vehicle interface without the
operator finding a terminal. Something therefore has to own those processes.

It cannot simply be "whatever this backend spawned", because segway.sh may have started
them before this process existed, and a Stop button that silently does nothing to a
process it did not spawn is worse than no button at all. So each managed launch is
identified by a pattern matching its real processes, and stop acts on whatever is running
under that pattern regardless of who started it. Start always spawns here.

Signal order matters:

* SIGINT to the process group first. `ros2 launch` shuts its nodes down cleanly on SIGINT
  and orphans them on SIGKILL, and the vehicle interface uses that window to zero the
  command and disable the motors.
* SIGKILL only to whatever survives the grace period, reported separately, because a
  launch that had to be killed did not run its shutdown path.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time


def _pids_matching(pattern: str) -> list[int]:
    """PIDs whose command line matches `pattern`, excluding this process.

    pgrep -f rather than a ROS graph lookup: a launch that is still starting, or wedged,
    has processes but may have no nodes yet, and those are exactly the ones a Restart
    button must be able to kill.
    """
    try:
        out = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    except OSError:
        return []
    me = os.getpid()
    pids = []
    for tok in out.stdout.split():
        try:
            pid = int(tok)
        except ValueError:
            continue
        if pid != me:
            pids.append(pid)
    return pids


def _signal_all(pids, sig) -> None:
    """Signal each process, preferring its group so a launch takes its children along.

    Guarded against killing our own group. segway.sh starts each service as a plain
    background job, which puts it in segway.sh's process group; signalling that group
    once took down segway.sh, the web UI, the control backend and every other service
    along with the one being stopped. The guard is here rather than only in segway.sh
    because it has to hold however the process was started.
    """
    my_group = os.getpgid(0)
    for pid in pids:
        try:
            group = os.getpgid(pid)
        except (ProcessLookupError, PermissionError):
            group = None
        if group is not None and group != my_group:
            try:
                os.killpg(group, sig)
                continue
            except (ProcessLookupError, PermissionError):
                pass
        # Shares our group, or the group could not be signalled: hit the process alone.
        # Its children may be orphaned, which the caller reports rather than hides.
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass


class Managed:
    """One supervised launch."""

    def __init__(self, logger, name: str, cmd: list[str], cwd: str,
                 pattern, log_name: str) -> None:
        self.logger = logger
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        # One string or several. The composable-node containers a launch spawns do not
        # carry the launch file name in their command line, so a single pattern often
        # cannot reach every process a service owns.
        self.patterns = [pattern] if isinstance(pattern, str) else list(pattern)
        self.log_path = os.path.join(os.path.expanduser("~/.segway/logs"), log_name)
        self.proc: subprocess.Popen | None = None

    # ------------------------------------------------------------------ state

    def pids(self) -> list[int]:
        seen = []
        for pat in self.patterns:
            for pid in _pids_matching(pat):
                if pid not in seen:
                    seen.append(pid)
        return seen

    def running(self) -> bool:
        return bool(self.pids())

    def owned(self) -> bool:
        """True when this backend spawned what is running, rather than segway.sh."""
        return self.proc is not None and self.proc.poll() is None

    def state(self) -> dict:
        pids = self.pids()
        return {
            "name": self.name,
            "running": bool(pids),
            "processes": len(pids),
            "owned": self.owned(),
            "log": self.log_path,
        }

    # ----------------------------------------------------------------- actions

    def start(self) -> tuple[bool, str]:
        if self.running():
            return False, f"{self.name} is already running"
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        try:
            fh = open(self.log_path, "wb")
            self.proc = subprocess.Popen(
                self.cmd, cwd=self.cwd, stdout=fh, stderr=subprocess.STDOUT,
                start_new_session=True)
        except OSError as exc:
            return False, f"could not start {self.name}: {exc}"
        self.logger.warn(f"{self.name} started from the web UI")
        return True, "started"

    def stop(self, grace_s: float = 10.0) -> tuple[bool, str]:
        pids = self.pids()
        if not pids:
            return False, f"{self.name} is not running"

        _signal_all(pids, signal.SIGINT)
        deadline = time.time() + grace_s
        while time.time() < deadline:
            if not self.pids():
                self.proc = None
                self.logger.warn(f"{self.name} stopped")
                return True, "stopped"
            time.sleep(0.2)

        _signal_all(self.pids(), signal.SIGKILL)
        time.sleep(0.5)
        self.proc = None
        remaining = len(self.pids())
        if remaining:
            return False, f"{remaining} process(es) survived SIGKILL"
        self.logger.warn(f"{self.name} force-stopped after ignoring SIGINT")
        return True, "stopped (forced)"

    def restart(self) -> tuple[bool, str]:
        if self.running():
            ok, msg = self.stop()
            if not ok:
                return False, f"restart aborted, stop failed: {msg}"
            # The chassis serial port and the Livox UDP ports are not released the
            # instant a process dies; starting again immediately can fail to bind.
            time.sleep(2.0)
        return self.start()
