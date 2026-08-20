#!/bin/bash
# Launch Autoware on the Pixkit 3.0.
#
# Adapted from Pixkit_Autoware/autoware_velodyne_kashiwa.sh: the upstream copy
# hardcoded /home/autoware/pixkit_autoware_0.45.1, which does not exist here.
#
# Usage:  ./autoware_velodyne_kashiwa.sh [map_dir] [launch_arg:=value ...]
# Default map dir: ./autoware_map  (override with $1 or $AUTOWARE_MAP_PATH).
# See docs/MAPS.md for what a map directory has to contain.
set -e

AUTOWARE_WS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The maps live inside the workspace. The previous layout kept them one level up,
# so that location is still accepted as a fallback.
DEFAULT_MAP_PATH="$AUTOWARE_WS/autoware_map"
if [ ! -d "$DEFAULT_MAP_PATH" ] && [ -d "$AUTOWARE_WS/../autoware_map" ]; then
    DEFAULT_MAP_PATH="$(cd "$AUTOWARE_WS/.." && pwd)/autoware_map"
fi
# Anything containing ":=" is a launch argument and is forwarded to ros2 launch, so the map
# directory can be omitted:  ./autoware_velodyne_kashiwa.sh lidar_profile:=os2_32
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

# Autoware defaults pointcloud_map_file to "pointcloud_map.pcd"; this map ships as
# kashiwanoha_binary_MGRS_v2.pcd, so detect whatever .pcd is actually present.
PCD_FILE="$(cd "$MAP_PATH" && ls -1 *.pcd 2>/dev/null | head -n1)"
if [ -z "$PCD_FILE" ]; then
    echo "error: no .pcd point cloud map found in $MAP_PATH" >&2
    exit 1
fi

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

ros2 launch autoware_launch autoware.launch.xml \
    vehicle_model:=pixkit \
    sensor_model:=velodyne_pixkit_sensor_kit \
    map_path:="$MAP_PATH" \
    pointcloud_map_file:="$PCD_FILE" \
    lanelet2_map_file:="$LANELET_FILE" \
    log_level:=debug \
    "${EXTRA_ARGS[@]}"
