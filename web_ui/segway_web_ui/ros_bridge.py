"""ROS 2 side of the dashboard.

Subscribes to Autoware's AD API diagnostic graph, measures topic rates, and
watches node liveness. Strictly read-only: no publishers, no service clients.

Topic rates are sampled with raw=True subscriptions. That hands us the
serialized bytes without constructing a Python message, which matters because
some of these topics are 128-beam point clouds - deserializing them in Python
just to count them would cost more CPU than Autoware's own pipeline.
"""

import threading
import time
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.qos import (QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile,
                       QoSReliabilityPolicy)
from rosidl_runtime_py.utilities import get_message

from autoware_adapi_v1_msgs.msg import DiagGraphStatus, DiagGraphStruct

STRUCT_TOPIC = "/api/system/diagnostics/struct"
STATUS_TOPIC = "/api/system/diagnostics/status"

# Latched AD API state topics used for the header bar. Loaded softly: if a
# message package is missing the dashboard still runs, just without that field.
HEADER_TOPICS = [
    ("operation_mode", "/api/operation_mode/state",
     "autoware_adapi_v1_msgs/msg/OperationModeState"),
    ("mrm", "/api/fail_safe/mrm_state", "autoware_adapi_v1_msgs/msg/MrmState"),
    ("localization_init", "/api/localization/initialization_state",
     "autoware_adapi_v1_msgs/msg/LocalizationInitializationState"),
    ("routing", "/api/routing/state", "autoware_adapi_v1_msgs/msg/RouteState"),
]

# Vehicle status, for the Vehicle tab. These are read from ROS rather than from the
# chassis directly and that is not a stylistic choice: the Segway SDK does not arbitrate
# access to the serial port. A second process opens /dev/ttyUSB0 without error, reads
# 0xffff for everything, and degrades the link for the vehicle interface while it does.
# segway_vehicle_interface owns the port; everyone else reads these topics.
VEHICLE_TOPICS = [
    ("battery", "/vehicle/status/battery", "sensor_msgs/msg/BatteryState"),
    ("velocity", "/vehicle/status/velocity_status",
     "autoware_vehicle_msgs/msg/VelocityReport"),
    ("control_mode", "/vehicle/status/control_mode",
     "autoware_vehicle_msgs/msg/ControlModeReport"),
]

CONTROL_MODE = {0: "no command", 1: "autonomous", 2: "autonomous steer only",
                3: "autonomous velocity only", 4: "manual", 5: "disengaged",
                6: "not ready"}

OPERATION_MODE = {0: "unknown", 1: "stop", 2: "autonomous", 3: "local", 4: "remote"}
MRM_STATE = {0: "unknown", 1: "normal", 2: "mrm operating",
             3: "mrm succeeded", 4: "mrm failed"}
ROUTE_STATE = {0: "unknown", 1: "unset", 2: "set", 3: "arrived", 4: "changing"}
LOCALIZATION_STATE = {0: "unknown", 1: "uninitialized", 2: "initializing", 3: "initialized"}

