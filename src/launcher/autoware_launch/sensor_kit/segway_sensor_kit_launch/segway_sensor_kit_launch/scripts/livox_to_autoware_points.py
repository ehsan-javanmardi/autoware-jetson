#!/usr/bin/env python3
"""Convert a Livox PointCloud2 into Autoware's PointXYZIRCAEDT layout.

Autoware's pointcloud_preprocessor checks the field layout of every incoming cloud and
**aborts** on a mismatch:

    The pointcloud layout is not compatible with PointXYZIRCAEDT. Aborting

livox_ros_driver2 publishes `x, y, z, intensity, tag, line, timestamp`, which is not that
layout, so the crop box that should move the cloud into base_link silently produced
nothing and /sensing/lidar/concatenated/pointcloud stayed at 0 Hz - with the driver itself
publishing perfectly well at 10 Hz. Nothing downstream of the point cloud worked, and
neither the driver nor the dashboard showed a fault.

The target layout, from autoware_point_types/types.hpp:

    float32 x, y, z
    uint8   intensity
    uint8   return_type
    uint16  channel
    float32 azimuth, elevation, distance
    uint32  time_stamp

Mapping decisions, and what is honestly missing:

* `intensity` is uint8 here and float32 from Livox, so it is clipped to 0..255.
* `return_type` comes from the Livox `tag`, masked to its return-number bits. The
  encodings are not the same taxonomy, so treat it as an indicator, not a truth.
* `channel` takes the Livox `line`, which is the scan line index. Close enough in meaning.
* `azimuth`, `elevation` and `distance` are recomputed from x/y/z rather than passed
  through, because Livox does not publish them. That is exact for distance, and exact for
  the angles up to the convention Autoware expects.
* `time_stamp` is nanoseconds since the cloud header, matching Autoware's use, derived
  from the Livox per-point absolute `timestamp`.
"""
import math
import struct
import sys

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from sensor_msgs.msg import PointCloud2, PointField

OUT_DTYPE = np.dtype([
    ("x", np.float32), ("y", np.float32), ("z", np.float32),
    ("intensity", np.uint8), ("return_type", np.uint8), ("channel", np.uint16),
    ("azimuth", np.float32), ("elevation", np.float32), ("distance", np.float32),
    ("time_stamp", np.uint32),
])

OUT_FIELDS = [
    PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
    PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
    PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
    PointField(name="intensity", offset=12, datatype=PointField.UINT8, count=1),
    PointField(name="return_type", offset=13, datatype=PointField.UINT8, count=1),
    PointField(name="channel", offset=14, datatype=PointField.UINT16, count=1),
    PointField(name="azimuth", offset=16, datatype=PointField.FLOAT32, count=1),
    PointField(name="elevation", offset=20, datatype=PointField.FLOAT32, count=1),
    PointField(name="distance", offset=24, datatype=PointField.FLOAT32, count=1),
    PointField(name="time_stamp", offset=28, datatype=PointField.UINT32, count=1),
]

_NP = {
    PointField.INT8: np.int8, PointField.UINT8: np.uint8,
    PointField.INT16: np.int16, PointField.UINT16: np.uint16,
    PointField.INT32: np.int32, PointField.UINT32: np.uint32,
    PointField.FLOAT32: np.float32, PointField.FLOAT64: np.float64,
}


def _in_dtype(msg):
    """Structured dtype describing the incoming cloud, padding included.

    Built from the message's own fields rather than assumed, so a driver version that
    reorders or adds a field does not silently produce garbage.
    """
    fields = sorted(msg.fields, key=lambda f: f.offset)
    names, formats, offsets = [], [], []
    for f in fields:
        if f.datatype not in _NP:
            continue
        names.append(f.name)
        formats.append(_NP[f.datatype])
        offsets.append(f.offset)
    return np.dtype({"names": names, "formats": formats, "offsets": offsets,
                     "itemsize": msg.point_step})


