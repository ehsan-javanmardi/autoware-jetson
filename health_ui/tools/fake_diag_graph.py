"""Publish a small diagnostic graph shaped like Autoware's.

Lets you develop and demo the dashboard with no vehicle and no Autoware:

    source /opt/ros/humble/setup.bash
    source ~/workspace/pix_autoware/install/setup.bash
    python3 tools/fake_diag_graph.py       # then ./run.sh in another shell

It publishes five modules, holds them healthy for three seconds, then drops
/autoware/localization into ERROR so you can watch the tile turn red, the
problem appear in the rail, and the event get logged.
"""
import sys

import rclpy
from rclpy.node import Node
from rclpy.qos import (QoSDurabilityPolicy, QoSProfile, QoSReliabilityPolicy)
from autoware_adapi_v1_msgs.msg import (DiagGraphStruct, DiagGraphStatus,
                                        DiagNodeStruct, DiagNodeStatus,
                                        DiagLeafStruct, DiagLeafStatus,
                                        DiagLinkStruct, KvString)

LATCH = QoSProfile(depth=1, reliability=QoSReliabilityPolicy.RELIABLE,
                   durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
BE = QoSProfile(depth=1, reliability=QoSReliabilityPolicy.BEST_EFFORT)

PATHS = ["/autoware/localization", "/autoware/localization/state",
         "/autoware/localization/topic_rate_check", "/autoware/perception",
         "/autoware/map", "/autoware/vehicle"]
LINKS = [(0, 1), (0, 2)]
DIAGS = [(1, "state"), (2, "localization_topic_status"),
         (3, "objects_rate"), (4, "vector_map"), (5, "velocity")]

class Fake(Node):
    def __init__(self):
        super().__init__("fake_diag_graph")
        self.gid = sys.argv[1] if len(sys.argv) > 1 else "fake-graph-1"
        self.ps = self.create_publisher(DiagGraphStruct, "/api/system/diagnostics/struct", LATCH)
        self.pt = self.create_publisher(DiagGraphStatus, "/api/system/diagnostics/status", BE)
        s = DiagGraphStruct(); s.id = self.gid
        s.nodes = [DiagNodeStruct(path=p) for p in PATHS]
        s.links = [DiagLinkStruct(parent=a, child=b) for a, b in LINKS]
        s.diags = [DiagLeafStruct(parent=p, name=n) for p, n in DIAGS]
        s.stamp = self.get_clock().now().to_msg()
        self.ps.publish(s)
        self.n = 0
        self.create_timer(0.1, self.tick)

    def tick(self):
        self.n += 1
        # flip the localization topic-rate leaf into ERROR after 3 seconds
        bad = self.n > 30
        st = DiagGraphStatus(); st.id = self.gid
        st.stamp = self.get_clock().now().to_msg()
        node_levels = [2 if bad else 0, 0, 2 if bad else 0, 0, 0, 1]
        st.nodes = [DiagNodeStatus(level=bytes([l]), input_level=bytes([l]), latch_level=bytes([l]),
                                   is_dependent=False) for l in node_levels]
        leaf = [(0, "OK"), (2 if bad else 0, "rate 0.4Hz < 1.0Hz" if bad else "OK"),
                (0, "OK"), (0, "OK"), (1, "velocity slightly stale")]
        st.diags = [DiagLeafStatus(level=bytes([l]), input_level=bytes([l]), message=m,
                                   hardware_id="hw%d" % i,
                                   values=[KvString(key="rate", value="0.4"),
                                           KvString(key="expected", value="1.0")])
                    for i, (l, m) in enumerate(leaf)]
        self.pt.publish(st)

rclpy.init(); n = Fake()
try: rclpy.spin(n)
except KeyboardInterrupt: pass
