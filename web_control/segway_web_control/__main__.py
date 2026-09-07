"""Entry point: ROS node on one thread, HTTP server on another."""
from __future__ import annotations

import argparse
import os
import sys
import threading

import rclpy
from rclpy.executors import SingleThreadedExecutor

from .control import ControlBackend
from .server import serve


def clean_argv(argv):
    """Drop the --ros-args tail ros2 launch appends, which argparse rejects."""
    return argv[:argv.index("--ros-args")] if "--ros-args" in argv else argv


def _load_env_file(path):
    """Merge `export KEY=value` lines from a shell env file into os.environ.

    Deliberately minimal: it handles the `export K=V` form that file uses and ignores
    anything else, rather than pretending to be a shell.
    """
    try:
        with open(path) as fh:
            lines = fh.readlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def main(argv=None):
    argv = clean_argv(list(sys.argv[1:] if argv is None else argv))
    ap = argparse.ArgumentParser(description="Autoware web control backend (write paths)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8843)
    args = ap.parse_args(argv)

    # The sensor launch this backend spawns includes the NTRIP client, which reads its
    # credentials from the environment. segway.sh sources ~/.ichimill.env; a backend
    # started any other way does not, and the caster answers 401 with nothing in the UI
    # to say why. Load it here so a child inherits it however the backend was started.
    _load_env_file(os.path.expanduser("~/.ichimill.env"))

    rclpy.init()
    backend = ControlBackend()
    httpd = serve(backend, args.host, args.port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    backend.get_logger().info(f"control backend on http://{args.host}:{args.port}")

    ex = SingleThreadedExecutor()
    ex.add_node(backend)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        # Never leave the robot armed because the backend went away.
        try:
            backend.estop()
        except Exception:
            pass
        httpd.shutdown()
        backend.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
