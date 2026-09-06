#!/usr/bin/env python3
"""Turn foxglove/topics.yaml into a topic_whitelist for foxglove_bridge.

The bridge takes a list of anchored regexes and reads them once at startup. The
web UI edits topics.yaml, so this is the one place that translates between them.

    ./build_whitelist.py                  # enabled groups, as a ros2 launch arg
    ./build_whitelist.py --groups core,map,planning
    ./build_whitelist.py --all
"""
from __future__ import annotations
import argparse, pathlib, re, sys, yaml

HERE = pathlib.Path(__file__).resolve().parent


def load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text())


def select(cfg: dict, groups: set[str] | None, want_all: bool) -> list[str]:
    out: list[str] = []
    for g in cfg["groups"]:
        if want_all:
            pass
        elif groups is not None:
            if g["key"] not in groups and not g.get("always"):
                continue
        elif not g.get("default_enabled", True) and not g.get("always"):
            continue
        out.extend(g["topics"])
    # A regex like /sensing/camera/.* is already a pattern; a plain topic is not,
    # and an unescaped '.' in it would match any character.
    return [t if ".*" in t or "[" in t else re.escape(t) for t in out]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=pathlib.Path, default=HERE / "topics.yaml")
    ap.add_argument("--groups", help="comma-separated group keys")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--format", choices=("launch", "lines"), default="launch")
    a = ap.parse_args()

    cfg = load(a.config)
    keys = {g["key"] for g in cfg["groups"]}
    chosen = set(a.groups.split(",")) if a.groups else None
    if chosen and (bad := chosen - keys):
        print(f"unknown group(s): {', '.join(sorted(bad))}\nknown: {', '.join(sorted(keys))}",
              file=sys.stderr)
        return 2

    topics = select(cfg, chosen, a.all)
    if a.format == "lines":
        print("\n".join(topics))
    else:
        print("[" + ", ".join(topics) + "]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
