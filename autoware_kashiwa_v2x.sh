#!/bin/bash
# Launch Autoware on the Pixkit 3.0 with V2X reported vehicles fed into perception.
#
# Usage:  ./autoware_kashiwa_v2x.sh [map_dir] [launch_arg:=value ...]
#
# This starts Autoware only. The V2X stack is a separate workspace,
# https://github.com/ehsan-javanmardi/racing_kart_v2x, launched alongside in another
# terminal:
#
#   source /opt/ros/humble/setup.bash
#   source ~/workspace/pix_autoware/install/setup.bash
#   source ~/workspace/racing_kart_v2x/install/setup.bash
#   export V2X_TLS_DIR=~/workspace/racing_kart_v2x/certs/d10
#   ros2 launch v2x_autoware_bridge v2x_autoware.launch.xml \
#     vehicle_id:=d10 vehicle_ids:=d8,d10,d11
#
# Without use_v2x_objects the tracker never subscribes to the V2X topic and the objects
# are dropped with no error at all, which is the whole reason this script exists.
# See docs/V2X.md.
#
# Default map dir: ./autoware_map  (override with $1 or $AUTOWARE_MAP_PATH).
set -e

AUTOWARE_WS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Map directory. autoware_map/ sits next to this script and holds the Kashiwanoha map the
# workspace ships with. Change this line to point somewhere else permanently, or pass a
# different path as the first argument for one run.
DEFAULT_MAP_PATH="$AUTOWARE_WS/autoware_map"
# The previous layout kept the maps one level up, so that location is still accepted.
if [ ! -d "$DEFAULT_MAP_PATH" ] && [ -d "$AUTOWARE_WS/../autoware_map" ]; then
    DEFAULT_MAP_PATH="$(cd "$AUTOWARE_WS/.." && pwd)/autoware_map"
fi
# Anything containing ":=" is a launch argument and is forwarded to ros2 launch, so the map
# directory can be omitted.
if [[ "${1:-}" == *":="* ]]; then
    MAP_ARG=""
    EXTRA_ARGS=("$@")
else
    MAP_ARG="${1:-}"
    EXTRA_ARGS=("${@:2}")
fi
MAP_PATH="${MAP_ARG:-${AUTOWARE_MAP_PATH:-$DEFAULT_MAP_PATH}}"

if [ ! -f "$AUTOWARE_WS/install/setup.bash" ]; then
    echo "error: $AUTOWARE_WS/install/setup.bash not found - build first:" >&2
    echo "  cd $AUTOWARE_WS && colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release" >&2
    exit 1
fi

if [ ! -d "$MAP_PATH" ]; then
    echo "error: map directory not found: $MAP_PATH" >&2
    exit 1
fi

# Autoware defaults pointcloud_map_file to "pointcloud_map.pcd"; a map may ship as
# something else, so detect whatever .pcd is actually present.
PCD_FILE="$(cd "$MAP_PATH" && ls -1 *.pcd 2>/dev/null | head -n1)"
if [ -z "$PCD_FILE" ]; then
    echo "error: no .pcd point cloud map found in $MAP_PATH" >&2
    exit 1
fi

# Whichever .osm sorts first. With several in one directory that choice is not obvious, so
# it is echoed below; pass lanelet2_map_file:=... to be explicit.
LANELET_FILE="$(cd "$MAP_PATH" && ls -1 *.osm 2>/dev/null | head -n1)"
if [ -z "$LANELET_FILE" ]; then
    echo "error: no .osm lanelet2 map found in $MAP_PATH" >&2
    exit 1
fi

if [ ! -f "$MAP_PATH/map_projector_info.yaml" ]; then
    echo "warning: $MAP_PATH/map_projector_info.yaml missing - Autoware will fall back" >&2
    echo "         to deriving projection from the lanelet2 map (deprecated)." >&2
fi

echo "workspace : $AUTOWARE_WS"
echo "map       : $MAP_PATH"
echo "pointcloud: $PCD_FILE"
echo "lanelet2  : $LANELET_FILE"
echo "lidar     : Ouster OS-1-128"
echo "v2x       : enabled (use_v2x_objects:=true)"

# --- DDS environment -------------------------------------------------------------
# Pin this explicitly rather than relying on ~/.bashrc: that file is only sourced by
# interactive shells, so launching from a desktop icon or a non-interactive script
# would otherwise fall back to the default RMW (fastrtps) while CLI shells use
# cyclonedds. Two different middlewares cannot see each other, which shows up as
# service calls timing out while `ros2 topic list` looks fine.
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"
# ROS_LOCALHOST_ONLY is intentionally not set - see ~/.config/environment.d/10-ros-dds.conf
unset ROS_LOCALHOST_ONLY

echo "rmw       : $RMW_IMPLEMENTATION"

source "$AUTOWARE_WS/install/setup.bash"

# EXTRA_ARGS comes last so that repeating one of these on the command line overrides it:
# ros2 launch takes the final value when an argument is given more than once.
ros2 launch autoware_launch autoware.launch.xml \
    vehicle_model:=pixkit \
    sensor_model:=pixkit_sensor_kit \
    map_path:="$MAP_PATH" \
    pointcloud_map_file:="$PCD_FILE" \
    lanelet2_map_file:="$LANELET_FILE" \
    lidar_profile:=os1_128 \
    use_v2x_objects:=true \
    log_level:=debug \
    "${EXTRA_ARGS[@]}"
