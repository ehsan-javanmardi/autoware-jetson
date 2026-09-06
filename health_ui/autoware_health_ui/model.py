"""Health model.

Holds the Autoware diagnostic graph (structure + live levels), synthesises a
Sensing module that Autoware's graph does not provide, and tracks problems and
their history. Everything here is pure Python - no ROS imports - so it can be
exercised without a running Autoware.

Index semantics, verified against autoware_diagnostic_graph_aggregator:
  * DiagGraphStruct.nodes[i]  <-> DiagGraphStatus.nodes[i]   (index aligned)
  * DiagGraphStruct.diags[i]  <-> DiagGraphStatus.diags[i]   (index aligned)
  * links[] hold node->node edges ONLY (children that are NodeUnits)
  * diags[i].parent is an index into nodes[] (leaves hang off a node)
  * node and diag indices are separate index spaces
"""

import re
import threading
import time
from collections import defaultdict, deque

OK, WARN, ERROR, STALE = 0, 1, 2, 3
LEVEL_NAME = {OK: "OK", WARN: "WARN", ERROR: "ERROR", STALE: "STALE"}

# Autoware's top-level module nodes are exactly /autoware/<name>.
_MODULE_RE = re.compile(r"^/autoware/([a-z_]+)$")

MODULE_LABELS = {
    "sensing": "Sensing",
    "map": "Map",
    "localization": "Localization",
    "perception": "Perception",
    "planning": "Planning",
    "control": "Control",
    "vehicle": "Vehicle",
    "system": "System",
}
# Display order: roughly the data flow through the stack.
MODULE_ORDER = ["sensing", "map", "localization", "perception",
                "planning", "control", "vehicle", "system"]

SENSING_ROOT = "/sensing"
LATCH_S = 30.0          # keep a cleared problem visible this long
HISTORY_LEN = 400       # level transitions retained per item


def _lvl(value):
    """Coerce a ROS `byte` level to int.

    rclpy delivers a `byte` field as a length-1 bytes object, not an integer -
    int(b"\x02") raises TypeError - so every level read from a message has to
    come through here.
    """
    if isinstance(value, (bytes, bytearray)):
        return value[0] if value else OK
    return int(value)


def _short(path):
    """Last path segment, for compact tree labels."""
    return path.rstrip("/").rsplit("/", 1)[-1] or path


