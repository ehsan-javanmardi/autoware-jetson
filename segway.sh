#!/usr/bin/env bash
#
# The Segway platform: everything that stays up.
#
#   ./segway.sh
#
# Sensors, the chassis, and the web UI. Autoware is NOT started here - start it from
# the web UI's Autoware tab, or from a terminal, and stop it again without any of this
# being disturbed. That is the point of the split: the hardware layer and the operator
# interface outlive any number of Autoware runs.
#
#   web UI          http://<this machine>:8842
#   Foxglove        ws://<this machine>:8765
#
# DO NOT run this alongside ./autoware_all.sh or ./autoware_kashiwa.sh. Those start
# their own sensor drivers and their own vehicle interface, and two vehicle interfaces
# cannot share the chassis serial port: the second one opens it, reads 0xffff, and
# degrades the link for the first. See docs/RUNNING.md.

set -uo pipefail

cd "$(dirname "$(readlink -f "$0")")"

LOG_DIR="${LOG_DIR:-$HOME/.segway/logs}"
mkdir -p "$LOG_DIR"

# allow_control=true so the platform can be driven from the Remote drive tab. The
# chassis E-stop and the RC enable switch are the real safeguards; see docs/RUNNING.md.
ALLOW_CONTROL="${ALLOW_CONTROL:-true}"
WITH_SENSORS="${WITH_SENSORS:-true}"
WITH_FOXGLOVE="${WITH_FOXGLOVE:-true}"

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

# ---------------------------------------------------------------- conflict check
#
# Catching this here is worth more than documenting it: a second vehicle interface
# does not fail loudly, it quietly makes the chassis unreadable for both.
if pgrep -f "lib/segway_vehicle_interface/segway_vehicle_interfac[e]" >/dev/null 2>&1; then
    die "a vehicle interface is already running.
   Something else already owns the chassis - most likely ./autoware_all.sh or
   ./autoware_kashiwa.sh. Stop it before starting the platform."
fi
if ss -tln 2>/dev/null | grep -qE ':8842|:8843'; then
    die "port 8842 or 8843 is already in use; the web UI is probably already running."
fi

PIDS=()
start() {  # start <name> <logfile> <command...>
    local name=$1 log=$2; shift 2
    "$@" > "$LOG_DIR/$log" 2>&1 &
    PIDS+=($!)
    printf '  starting %-22s -> %s\n' "$name" "$LOG_DIR/$log"
}

shutdown() {
    echo
    say "stopping the platform"
    # Reverse order: the vehicle interface last, so its own shutdown path (zero the
    # command, disable the motors) runs while nothing is still publishing to it.
    for ((i=${#PIDS[@]}-1; i>=0; i--)); do
        kill "${PIDS[i]}" 2>/dev/null
    done
    for ((i=0; i<40; i++)); do
        pgrep -P $$ >/dev/null 2>&1 || break
        sleep 0.1
    done
    pkill -P $$ 2>/dev/null
    ok "stopped"
    exit 0
}
trap shutdown INT TERM

say "Segway platform"

if [ "$WITH_SENSORS" = "true" ]; then
    # One launch file, because the namespace has to be right: it pushes /sensing so
    # the drivers land where Autoware's own sensing chain reads them.
    start "sensor drivers"   sensors.log \
        ros2 launch segway_sensor_kit_launch platform_sensors.launch.xml
else
    warn "sensors skipped (WITH_SENSORS=false)"
fi

start "vehicle interface" vehicle.log \
    ros2 launch segway_vehicle_interface segway_vehicle_interface.launch.xml \
        allow_control:="$ALLOW_CONTROL"

start "web UI"      web_ui.log      ros2 launch segway_web_ui web_ui.launch.xml
start "web control" web_control.log ros2 launch segway_web_control web_control.launch.xml

if [ "$WITH_FOXGLOVE" = "true" ]; then
    start "foxglove bridge" foxglove.log \
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 \
            topic_whitelist:="$(./foxglove/build_whitelist.py)"
fi

sleep 6
echo
say "up"
IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[0-9.]+' | head -1)
IP=${IP:-localhost}
printf '  web UI    http://%s:8842\n' "$IP"
[ "$WITH_FOXGLOVE" = "true" ] && printf '  foxglove  ws://%s:8765\n' "$IP"
printf '  logs      %s\n' "$LOG_DIR"
echo
if grep -q "not replying" "$LOG_DIR/vehicle.log" 2>/dev/null; then
    warn "the chassis is not replying - check it is powered on and the controller is on"
elif grep -q "connected:" "$LOG_DIR/vehicle.log" 2>/dev/null; then
    ok "$(grep -oP 'connected: \K.*' "$LOG_DIR/vehicle.log" | tail -1)"
fi
[ "$ALLOW_CONTROL" = "true" ] && warn "remote drive is available: this platform CAN move the robot"
echo
say "Ctrl-C to stop. Start Autoware from the web UI's Autoware tab."

wait
