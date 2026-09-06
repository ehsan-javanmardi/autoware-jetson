#!/usr/bin/env bash
#
# Everything, in one process tree: Autoware, its sensor drivers, the vehicle
# interface, the web UI and Foxglove.
#
#   ./autoware_all.sh [map_dir] [args...]
#
# For a single self-contained run where Autoware is the point. Stopping this stops
# the sensors and the chassis with it.
#
# ┌─────────────────────────────────────────────────────────────────────────────┐
# │ DO NOT run this while ./segway.sh is running.                               │
# │                                                                             │
# │ Both start a vehicle interface, and two cannot share the chassis serial      │
# │ port. The vendor SDK does not report the conflict: the second opener gets a  │
# │ success return, then reads 0xffff for everything, while degrading the link   │
# │ for the first. Neither process looks broken; the chassis just stops making   │
# │ sense.                                                                       │
# └─────────────────────────────────────────────────────────────────────────────┘
#
# If you want Autoware to come and go while the sensors and the web UI stay up,
# use ./segway.sh and start Autoware from its Autoware tab instead. That is the
# better arrangement for everyday work.

set -uo pipefail

cd "$(dirname "$(readlink -f "$0")")"

LOG_DIR="${LOG_DIR:-$HOME/.segway/logs}"
mkdir -p "$LOG_DIR"
WITH_FOXGLOVE="${WITH_FOXGLOVE:-true}"
WITH_WEB_UI="${WITH_WEB_UI:-true}"

c_h=$'\033[1;36m'; c_ok=$'\033[32m'; c_w=$'\033[33m'; c_e=$'\033[31m'; c_0=$'\033[0m'
say()  { printf '%s%s%s\n' "$c_h" "$1" "$c_0"; }
ok()   { printf '  %sok%s   %s\n' "$c_ok" "$c_0" "$1"; }
warn() { printf '  %swarn%s %s\n' "$c_w" "$c_0" "$1"; }
die()  { printf '%serror%s %s\n' "$c_e" "$c_0" "$1" >&2; exit 1; }

[ -f install/setup.bash ] || die "install/setup.bash missing - build the workspace first"
set +u
source /opt/ros/humble/setup.bash
source install/setup.bash
[ -f "$HOME/.ichimill.env" ] && source "$HOME/.ichimill.env"
set -u

if pgrep -f "lib/segway_vehicle_interface/segway_vehicle_interfac[e]" >/dev/null 2>&1; then
    die "a vehicle interface is already running - ./segway.sh is probably up.
   Stop it first, or start Autoware from the web UI instead of running this."
fi

PIDS=()
start() {
    local name=$1 log=$2; shift 2
    "$@" > "$LOG_DIR/$log" 2>&1 &
    PIDS+=($!)
    printf '  starting %-22s -> %s\n' "$name" "$LOG_DIR/$log"
}

shutdown() {
    echo; say "stopping everything"
    for ((i=${#PIDS[@]}-1; i>=0; i--)); do kill "${PIDS[i]}" 2>/dev/null; done
    sleep 2
    pkill -P $$ 2>/dev/null
    ok "stopped"; exit 0
}
trap shutdown INT TERM

say "Autoware, all in one"

if [ "$WITH_WEB_UI" = "true" ]; then
    if ss -tln 2>/dev/null | grep -qE ':8842|:8843'; then
        warn "8842/8843 already in use; not starting the web UI again"
    else
        start "web UI"      web_ui.log      ros2 launch segway_web_ui web_ui.launch.xml
        start "web control" web_control.log ros2 launch segway_web_control web_control.launch.xml
    fi
fi

if [ "$WITH_FOXGLOVE" = "true" ]; then
    start "foxglove bridge" foxglove.log \
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 \
            topic_whitelist:="$(./foxglove/build_whitelist.py)"
fi

IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[0-9.]+' | head -1)
IP=${IP:-localhost}
echo
printf '  web UI    http://%s:8842\n' "$IP"
printf '  foxglove  ws://%s:8765\n' "$IP"
printf '  logs      %s\n' "$LOG_DIR"
echo
warn "Autoware brings up the vehicle interface able to drive"
say "starting Autoware in the foreground; Ctrl-C stops everything"
echo

# Foreground, so Autoware's own output is what fills the terminal and Ctrl-C
# reaches it directly.
./autoware_kashiwa.sh "$@"
shutdown