class HealthModel:
    def __init__(self, cfg):
        self.cfg = cfg
        s = cfg.get("settings", {})
        self.stale_after = float(s.get("stale_after_s", 5.0))
        self.warn_ratio = float(s.get("rate_warn_ratio", 0.7))
        self.error_ratio = float(s.get("rate_error_ratio", 0.4))

        self._lock = threading.RLock()
        self.struct_version = 0
        self.graph_id = None

        # Real graph (from Autoware), index aligned with the ROS messages.
        self.nodes = []          # dict: id, path, label, children[], leaves[], module
        self.leaves = []         # dict: id, parent, name, path, module
        self.node_level = []
        self.leaf_level = []
        self.leaf_detail = []    # dict: message, hardware_id, values[[k,v]..]
        self.modules = []        # dict: key, label, path, node_id, synthetic
        self.last_status_t = 0.0

        # Synthetic Sensing subtree, keyed by string id.
        self.syn_nodes = {}
        self.syn_leaves = {}
        self.syn_level = {}
        self.syn_detail = {}
        self.syn_muted = {}
        self._build_sensing()

        self.events = deque(maxlen=2000)
        self._first_seen = {}     # problem id -> t when it went non-OK
        self._cleared_at = {}     # problem id -> t when it returned to OK
        self._history = defaultdict(lambda: deque(maxlen=HISTORY_LEN))
        self._prev_level = {}

    # ---------------------------------------------------------------- sensing

    def _build_sensing(self):
        """Build the Sensing subtree from devices.yaml.

        Autoware's diagnostic graph has no /autoware/sensing node, so we make one
        that mirrors the real tree's shape: group -> device -> topic leaf.
        """
        root = {"id": "s:" + SENSING_ROOT, "path": SENSING_ROOT, "label": "Sensing",
                "children": [], "leaves": [], "module": "sensing", "synthetic": True}
        self.syn_nodes[root["id"]] = root

        for group in self.cfg.get("groups", []):
            gpath = "%s/%s" % (SENSING_ROOT, group["key"])
            gid = "s:" + gpath
            gnode = {"id": gid, "path": gpath, "label": group.get("label", group["key"]),
                     "children": [], "leaves": [], "module": "sensing", "synthetic": True}
            self.syn_nodes[gid] = gnode
            root["children"].append(gid)

            for dev in group.get("devices", []):
                slug = re.sub(r"[^a-z0-9]+", "_", dev["name"].lower()).strip("_")
                dpath = "%s/%s" % (gpath, slug)
                did = "s:" + dpath
                dnode = {"id": did, "path": dpath, "label": dev["name"],
                         "children": [], "leaves": [], "module": "sensing",
                         "synthetic": True, "ip": dev.get("ip"),
                         "probe": dev.get("probe", "icmp"),
                         "profile": dev.get("profile")}
                self.syn_nodes[did] = dnode
                gnode["children"].append(did)

                if dev.get("probe", "icmp") != "none" and dev.get("ip"):
                    lid = did + "#reachability"
                    self.syn_leaves[lid] = {
                        "id": lid, "parent": did, "name": "reachability",
                        "path": dpath + "/reachability", "module": "sensing",
                        "synthetic": True, "kind": "probe", "ip": dev.get("ip"),
                        "optional": bool(dev.get("optional")),
                    }
                    dnode["leaves"].append(lid)

                for t in dev.get("topics", []):
                    lid = did + "#" + t["topic"]
                    self.syn_leaves[lid] = {
                        "id": lid, "parent": did, "name": t["topic"],
                        "path": "%s \u2192 %s" % (dpath, t["topic"]),
                        "module": "sensing",
                        "synthetic": True, "kind": "rate", "topic": t["topic"],
                        "ip": dev.get("ip"), "optional": bool(dev.get("optional")),
                        "expect_hz": t.get("expect_hz"),
                        "warn_hz": t.get("warn_hz"), "error_hz": t.get("error_hz"),
                    }
                    dnode["leaves"].append(lid)

        for i in list(self.syn_nodes) + list(self.syn_leaves):
            self.syn_level[i] = STALE

    def _rate_level(self, leaf, hz, seen, warming=False):
        """Grade a measured topic rate. Never published at all -> STALE, not ERROR:
        a topic that was never advertised is a different problem from one that died."""
        if not seen:
            return STALE, "no publisher seen"
        if warming:
            return STALE, "measuring…"
        expect = leaf.get("expect_hz")
        if not expect:
            return (OK, "%.1f Hz" % hz) if hz > 0 else (ERROR, "no messages")
        err = leaf.get("error_hz")
        warn = leaf.get("warn_hz")
        err = float(err) if err is not None else expect * self.error_ratio
        warn = float(warn) if warn is not None else expect * self.warn_ratio
        msg = "%.1f Hz (expected %.1f Hz)" % (hz, expect)
        if hz < err:
            return ERROR, msg
        if hz < warn:
            return WARN, msg
        return OK, msg

    def update_sensing(self, rates, probes):
        """Recompute the synthetic subtree. `rates` maps topic -> (hz, seen, age,
        bytes_per_s); `probes` maps ip -> (reachable, rtt_ms, t)."""
        now = time.time()
        with self._lock:
            for lid, leaf in self.syn_leaves.items():
                probe = probes.get(leaf.get("ip"), (None, None, None))
                if leaf["kind"] == "rate":
                    hz, seen, age, bps, warming = rates.get(
                        leaf["topic"], (0.0, False, None, 0.0, True))
                    lvl, msg = self._rate_level(leaf, hz, seen, warming)
                    values = [["rate", "%.2f Hz" % hz],
                              ["expected", str(leaf.get("expect_hz") or "-")],
                              ["throughput", "%.1f kB/s" % (bps / 1000.0)]]
                    if age is not None:
                        values.append(["last message", "%.1f s ago" % age])
                    detail = {"message": msg, "hardware_id": leaf["topic"], "values": values}
                else:
                    reachable, rtt, t = probe
                    if reachable is None:
                        lvl, msg = STALE, "not probed yet"
                        values = [["address", leaf["ip"]]]
                    elif reachable:
                        lvl, msg = OK, "reachable (%.0f ms)" % (rtt or 0.0)
                        values = [["address", leaf["ip"]], ["rtt", "%.1f ms" % (rtt or 0.0)],
                                  ["last probe", "%.0f s ago" % (now - t)]]
                    else:
                        lvl, msg = ERROR, "unreachable"
                        values = [["address", leaf["ip"]],
                                  ["last probe", "%.0f s ago" % (now - t)]]
                    detail = {"message": msg, "hardware_id": leaf["ip"], "values": values}

                # An optional device that does not answer at its address is
                # simply not fitted - only one lidar profile is on the car at a
                # time. Keep it grey and out of the way. The moment it does
                # answer we grade it for real, because a lidar that responds on
                # its port but publishes nothing is broken, not absent.
                muted = bool(leaf.get("optional")) and probe[0] is not True
                self.syn_muted[lid] = muted
                self.syn_level[lid] = lvl
                self.syn_detail[lid] = detail
                if muted:
                    self._prev_level.pop(lid, None)
                    self._first_seen.pop(lid, None)
                    self._cleared_at.pop(lid, None)
                else:
                    self._track(lid, leaf["path"], leaf["name"], lvl, msg,
                                "sensing", now)

            # Roll device -> group -> root, worst-wins (mirrors an `and` unit).
            # Sorting by descending key length walks deepest-first: every child
            # path is a strict prefix-extension of its parent's.
            for nid in sorted(self.syn_nodes, key=lambda k: -len(k)):
                node = self.syn_nodes[nid]
                kids = node["children"] + node["leaves"]
                live = [k for k in kids if not self.syn_muted.get(k)]
                self.syn_muted[nid] = bool(kids) and not live
                self.syn_level[nid] = self._worst([self.syn_level[k] for k in live])

    @staticmethod
    def _worst(levels):
        """Worst-of, with ERROR outranking STALE: a reporting failure is less
        actionable than a component actively telling you it is broken."""
        if not levels:
            return OK
        rank = {OK: 0, WARN: 1, STALE: 2, ERROR: 3}
        return max(levels, key=lambda l: rank.get(l, 0))

    # ------------------------------------------------------------ real graph

    def set_struct(self, msg):
        """Rebuild from a DiagGraphStruct. Called only when graph id changes."""
        with self._lock:
            nodes, leaves = [], []
            for i, n in enumerate(msg.nodes):
                nodes.append({"id": "n%d" % i, "path": n.path, "label": _short(n.path),
                              "children": [], "leaves": [], "module": None,
                              "synthetic": False})
            for link in msg.links:
                if link.parent < len(nodes) and link.child < len(nodes):
                    nodes[link.parent]["children"].append("n%d" % link.child)
            for i, d in enumerate(msg.diags):
                lid = "d%d" % i
                parent = nodes[d.parent] if d.parent < len(nodes) else None
                leaves.append({"id": lid, "parent": parent["id"] if parent else None,
                               "name": d.name,
                               "path": (parent["path"] + "/" if parent else "") + d.name,
                               "module": None, "synthetic": False})
                if parent:
                    parent["leaves"].append(lid)

            by_id = {n["id"]: n for n in nodes}
            leaf_by_id = {l["id"]: l for l in leaves}

            modules = [{"key": "sensing", "label": MODULE_LABELS["sensing"],
                        "path": SENSING_ROOT, "node_id": "s:" + SENSING_ROOT,
                        "synthetic": True}]
            for n in nodes:
                m = _MODULE_RE.match(n["path"])
                if m:
                    key = m.group(1)
                    modules.append({"key": key, "label": MODULE_LABELS.get(key, key.title()),
                                    "path": n["path"], "node_id": n["id"],
                                    "synthetic": False})
            order = {k: i for i, k in enumerate(MODULE_ORDER)}
            modules.sort(key=lambda m: (order.get(m["key"], 99), m["key"]))

            # Attribute every node/leaf to the first module that reaches it, so a
            # problem in the rail can say which tile to click.
            for mod in modules:
                if mod["synthetic"]:
                    continue
                for nid, lid in self._walk(mod["node_id"], by_id, leaf_by_id):
                    if nid and by_id[nid]["module"] is None:
                        by_id[nid]["module"] = mod["key"]
                    if lid and leaf_by_id[lid]["module"] is None:
                        leaf_by_id[lid]["module"] = mod["key"]

            self.nodes, self.leaves = nodes, leaves
            self._by_id, self._leaf_by_id = by_id, leaf_by_id
            self.node_level = [STALE] * len(nodes)
            self.leaf_level = [STALE] * len(leaves)
            self.leaf_detail = [None] * len(leaves)
            self.modules = modules
            self.graph_id = msg.id
            self.struct_version += 1

    @staticmethod
    def _walk(root_id, by_id, leaf_by_id):
        """DFS over the DAG. Yields (node_id, None) and (None, leaf_id)."""
        seen, stack = set(), [root_id]
        while stack:
            nid = stack.pop()
            if nid in seen or nid not in by_id:
                continue
            seen.add(nid)
            yield nid, None
            node = by_id[nid]
            for lid in node["leaves"]:
                yield None, lid
            stack.extend(node["children"])

    def set_status(self, msg):
        """Apply a DiagGraphStatus. Ignored unless it matches the current struct."""
        now = time.time()
        with self._lock:
            if msg.id != self.graph_id or not self.nodes:
                return False
            if len(msg.nodes) != len(self.nodes) or len(msg.diags) != len(self.leaves):
                return False
            for i, n in enumerate(msg.nodes):
                self.node_level[i] = _lvl(n.level)
            for i, d in enumerate(msg.diags):
                lvl = _lvl(d.level)
                self.leaf_level[i] = lvl
                self.leaf_detail[i] = {
                    "message": d.message, "hardware_id": d.hardware_id,
                    "values": [[kv.key, kv.value] for kv in d.values],
                }
                leaf = self.leaves[i]
                self._track(leaf["id"], leaf["path"], leaf["name"], lvl,
                            d.message, leaf["module"], now)
            self.last_status_t = now
            return True

    # ---------------------------------------------------------------- events

    def _track(self, item_id, path, name, level, message, module, now):
        """Record transitions, first-seen time and latch window for one item."""
        prev = self._prev_level.get(item_id)
        if prev == level:
            return
        self._prev_level[item_id] = level
        self._history[item_id].append([round(now, 2), level])
        if prev is not None:
            self.events.appendleft({
                "t": now, "id": item_id, "path": path, "name": name,
                "module": module, "from": prev, "to": level, "message": message,
            })
        if level == OK:
            if prev not in (None, OK):
                self._cleared_at[item_id] = now
        else:
            self._cleared_at.pop(item_id, None)
            self._first_seen.setdefault(item_id, now)

    # ----------------------------------------------------------- serialising

    def struct_json(self):
        with self._lock:
            nodes = list(self.syn_nodes.values()) + self.nodes
            leaves = list(self.syn_leaves.values()) + self.leaves
            return {
                "version": self.struct_version,
                "graph_id": self.graph_id,
                "modules": self.modules or [{
                    "key": "sensing", "label": "Sensing", "path": SENSING_ROOT,
                    "node_id": "s:" + SENSING_ROOT, "synthetic": True}],
                "nodes": nodes,
                "leaves": leaves,
            }

    def _level_of(self, item_id):
        if item_id.startswith("s:"):
            return self.syn_level.get(item_id, STALE)
        idx = int(item_id[1:])
        if item_id[0] == "n":
            return self.node_level[idx] if idx < len(self.node_level) else STALE
        return self.leaf_level[idx] if idx < len(self.leaf_level) else STALE

    def detail_of(self, item_id):
        with self._lock:
            if item_id.startswith("s:"):
                return self.syn_detail.get(item_id)
            if item_id.startswith("d"):
                idx = int(item_id[1:])
                if idx < len(self.leaf_detail):
                    return self.leaf_detail[idx]
            return None

    def history_of(self, item_id):
        with self._lock:
            return list(self._history.get(item_id, ()))

    def problems(self, now=None):
        """Every non-OK leaf, plus leaves that cleared within the latch window.

        Autoware diagnostics run at ~10 Hz and real faults routinely flash for a
        couple of hundred milliseconds. Without the latch you simply never see them.
        """
        now = now or time.time()
        out = []
        with self._lock:
            items = [(l["id"], l, self.leaf_level[i], self.leaf_detail[i])
                     for i, l in enumerate(self.leaves)]
            items += [(lid, l, self.syn_level.get(lid, STALE), self.syn_detail.get(lid))
                      for lid, l in self.syn_leaves.items()]
            for lid, leaf, lvl, detail in items:
                if lid not in self._prev_level or self.syn_muted.get(lid):
                    continue  # never evaluated, or hardware that is not fitted
                cleared = self._cleared_at.get(lid)
                if lvl == OK and not (cleared and now - cleared < LATCH_S):
                    continue
                parent = (self.syn_nodes.get(leaf["parent"])
                          or getattr(self, "_by_id", {}).get(leaf["parent"]) or {})
                out.append({
                    "id": lid, "path": leaf["path"], "name": leaf["name"],
                    "parent": parent.get("label"),
                    "module": leaf["module"], "level": lvl,
                    "message": (detail or {}).get("message", ""),
                    "since": self._first_seen.get(lid),
                    "cleared_at": cleared,
                })
        rank = {ERROR: 0, STALE: 1, WARN: 2, OK: 3}
        out.sort(key=lambda p: (p["cleared_at"] is not None, rank.get(p["level"], 9),
                                p["path"]))
        return out

    def module_summary(self, now=None):
        now = now or time.time()
        with self._lock:
            graph_stale = (not self.nodes) or (now - self.last_status_t > self.stale_after)
            out = []
            for mod in self.modules or self.struct_json()["modules"]:
                if mod["synthetic"]:
                    lvl = self.syn_level.get(mod["node_id"], STALE)
                    counts = self._count_syn()
                    age = 0.0
                else:
                    lvl = STALE if graph_stale else self._level_of(mod["node_id"])
                    counts = self._count_real(mod["node_id"], graph_stale)
                    age = now - self.last_status_t if self.last_status_t else None
                out.append({**mod, "level": lvl, "warn": counts[WARN],
                            "error": counts[ERROR], "stale": counts[STALE], "age": age})
            return out

    def _count_syn(self):
        c = defaultdict(int)
        for lid in self.syn_leaves:
            if self.syn_muted.get(lid):
                continue
            c[self.syn_level.get(lid, STALE)] += 1
        return c

    def _count_real(self, root_id, graph_stale):
        c = defaultdict(int)
        for _, lid in self._walk(root_id, self._by_id, self._leaf_by_id):
            if lid is None:
                continue
            lvl = STALE if graph_stale else self.leaf_level[int(lid[1:])]
            c[lvl] += 1
        return c

    def stream_json(self):
        now = time.time()
        with self._lock:
            graph_stale = (not self.nodes) or (now - self.last_status_t > self.stale_after)
            return {
                "version": self.struct_version,
                "t": now,
                "graph_ok": bool(self.nodes) and not graph_stale,
                "graph_age": (now - self.last_status_t) if self.last_status_t else None,
                "node_levels": list(self.node_level),
                "leaf_levels": list(self.leaf_level),
                "syn_levels": dict(self.syn_level),
                "graph_stale": graph_stale,
                "modules": self.module_summary(now),
                "problems": self.problems(now),
                "events": list(self.events)[:60],
            }
