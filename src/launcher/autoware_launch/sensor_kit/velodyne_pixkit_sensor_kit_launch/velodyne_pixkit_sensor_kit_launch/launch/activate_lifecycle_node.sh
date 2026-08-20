#!/bin/bash
# Bring a ROS 2 lifecycle node up: wait until it registers, then configure -> activate.
#
# Replaces the upstream ouster_ros approach of two `ros2 lifecycle set` calls behind
# fixed `sleep 3` / `sleep 5` (self-labelled "HACK" in os_sensor_*.launch.xml). Those
# lose the race whenever the machine is busy -- launching Autoware starts ~80 nodes and
# builds TensorRT engines -- and fail with "Node not found", leaving the driver in
# `unconfigured` state with no publishers.
#
# Usage: activate_lifecycle_node.sh <fully/qualified/node/name> [max_wait_seconds]
set -u

NODE="${1:?usage: $0 <node> [max_wait_seconds]}"
MAX_WAIT="${2:-180}"

# --no-daemon on every call: the ros2 CLI daemon caches the node graph and, once it dies
# (seen as "RuntimeError:!rclpy.ok()"), every query returns empty instead of failing. This
# loop would then wait out its whole timeout while the node sat there registered and healthy.
state() { ros2 lifecycle get --no-daemon "$NODE" 2>/dev/null | cut -d' ' -f1; }

echo "[lifecycle] waiting for $NODE (up to ${MAX_WAIT}s)"
deadline=$((SECONDS + MAX_WAIT))
until [ -n "$(state)" ]; do
    if [ $SECONDS -ge $deadline ]; then
        echo "[lifecycle] ERROR: $NODE never registered within ${MAX_WAIT}s" >&2
        exit 1
    fi
    sleep 2
done
echo "[lifecycle] $NODE registered, state=$(state)"

for attempt in 1 2 3 4 5; do
    st="$(state)"
    [ "$st" = active ] && break
    if [ "$st" = unconfigured ]; then
        echo "[lifecycle] configure (attempt $attempt)"
        ros2 lifecycle set --no-daemon "$NODE" configure || true
        sleep 2
    fi
    st="$(state)"
    if [ "$st" = inactive ]; then
        echo "[lifecycle] activate (attempt $attempt)"
        ros2 lifecycle set --no-daemon "$NODE" activate || true
        sleep 2
    fi
    st="$(state)"
    echo "[lifecycle] state=$st after attempt $attempt"
    [ "$st" = active ] && break
    sleep 3
done

final="$(state)"
if [ "$final" = active ]; then
    echo "[lifecycle] $NODE is ACTIVE"
else
    echo "[lifecycle] ERROR: $NODE ended in state '$final' (expected active)" >&2
    exit 1
fi
