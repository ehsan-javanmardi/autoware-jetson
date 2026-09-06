#!/bin/bash
# Launch Autoware on the Pixkit 3.0, with whatever the launch defaults are.
#
# Usage:  ./autoware_kashiwa.sh [map_dir] [launch_arg:=value ...]
#
# The general purpose launcher. For the two combinations used most often there are
# dedicated scripts that need no arguments:
#
#   ./autoware_kashiwa_os1_128.sh   Ouster OS-1-128 as the only lidar
#   ./autoware_kashiwa_v2x.sh       the same, plus V2X reported vehicles
#
# Use this one for anything else, for example:
#
#   ./autoware_kashiwa.sh lidar_profile:=os2_32
#   ./autoware_kashiwa.sh pose_source:=gnss
#   ./autoware_kashiwa.sh launch_perception:=false
#
# Map: ./autoware_map, holding pointcloud_map.pcd and lanelet2_map.osm under those exact
# names. Pass a different directory as the first argument. Nothing is auto-detected.
# See docs/MAPS.md for what a map directory has to contain.
#
# Adapted from Pixkit_Autoware/autoware_kashiwa.sh, which hardcoded
# /home/autoware/pixkit_autoware_0.45.1 and was named after a lidar this vehicle does not
# carry.
set -e

AUTOWARE_WS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Map ---------------------------------------------------------------------------
# The map is ./autoware_map in this repository, holding exactly these two files under
# exactly these names. Nothing is searched for: no globbing, no fallback to a parent
# directory, no picking "whichever .osm sorts first". That search is what previously made
# the script load a different map from the one it appeared to, because ls order decided it.
#
# To drive a different road network, copy it over lanelet2_map.osm. To use a map that lives
# somewhere else entirely, pass its directory as the first argument; it has to contain the
# same two filenames.
MAP_DIR="$AUTOWARE_WS/autoware_map"
PCD_FILE="pointcloud_map.pcd"
LANELET_FILE="lanelet2_map.osm"

# A first argument without ":=" is a map directory; everything else is a launch argument
# forwarded to ros2 launch.
if [ $# -gt 0 ] && [[ "$1" != *":="* ]]; then
    MAP_DIR="$1"
    shift
fi
EXTRA_ARGS=("$@")

if [ ! -f "$AUTOWARE_WS/install/setup.bash" ]; then
    echo "error: $AUTOWARE_WS/install/setup.bash not found - build first:" >&2
    echo "  cd $AUTOWARE_WS && colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release" >&2
    exit 1
fi

if [ ! -d "$MAP_DIR" ]; then
    echo "error: map directory not found: $MAP_DIR" >&2
    exit 1
fi
for f in "$PCD_FILE" "$LANELET_FILE"; do
    if [ ! -f "$MAP_DIR/$f" ]; then
        echo "error: $MAP_DIR/$f not found." >&2
        echo "       A map directory must contain $PCD_FILE and $LANELET_FILE under those" >&2
        echo "       exact names. See docs/MAPS.md." >&2
        exit 1
    fi
done

if [ ! -f "$MAP_DIR/map_projector_info.yaml" ]; then
    echo "warning: $MAP_DIR/map_projector_info.yaml missing - Autoware will fall back" >&2
    echo "         to deriving projection from the lanelet2 map (deprecated)." >&2
fi

echo "workspace : $AUTOWARE_WS"
echo "map       : $MAP_DIR"
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

# EXTRA_ARGS comes last so that repeating one of these on the command line overrides it:
# ros2 launch takes the final value when an argument is given more than once.
ros2 launch autoware_launch autoware.launch.xml \
    vehicle_model:=segway \
    sensor_model:=pixkit_sensor_kit \
    map_path:="$MAP_DIR" \
    pointcloud_map_file:="$PCD_FILE" \
    lanelet2_map_file:="$LANELET_FILE" \
    log_level:=debug \
    "${EXTRA_ARGS[@]}"