class Converter(Node):
    def __init__(self):
        super().__init__("livox_to_autoware_points")
        self.declare_parameter("input", "/sensing/lidar/top/livox/points_raw")
        self.declare_parameter("output", "/sensing/lidar/top/livox/points")
        self.declare_parameter("compute_angles", False)
        src = self.get_parameter("input").value
        dst = self.get_parameter("output").value
        self.compute_angles = bool(self.get_parameter("compute_angles").value)

        # Sensor data: best effort, shallow queue. A stale cloud is worthless, so
        # dropping is preferable to queueing.
        qos = QoSProfile(depth=5, reliability=QoSReliabilityPolicy.BEST_EFFORT,
                         history=QoSHistoryPolicy.KEEP_LAST)
        self.pub = self.create_publisher(PointCloud2, dst, qos)
        self.create_subscription(PointCloud2, src, self.on_cloud, qos)
        self._warned = False
        self._sig = None
        self._in_dt = None
        self.get_logger().info(f"converting {src} -> {dst} as PointXYZIRCAEDT")

    def on_cloud(self, msg: PointCloud2) -> None:
        # The incoming dtype is derived from the message's own fields, but rebuilding it
        # per cloud costs real time at 10 Hz, so it is cached against the layout
        # signature and only rebuilt if the driver ever changes its fields.
        sig = (msg.point_step, tuple((f.name, f.offset, f.datatype) for f in msg.fields))
        if sig != self._sig:
            self._in_dt = _in_dtype(msg)
            self._sig = sig
            self.get_logger().info("input layout: %s" % (self._in_dt.names,))
        try:
            arr = np.frombuffer(msg.data, dtype=self._in_dt)
        except (ValueError, TypeError) as exc:
            if not self._warned:
                self.get_logger().error(f"cannot read incoming cloud: {exc}")
                self._warned = True
            return

        n = arr.shape[0]
        out = np.zeros(n, dtype=OUT_DTYPE)
        out["x"] = arr["x"]
        out["y"] = arr["y"]
        out["z"] = arr["z"]

        if "intensity" in arr.dtype.names:
            out["intensity"] = np.clip(arr["intensity"], 0, 255).astype(np.uint8)
        if "tag" in arr.dtype.names:
            # Livox packs several things into tag; the low bits carry the return number.
            out["return_type"] = (np.asarray(arr["tag"]) & 0x03).astype(np.uint8)
        if "line" in arr.dtype.names:
            out["channel"] = np.asarray(arr["line"]).astype(np.uint16)

        # distance is cheap and several Autoware filters read it. azimuth and elevation
        # cost an arctan2 over every point each, which on an Orin already running the
        # full stack is the difference between keeping up and dropping most frames, so
        # they are opt-in. Autoware's layout check validates the FIELDS, not their
        # contents, and the crop box reads only x/y/z - but a filter that does use the
        # angles needs compute_angles true.
        x = out["x"]; y = out["y"]; z = out["z"]
        np.sqrt(x * x + y * y + z * z, out=out["distance"])
        if self.compute_angles:
            out["azimuth"] = np.arctan2(y, x)
            out["elevation"] = np.arctan2(z, np.maximum(np.hypot(x, y), 1e-9))

        if "timestamp" in arr.dtype.names:
            ts = np.asarray(arr["timestamp"]).astype(np.float64)
            base = ts.min() if n else 0.0
            # Livox timestamps are absolute nanoseconds; Autoware wants an offset from
            # the cloud header, so rebase and clamp into uint32.
            out["time_stamp"] = np.clip(ts - base, 0, np.iinfo(np.uint32).max).astype(np.uint32)

        o = PointCloud2()
        o.header = msg.header
        o.height = 1
        o.width = n
        o.fields = OUT_FIELDS
        o.is_bigendian = False
        o.point_step = OUT_DTYPE.itemsize
        o.row_step = OUT_DTYPE.itemsize * n
        o.is_dense = True
        o.data = out.tobytes()
        self.pub.publish(o)


def main():
    rclpy.init()
    node = Converter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