_QOS_LATCHED = QoSProfile(depth=1, history=QoSHistoryPolicy.KEEP_LAST,
                          reliability=QoSReliabilityPolicy.RELIABLE,
                          durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
_QOS_STATUS = QoSProfile(depth=1, history=QoSHistoryPolicy.KEEP_LAST,
                         reliability=QoSReliabilityPolicy.BEST_EFFORT,
                         durability=QoSDurabilityPolicy.VOLATILE)
# Best-effort + volatile subscribers match reliable and transient-local
# publishers too, so one profile works for every sampled topic.
_QOS_SAMPLE = QoSProfile(depth=1, history=QoSHistoryPolicy.KEEP_LAST,
                         reliability=QoSReliabilityPolicy.BEST_EFFORT,
                         durability=QoSDurabilityPolicy.VOLATILE)


class RateMeter:
    """Sliding-window message rate for one topic."""

    def __init__(self, window_s):
        self.window = window_s
        self.started = time.time()
        self._stamps = deque()
        self._bytes = deque()
        self.seen_publisher = False
        self.last_msg_t = None
        self._lock = threading.Lock()

    def attach(self):
        """Called when the subscription is actually created.

        The averaging window has to start here, not at construction: discovery
        runs on a 2 s timer, so a meter built at start-up may only begin
        receiving seconds later, and normalising by the older timestamp would
        under-report the rate for the whole first window.
        """
        with self._lock:
            self.started = time.time()
            self._stamps.clear()
            self._bytes.clear()

    def record(self, nbytes):
        now = time.time()
        with self._lock:
            self._stamps.append(now)
            self._bytes.append(nbytes)
            self.last_msg_t = now
            self._trim(now)

    def _trim(self, now):
        cutoff = now - self.window
        while self._stamps and self._stamps[0] < cutoff:
            self._stamps.popleft()
            self._bytes.popleft()

    def sample(self):
        """Return (hz, seen_publisher, age, bytes_per_s, warming).

        The rate is divided by however much of the window has actually elapsed,
        not by the nominal window. Dividing by a 10 s window two seconds after
        start-up would report a fifth of the true rate and paint every healthy
        topic red - which teaches you to ignore red.
        """
        now = time.time()
        with self._lock:
            self._trim(now)
            span = min(self.window, now - self.started)
            warming = span < 2.0
            if span <= 0.05:
                return 0.0, self.seen_publisher, None, 0.0, True
            hz = len(self._stamps) / span
            bps = sum(self._bytes) / span
            age = (now - self.last_msg_t) if self.last_msg_t else None
        return hz, self.seen_publisher, age, bps, warming


class HealthBridge(Node):
    def __init__(self, model, cfg):
        super().__init__("segway_web_ui")
        self.model = model
        s = cfg.get("settings", {})
        self.window = float(s.get("rate_window_s", 10.0))

        self._struct_id = None
        self.header = {}
        self.node_names = []

        self.create_subscription(DiagGraphStruct, STRUCT_TOPIC,
                                 self._on_struct, _QOS_LATCHED)
        self.create_subscription(DiagGraphStatus, STATUS_TOPIC,
                                 self._on_status, _QOS_STATUS)

        for key, topic, type_str in HEADER_TOPICS:
            try:
                msg_cls = get_message(type_str)
            except Exception:
                self.get_logger().warn("header topic %s unavailable (%s)" % (topic, type_str))
                continue
            self.create_subscription(
                msg_cls, topic,
                lambda m, k=key: self._on_header(k, m), _QOS_LATCHED)

        self.vehicle = {}
        for key, topic, type_str in VEHICLE_TOPICS:
            try:
                msg_cls = get_message(type_str)
            except Exception:
                self.get_logger().warn("vehicle topic %s unavailable (%s)" % (topic, type_str))
                continue
            self.create_subscription(
                msg_cls, topic,
                lambda m, k=key: self._on_vehicle(k, m), 1)

        # Every topic named anywhere in devices.yaml gets a rate meter.
        self.meters = {}
        for group in cfg.get("groups", []):
            for dev in group.get("devices", []):
                for t in dev.get("topics", []):
                    self.meters.setdefault(t["topic"], RateMeter(self.window))
        self._subscribed = set()

        self.create_timer(2.0, self._discover)
        self.create_timer(2.0, self._refresh_nodes)
        self.get_logger().info(
            "watching %d topics, waiting for %s" % (len(self.meters), STRUCT_TOPIC))

    # ------------------------------------------------------------- callbacks

    def _on_struct(self, msg):
        if msg.id == self._struct_id:
            return
        self._struct_id = msg.id
        self.model.set_struct(msg)
        self.get_logger().info(
            "diagnostic graph '%s': %d nodes, %d leaves"
            % (msg.id, len(msg.nodes), len(msg.diags)))

    def _on_status(self, msg):
        if not self.model.set_status(msg) and msg.id != self._struct_id:
            # Status arrived for a graph we have not seen the struct of; the
            # struct is latched so it will turn up, nothing to do but wait.
            pass

    def _on_header(self, key, msg):
        if key == "operation_mode":
            self.header[key] = OPERATION_MODE.get(getattr(msg, "mode", 0), "unknown")
            self.header["autoware_control"] = bool(
                getattr(msg, "is_autoware_control_enabled", False))
            self.header["autonomous_available"] = bool(
                getattr(msg, "is_autonomous_mode_available", False))
        elif key == "mrm":
            self.header[key] = MRM_STATE.get(getattr(msg, "state", 0), "unknown")
        elif key == "routing":
            self.header[key] = ROUTE_STATE.get(getattr(msg, "state", 0), "unknown")
        elif key == "localization_init":
            self.header[key] = LOCALIZATION_STATE.get(getattr(msg, "state", 0), "unknown")

    def _on_vehicle(self, key, msg):
        now = time.time()
        if key == "battery":
            self.vehicle["battery_percent"] = round(getattr(msg, "percentage", 0.0) * 100.0, 1)
            self.vehicle["battery_volts"] = round(getattr(msg, "voltage", 0.0), 2)
            self.vehicle["chassis_present"] = bool(getattr(msg, "present", False))
        elif key == "velocity":
            self.vehicle["speed_mps"] = round(getattr(msg, "longitudinal_velocity", 0.0), 3)
            self.vehicle["yaw_rate"] = round(getattr(msg, "heading_rate", 0.0), 3)
        elif key == "control_mode":
            self.vehicle["control_mode"] = CONTROL_MODE.get(getattr(msg, "mode", 0), "unknown")
        self.vehicle["updated"] = now

    def vehicle_state(self):
        """Vehicle status, plus how stale it is.

        The Vehicle tab must distinguish "the interface is running and the robot is
        stationary" from "nothing is publishing", which look identical if you only
        report zeros.
        """
        out = dict(self.vehicle)
        updated = out.pop("updated", None)
        out["running"] = updated is not None and (time.time() - updated) < 3.0
        out["age_s"] = round(time.time() - updated, 1) if updated else None
        return out

    # ------------------------------------------------------------- discovery

    def _discover(self):
        """Subscribe to any watched topic that has since been advertised."""
        try:
            available = dict(self.get_topic_names_and_types())
        except Exception:
            return
        for topic, meter in self.meters.items():
            if topic in self._subscribed:
                continue
            types = available.get(topic)
            if not types:
                continue
            try:
                msg_cls = get_message(types[0])
                self.create_subscription(
                    msg_cls, topic,
                    lambda raw, m=meter: m.record(len(raw)),
                    _QOS_SAMPLE, raw=True)
            except Exception as exc:
                self.get_logger().warn("cannot sample %s: %s" % (topic, exc))
                continue
            meter.attach()
            meter.seen_publisher = True
            self._subscribed.add(topic)
            self.get_logger().info("sampling %s (%s)" % (topic, types[0]))

    def _refresh_nodes(self):
        try:
            self.node_names = sorted(
                (ns.rstrip("/") + "/" + n) if ns != "/" else "/" + n
                for n, ns in self.get_node_names_and_namespaces())
        except Exception:
            pass

    def rates(self):
        return {topic: meter.sample() for topic, meter in self.meters.items()}
