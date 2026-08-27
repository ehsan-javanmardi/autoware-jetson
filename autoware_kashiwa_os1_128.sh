#!/usr/bin/env bash
# Autoware on the Pixkit with the Ouster OS-1-128 as the only lidar.
#
# Usage:  ./autoware_kashiwa_os1_128.sh [map_dir] [launch_arg:=value ...]
#
# A thin wrapper over autoware_velodyne_kashiwa.sh, which does the real work: finding the
# map files, pinning the RMW, and sourcing the workspace. Everything here is one launch
# argument, so there is only ever one launcher to keep correct.
#
# os1_128 is already that launcher's default, so this script exists to make the choice
# visible rather than to change it. The OS-2-32 equivalent is
# lidar_profile:=os2_32; see docs/SENSORS.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Map directory. autoware_map/ sits next to this script and holds the Kashiwanoha map the
# workspace ships with. Change this line to point somewhere else permanently, or pass a
# different path as the first argument for one run.
DEFAULT_MAP_DIR="$HERE/autoware_map"

DEFAULTS=(lidar_profile:=os1_128)

# A first argument without ":=" is a map directory; anything else is a launch argument.
# The defaults go before the caller's arguments so that repeating one of them overrides it.
if [ $# -gt 0 ] && [[ "$1" != *":="* ]]; then
    MAP_DIR="$1"
    shift
else
    MAP_DIR="$DEFAULT_MAP_DIR"
fi

exec "$HERE/autoware_velodyne_kashiwa.sh" "$MAP_DIR" "${DEFAULTS[@]}" "$@"
