"""Entry point: ROS node on one thread, HTTP server on another."""
from __future__ import annotations

import argparse
import sys
import threading

import rclpy
from rclpy.executors import SingleThreadedExecutor

from .control import ControlBackend
from .server import serve


def clean_argv(argv):
    """Drop the --ros-args tail ros2 launch appends, which argparse rejects."""
    return argv[:argv.index("--ros-args")] if "--ros-args" in argv else argv


def main(argv=None):
    argv = clean_argv(list(sys.argv[1:] if argv is None else argv))
    ap = argparse.ArgumentParser(description="Autoware web control backend (write paths)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8843)
    args = ap.parse_args(argv)

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
