#!/usr/bin/env bash
# Launch the Autoware health dashboard (read-only).
#
#   ./run.sh                      # bind 0.0.0.0:8842
#   ./run.sh --port 9000          # different port
#   ./run.sh --host 127.0.0.1     # localhost only
#   ./run.sh --no-probe           # skip ping/TCP reachability checks
#
# AUTOWARE_WS overrides the workspace whose install/ is sourced.
set -eo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# health_ui/ lives inside the Autoware workspace, so derive it rather than
# assuming a path under $HOME.
AUTOWARE_WS="${AUTOWARE_WS:-$(cd "$HERE/.." && pwd)}"

# --- DDS environment -------------------------------------------------------------
# Pinned here for the same reason autoware_kashiwa.sh pins it: ~/.bashrc is only
# sourced by interactive shells, so a systemd unit or a desktop launcher would
# otherwise fall back to the default RMW (fastrtps) while Autoware runs on
# cyclonedds. The two middlewares cannot see each other, and the failure is
# silent - the dashboard would sit at "waiting for Autoware" forever with a
# perfectly healthy stack running next to it.
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"
if [ -z "${CYCLONEDDS_URI:-}" ] && [ -f "$HOME/cyclonedds.xml" ]; then
  export CYCLONEDDS_URI="file://$HOME/cyclonedds.xml"
fi
unset ROS_LOCALHOST_ONLY

# shellcheck disable=SC1091
source /opt/ros/humble/setup.bash
if [ -f "$AUTOWARE_WS/install/setup.bash" ]; then
  # shellcheck disable=SC1091
  source "$AUTOWARE_WS/install/setup.bash"
else
  echo "warning: $AUTOWARE_WS/install/setup.bash not found;" \
       "autoware_adapi_v1_msgs will be missing" >&2
fi

cd "$HERE"
echo "rmw       : $RMW_IMPLEMENTATION"
exec python3 -m autoware_health_ui "$@"
