"""Offline check of the model against a synthetic diagnostic graph.

Duck-types the ROS messages so this runs with no ROS environment at all.
"""
import sys, time, types, yaml
sys.path.insert(0, ".")
from segway_web_ui.model import HealthModel, OK, WARN, ERROR, STALE

def N(path): return types.SimpleNamespace(path=path)
def L(parent, name): return types.SimpleNamespace(parent=parent, name=name)
def K(parent, child): return types.SimpleNamespace(parent=parent, child=child)
def kv(k, v): return types.SimpleNamespace(key=k, value=v)

# nodes: 0 /autoware/localization, 1 .../state, 2 .../topic_rate_check,
#        3 /autoware/perception
nodes = [N("/autoware/localization"), N("/autoware/localization/state"),
         N("/autoware/localization/topic_rate_check"), N("/autoware/perception")]
links = [K(0, 1), K(0, 2)]
diags = [L(1, "state"), L(2, "localization_topic_status"), L(3, "objects_rate")]
struct = types.SimpleNamespace(id="g1", nodes=nodes, diags=diags, links=links)

cfg = yaml.safe_load(open("config/devices.yaml"))
m = HealthModel(cfg)
m.set_struct(struct)

mods = [x["key"] for x in m.modules]
assert mods[0] == "sensing", mods
assert "localization" in mods and "perception" in mods, mods
print("modules:", mods)

# leaf 1 belongs to localization, leaf 2 to perception
assert m.leaves[1]["module"] == "localization", m.leaves[1]
assert m.leaves[2]["module"] == "perception", m.leaves[2]
print("module attribution OK")

def status(levels, msgs):
    return types.SimpleNamespace(
        id="g1",
        nodes=[types.SimpleNamespace(level=l) for l in levels[0]],
        diags=[types.SimpleNamespace(level=l, message=msg, hardware_id="hw",
                                     values=[kv("rate", "3.2")])
               for l, msg in zip(levels[1], msgs)])

assert m.set_status(status(([OK,OK,OK,OK],[OK,OK,OK]), ["ok","ok","ok"]))
assert not m.problems(), m.problems()
print("clean graph -> no problems OK")

# a mismatched graph id must be ignored, not applied to the wrong indices
bad = status(([OK]*4, [OK]*3), ["x"]*3); bad.id = "g2"
assert not m.set_status(bad)
print("graph-id guard OK")

# raise an error on the localization topic-rate leaf
m.set_status(status(([ERROR,OK,ERROR,OK],[OK,ERROR,OK]),
                    ["ok","rate 0.4 Hz < 1.0 Hz","ok"]))
p = m.problems()
assert len(p) == 1 and p[0]["level"] == ERROR, p
assert p[0]["module"] == "localization" and p[0]["since"], p[0]
print("problem detected:", p[0]["name"], "|", p[0]["message"], "| module", p[0]["module"])

summary = {x["key"]: x for x in m.module_summary()}
assert summary["localization"]["error"] == 1, summary["localization"]
assert summary["perception"]["error"] == 0, summary["perception"]
print("counts OK: localization error=1, perception error=0")

# clear it: must latch, then drop out after the window
m.set_status(status(([OK]*4,[OK]*3), ["ok"]*3))
p = m.problems()
assert len(p) == 1 and p[0]["cleared_at"], p
print("latch OK: cleared problem still listed")
p = m.problems(now=time.time() + 31)
assert not p, p
print("latch expiry OK")

assert len(m.events) >= 2, list(m.events)
print("events recorded:", len(m.events))

# synthetic sensing: fitted lidar unreachable and starved, alternates absent
rates = {"/sensing/lidar/top/livox/points": (0.2, True, 4.0, 100.0, False)}
probes = {"192.168.1.126": (False, None, time.time())}
m.update_sensing(rates, probes)
sens = [x for x in m.module_summary() if x["key"] == "sensing"][0]
assert sens["level"] in (ERROR, STALE), sens
sp = [x for x in m.problems() if x["module"] == "sensing"]
assert any("unreachable" in x["message"] for x in sp), sp[:3]
assert any("0.2 Hz" in x["message"] for x in sp), sp[:3]
print("sensing synthesis OK:", sens["level"], "| problems", len(sp))

# the unfitted Velodynes and OS-2-32 must not be in that list
for x in sp:
    assert "velodyne" not in x["path"].lower(), "unfitted hardware leaked: " + x["path"]
    assert "os_2_32" not in x["path"], "unfitted hardware leaked: " + x["path"]
print("muting OK: %d sensing problems, no unfitted hardware" % len(sp))

# leaf paths must not nest the topic as if it were a path segment
bad = [l["path"] for l in m.syn_leaves.values()
       if l["path"].count("/sensing") > 1 and "\u2192" not in l["path"]]
assert not bad, bad[:3]
print("leaf path shape OK, e.g.:",
      [l["path"] for l in m.syn_leaves.values() if l["kind"] == "rate"][0])

# a fitted-but-silent optional device is NOT muted: reachable + no data is a fault
m.update_sensing({}, {"192.168.1.201": (True, 1.2, time.time()),
                      "192.168.1.126": (True, 0.8, time.time())})
sp2 = [x for x in m.problems() if "velodyne_vlp_16_top" in x["path"]]
assert sp2, "reachable-but-silent optional device should surface"
print("reachable-but-silent optional device surfaces OK:", sp2[0]["message"])

j = m.struct_json()
print("struct json: %d nodes, %d leaves, %d modules"
      % (len(j["nodes"]), len(j["leaves"]), len(j["modules"])))
s = m.stream_json()
print("stream json keys:", sorted(s.keys()))
print("\nALL MODEL TESTS PASSED")
