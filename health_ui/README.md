# Autoware Health

A read-only web dashboard for the Pixkit Autoware stack: which module is
unhealthy, why, and whether every sensor is reachable and publishing at rate.

It is **read-only by construction**: it creates no publishers and no service
clients, so it cannot command the vehicle. It subscribes, pings, and serves a
web page — nothing else. It lives inside this workspace and sources
`install/setup.bash` for the message definitions.

```
┌──────────────────────────── Autoware ROS 2 graph ─────────────────────────────┐
│ /api/system/diagnostics/struct   the module tree      (latched)               │
│ /api/system/diagnostics/status   live levels + text   (~10 Hz, best effort)   │
│ /api/operation_mode/state, /api/fail_safe/mrm_state, …  header bar            │
│ sensor + vehicle topics          sampled for rate     (raw, not deserialised) │
└───────────────────────────────────┬───────────────────────────────────────────┘
                                    │  subscribe only
                        ┌───────────▼────────────┐
                        │  autoware_health_ui    │  graph cache, rate meters,
                        │  + ping / TCP prober   │  event log, ping prober
                        └───────────┬────────────┘
                                    │  HTTP + Server-Sent Events
                        ┌───────────▼────────────┐
                        │  browser (vanilla JS)  │  tiles → tree → leaf detail
                        └────────────────────────┘
```

## Running it

**The launch scripts start it for you.** `autoware_kashiwa.sh`,
`autoware_kashiwa_os1_128.sh` and `autoware_kashiwa_v2x.sh` each bring the
dashboard up before handing off to `ros2 launch`, so it is already at
`http://<vehicle-ip>:8842` by the time Autoware is up. Set `HEALTH_UI=0` to skip
it for one run:

```bash
HEALTH_UI=0 ./autoware_kashiwa.sh
```

It is started **detached, in its own session**, so the Ctrl-C that stops
Autoware does not also stop the dashboard — every module going STALE is exactly
what you want to be looking at in the seconds after Autoware exits or fails to
come up. Starting it twice is a no-op, and a failure to start never blocks the
launch.

### `ros2 launch`, for a one-off look

It is an `ament_python` package (`autoware_health_ui`), so it launches like
anything else in this workspace — in the foreground, stopping with Ctrl-C:

```bash
ros2 launch autoware_health_ui health_ui.launch.xml
ros2 launch autoware_health_ui health_ui.launch.xml port:=9000 probe:=false
ros2 launch autoware_health_ui health_ui.launch.xml host:=127.0.0.1
```

| Argument | Default | |
| --- | --- | --- |
| `host` | `0.0.0.0` | bind address; `127.0.0.1` restricts it to this machine |
| `port` | `8842` | HTTP port |
| `probe` | `true` | ping/TCP the devices in `devices.yaml` |
| `config` | *(packaged)* | a different device inventory |

This needs the package built once (`colcon build --symlink-install
--packages-select autoware_health_ui`). The other two entry points below do not,
which is the reason all three exist: the thing you reach for to diagnose a
workspace should not itself be waiting on that workspace to build.

### The `autoware-health` command

```bash
autoware-health              # run in the foreground (Ctrl-C to stop)
autoware-health start        # start detached; survives closing the shell
autoware-health stop
autoware-health restart
autoware-health status       # up? and what is it currently reporting
autoware-health logs         # follow a detached instance's log
autoware-health open         # open it in a browser
```

Extra arguments pass straight through: `autoware-health start --port 9000`,
`autoware-health --host 127.0.0.1 --no-probe`.

`status` is worth knowing about — it answers the question from a terminal
without opening anything:

```
$ autoware-health status
autoware-health: running (pid 28655) - http://localhost:8842
  autoware  : connected  (last update 0.0s ago)
  modules   : Sensing=STALE  Map=OK  Localization=ERROR  Perception=OK  Vehicle=WARN
  problems  : 14
      [ERROR] localization_topic_sta rate 0.4Hz < 1.0Hz
      [STALE] /sensing/gnss/fix      no publisher seen
      ... and 9 more
```

To put it on `PATH` (once per machine):

```bash
mkdir -p ~/.local/bin
ln -sf "$PWD/health_ui/bin/autoware-health" ~/.local/bin/autoware-health
```

Or call it directly at `health_ui/bin/autoware-health`, or run
`health_ui/run.sh` in the foreground. Start it before or after Autoware — it
picks the graph up whenever it appears, and survives Autoware restarting.

### Which one to use

| | Needs a build | Keeps running after Ctrl-C | |
| --- | --- | --- | --- |
| launch scripts | no | yes | automatic, the normal case |
| `ros2 launch` | **yes** | no | a one-off look, with launch args |
| `autoware-health start` | no | yes | on demand, left running |
| `autoware-health` / `run.sh` | no | no | foreground, for development |

All four run the same node and serve the same page.

No build step, no `npm`, no `pip install`: it uses only the Python standard
library plus `yaml` and `rclpy`, all already present on the vehicle PC.

### Running it as a service instead

The launch scripts cover the normal case. A systemd **user** service is the
alternative if you want the dashboard up from boot, before and independent of
any Autoware run — useful when you want to watch a stack that is failing to
start at all:

```bash
mkdir -p ~/.config/systemd/user
cp health_ui/tools/autoware-health-ui.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now autoware-health-ui
sudo loginctl enable-linger $USER      # start at boot, not at first login
```

Pick one or the other. With the service enabled, the launch-script hook simply
finds it already running and does nothing.

Either way it picks up each Autoware run on its own: the aggregator stamps every
start with a fresh graph id (the start time in hex), the bridge notices the
change and rebuilds the tree, and the browser reloads the structure without a
refresh.

