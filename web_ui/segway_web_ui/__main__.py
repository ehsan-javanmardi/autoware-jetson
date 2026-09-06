"""Entry point: python3 -m segway_web_ui [--host H] [--port P] [--config F]"""

import argparse
import signal
import sys
import threading

import yaml

from .model import HealthModel
from .prober import DeviceProber
from .resources import default_config
from .server import Context, serve


def clean_argv(argv):
    """Normalise argv so one entry point serves a shell and ros2 launch alike.

    Two things launch does that argparse will not accept:

    * It appends `--ros-args -r __node:=...` to every node it starts. By ROS
      convention that section runs to the end of argv or to a bare `--`.
    * An XML `args=` attribute that interpolates an unset substitution yields a
      genuinely empty argv element rather than nothing at all, and argparse
      reports it as `unrecognized arguments:` with no name. Every flag this
      program takes has a non-empty value, so empty tokens are always that.
    """
    if "--ros-args" in argv:
        head = argv[:argv.index("--ros-args")]
        rest = argv[argv.index("--ros-args") + 1:]
        argv = head + (rest[rest.index("--") + 1:] if "--" in rest else [])
    return [a for a in argv if a != ""]


def main(argv=None):
    argv = clean_argv(list(sys.argv[1:] if argv is None else argv))
    ap = argparse.ArgumentParser(description="Autoware health dashboard (read-only)")
    ap.add_argument("--host", default="0.0.0.0",
                    help="bind address (default: all interfaces)")
    ap.add_argument("--port", type=int, default=8842)
    ap.add_argument("--config", default=None,
                    help="device inventory (default: the packaged devices.yaml)")
    ap.add_argument("--no-probe", action="store_true",
                    help="skip ping/TCP reachability probing")
    args = ap.parse_args(argv)

    config_path = args.config or default_config()
    with open(config_path) as fh:
        cfg = yaml.safe_load(fh)

    model = HealthModel(cfg)
    prober = DeviceProber(cfg)
    if not args.no_probe:
        prober.start()

    ctx = Context(model, cfg, prober)
    stop = threading.Event()

    # ROS runs on its own thread; importing rclpy is deferred so that --help and
    # a bad config fail fast without needing a sourced ROS environment.
    def ros_thread():
        try:
            import rclpy
            from rclpy.executors import SingleThreadedExecutor

            from .ros_bridge import HealthBridge
            rclpy.init()
            node = HealthBridge(model, cfg)
            ctx.bridge = node

            def refresh():
                model.update_sensing(node.rates(), prober.results())

            node.create_timer(1.0, refresh)
            executor = SingleThreadedExecutor()
            executor.add_node(node)
            try:
                while rclpy.ok() and not stop.is_set():
                    executor.spin_once(timeout_sec=0.2)
            except Exception as exc:
                if type(exc).__name__ != "ExternalShutdownException":
                    raise
            finally:
                executor.remove_node(node)
                node.destroy_node()
                if rclpy.ok():
                    rclpy.shutdown()
        except Exception as exc:  # keep the UI up even with no ROS at all
            import traceback
            print("[health-ui] ROS bridge unavailable: %s: %s"
                  % (type(exc).__name__, exc), file=sys.stderr)
            traceback.print_exc()
            print("[health-ui] dashboard still serving; Autoware modules will "
                  "read as STALE", file=sys.stderr)

    threading.Thread(target=ros_thread, name="ros", daemon=True).start()

    httpd = serve(ctx, args.host, args.port)
    shown = "localhost" if args.host in ("0.0.0.0", "") else args.host
    print("[health-ui] http://%s:%d  (read-only; Ctrl-C to stop)" % (shown, args.port))

    def shutdown(*_):
        stop.set()
        prober.stop()
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
