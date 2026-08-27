#!/usr/bin/env bash
# Autoware on the Pixkit with V2X reported vehicles fed into the perception pipeline.
#
# Usage:  ./autoware_kashiwa_v2x.sh [map_dir] [launch_arg:=value ...]
#
# This starts Autoware only. The V2X stack itself is a separate workspace,
# https://github.com/ehsan-javanmardi/racing_kart_v2x, and has to be launched alongside
# in another terminal:
#
#   source /opt/ros/humble/setup.bash
#   source ~/workspace/pix_autoware/install/setup.bash
#   source ~/workspace/racing_kart_v2x/install/setup.bash
#   export V2X_TLS_DIR=~/workspace/racing_kart_v2x/certs/d10
#   ros2 launch v2x_autoware_bridge v2x_autoware.launch.xml \
#     vehicle_id:=d10 vehicle_ids:=d8,d10,d11
#
# Without use_v2x_objects the tracker never subscribes to the V2X topic and the objects
# are dropped with no error, which is the whole reason this script exists. See docs/V2X.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Map directory. autoware_map/ sits next to this script and holds the Kashiwanoha map the
# workspace ships with. Change this line to point somewhere else permanently, or pass a
# different path as the first argument for one run.
DEFAULT_MAP_DIR="$HERE/autoware_map"

DEFAULTS=(lidar_profile:=os1_128 use_v2x_objects:=true)

# A first argument without ":=" is a map directory; anything else is a launch argument.
# The defaults go before the caller's arguments so that repeating one of them overrides it.
if [ $# -gt 0 ] && [[ "$1" != *":="* ]]; then
    MAP_DIR="$1"
    shift
else
    MAP_DIR="$DEFAULT_MAP_DIR"
fi

exec "$HERE/autoware_velodyne_kashiwa.sh" "$MAP_DIR" "${DEFAULTS[@]}" "$@"