> **DDS environment.** `run.sh` pins `RMW_IMPLEMENTATION` itself, exactly as
> `autoware_kashiwa.sh` does. `~/.bashrc` is only read by interactive shells, so
> without this a service or desktop launcher would default to fastrtps while
> Autoware runs on cyclonedds. The two cannot see each other and the failure is
> silent — the dashboard would sit at "waiting for Autoware" forever next to a
> perfectly healthy stack.

## What you see

**Overview** — one tile per module: Sensing, Map, Localization, Perception,
Planning, Control, Vehicle, System. Colour is the aggregated level; each tile
also carries a WARN/ERROR count and a *liveness age* ("updated 0.2 s ago").
The age matters as much as the colour: a module that is quietly not reporting
is a different failure from one that is reporting a fault, and only the age
tells them apart.

**Drill-down** — click a tile for its subtree, straight from Autoware's own
diagnostic graph. Branches containing a fault are auto-expanded, and the child
whose level matches its unhealthy parent is marked as the culprit, so "why is
Localization red" is answerable without opening every branch.

**Leaf detail** — click any leaf for its `DiagnosticStatus`: message,
`hardware_id`, the full key/value table, and a bar strip of its level history.

**Active problems rail** — always visible, every non-OK item sorted worst
first, each row jumping straight to the leaf. Drill-down is for investigating;
the rail is for *noticing*.

**Devices** — every sensor and its IP, reachability, and measured rate per
topic over a sliding window. **Events** — recent level transitions.

## Design decisions worth knowing

**Cleared faults latch for 30 s.** Autoware diagnostics run at ~10 Hz and real
faults routinely flash for a couple of hundred milliseconds. A dashboard that
only draws instantaneous state will never show them to you. Cleared problems
stay in the rail, dimmed and dashed, and every transition lands in Events.

**ERROR outranks STALE when aggregating.** A component actively reporting a
fault is more actionable than one that has gone quiet, so it wins the tile.

**Rates are normalised by elapsed time, not the nominal window.** Dividing by a
10 s window two seconds after subscribing would report a fifth of the true rate
and paint every healthy topic red — which teaches you to ignore red. Topics
read `measuring…` for their first two seconds instead.

**Not-fitted hardware is muted, not alarmed.** `optional: true` devices stay
grey and out of the rail *while they do not answer at their IP* — only one
lidar profile is on the car at a time. The moment such a device does answer it
is graded normally, because a lidar that responds on its port but publishes
nothing is broken, not absent.

**Sensing is synthesised here.** Autoware's diagnostic graph has no
`/autoware/sensing` node, so the dashboard builds that subtree itself from
device reachability and topic rates. See "Optional Autoware changes" below.

## Configuration

Everything tunable lives in [`config/devices.yaml`](config/devices.yaml):
device names, IPs, probe method (`icmp`, `tcp:<port>`, `none`), the topics each
device feeds with their expected rates, and the `optional` flag. The IPs were
seeded from `segway_sensor_kit_launch/launch/lidar.launch.xml`; the file is read
at start-up and nothing is ever written back to the vehicle.

Global knobs under `settings:` — `probe_interval_s` (10), `rate_window_s` (10),
`rate_warn_ratio` (0.7), `rate_error_ratio` (0.4), `stale_after_s` (5).

**Set `optional:` to match the fitted lidar.** It currently assumes the
`os1_128` default from `lidar.launch.xml`: the OS-1-128 top unit is required,
every other lidar is optional.

## Optional Autoware changes

None of these are made, and none are needed — the dashboard works as-is. They
would only deepen what it can show:

| To gain | Change |
| --- | --- |
| Sensing as a *real* graph module, visible to Autoware's own fail-safe logic | new `autoware_launch/config/system/diagnostics/sensing.yaml` + one line in `autoware-main.yaml` |
| Sensor-driver diagnostics aggregated per kit | `segway_sensor_kit_launch` has no `config/diagnostic_aggregator/sensor_kit.param.yaml`, though the sample kits do |
| Velodyne hardware health (temperature, motor RPM, via the sensor's HTTP interface) | `autoware_velodyne_monitor` is in the tree but is not launched anywhere |

## Developing without a vehicle

```bash
source /opt/ros/humble/setup.bash
source ../install/setup.bash
python3 tools/fake_diag_graph.py     # publishes a small Autoware-shaped graph
autoware-health                      # in another shell
```

The fake graph holds healthy for three seconds, then drops
`/autoware/localization` into ERROR. It takes an optional graph id argument
(`python3 tools/fake_diag_graph.py deadbeef`) so you can simulate an Autoware
restart and watch the dashboard rebuild its tree.

```bash
python3 test_model.py    # offline checks: tree building, module attribution,
                         # graph-id guard, latching, muting, path shapes
```

The Python lives in `autoware_health_ui/`, the browser side in `frontend/`.
Because the workspace builds with `--symlink-install`, editing either takes
effect on the next start with no rebuild; only *adding* a file needs
`colcon build --packages-select autoware_health_ui` again.

## Limitations

- **No authentication.** It binds `0.0.0.0` by default and anyone on the
  vehicle network can read it. That is a deliberate fit for a private research
  network — use `--host 127.0.0.1` plus an SSH tunnel if that is not true here.
- **History is in memory only.** The event log holds the last 2000 transitions
  and is lost on restart; there is no post-drive post-mortem yet.
- **Single vehicle.** The API has no vehicle id.
- **Rate sampling costs a subscription per configured topic.** They are raw
  (never deserialised), so the cost is a memcpy, but they are still real DDS
  subscriptions — do not add hundreds.
