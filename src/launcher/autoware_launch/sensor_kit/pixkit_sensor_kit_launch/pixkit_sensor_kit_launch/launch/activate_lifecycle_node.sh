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

# Everything here goes through the node's own lifecycle services rather than `ros2 lifecycle`,
# which enumerates the node graph first. That enumeration is unreliable in a graph this size:
# the ros2 CLI daemon caches the graph and answers with silence once its context dies (seen as
# "RuntimeError:!rclpy.ok()"), and --no-daemon reports "Node not found" often enough under load
# to matter. Either way the script would wait out its timeout while the driver sat registered
# and healthy in unconfigured, publishing nothing. Service calls find the node every time.
state() {
    ros2 service call "$NODE/get_state" lifecycle_msgs/srv/GetState 2>/dev/null |
        grep -oP "label='\K[^']+" | tail -1
}

# 1 = configure, 3 = activate (lifecycle_msgs/msg/Transition)
transition() {
    ros2 service call "$NODE/change_state" lifecycle_msgs/srv/ChangeState \
        "{transition: {id: $1}}" 2>/dev/null | grep -q "success=True"
}

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
        transition 1 || true
        sleep 2
    fi
    st="$(state)"
    if [ "$st" = inactive ]; then
        echo "[lifecycle] activate (attempt $attempt)"
        transition 3 || true
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
