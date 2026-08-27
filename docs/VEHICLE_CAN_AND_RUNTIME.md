# Vehicle CAN and runtime notes (Pixkit)

State as of 2026-08-18, from a real launch on this machine.

## Vehicle CAN bus

Two **PEAK PCAN-USB FD** adapters (`lsusb`: `0c72:0012` ×2) are connected and the
`peak_usb` kernel module is loaded, so the interfaces enumerate as `can0` and `can1`.

**They come up `DOWN` and ROS does not configure them.** `ros2_socketcan` only opens an
already-configured SocketCAN interface; setting the bitrate is a host-level step:

```bash
sudo ip link set can0 up type can bitrate 500000
sudo ip link set can1 up type can bitrate 500000
ip -br link show type can          # expect UP
```

500 kbit/s is the rate documented in this repo
(`src/sensor_component/external/ars408_driver/README.md`), and it is confirmed working.

### Verified working 2026-08-18

Brought up at 500 kbit/s with Autoware stopped (so no control frames reached the chassis).
Both buses carry live vehicle reports:

```
can0  UP   bitrate 500000  sample-point 0.875  state ERROR-ACTIVE (berr tx 0 rx 0)
can1  UP   bitrate 500000
```

`ERROR-ACTIVE` is the normal healthy CAN state, not a fault. Throughput measured over a
~70 s window: **+33,894 frames on can0, +33,973 on can1** (~480 frames/s each), with
**0 errors and 0 dropped** on both.

Sample frames (`candump -n 8 can0`):

```
can0  530   [8]  34 00 00 00 00 00 00 03
can0  531   [8]  10 00 00 00 00 00 03 00
can0  532   [8]  04 01 00 00 00 E1 03 00
can0  600   [5]  50 24 58 11 10
can0  701   [8]  00 4E 81 FC 80 20 01 47
```

IDs `0x530`-`0x532` are in the PIX Hooke chassis-report range decoded by
`pix_hooke_driver_report_parser_node`.

**Known anomaly:** `can1` reports `<NO-CARRIER>` in its link flags while still receiving
~480 frames/s with zero errors. The RX counter is authoritative; the flag is unreliable on
some `peak_usb` setups. Check `ip -s link show can1` rather than the flag.

`can-utils` is installed, so `candump` / `cansend` are available.

> [!WARNING]
> **Bring CAN up only when the vehicle is in a safe state.**
> `pix_hooke_driver_control_command_node` publishes to `/to_can_bus` as soon as Autoware
> runs. The instant `can0`/`can1` are up, those frames reach the chassis controller, so a
> powered vehicle can move. Safe order: stop Autoware → bring interfaces up → verify with
> `candump can0` → then start Autoware with wheels clear and the e-stop in reach.

To verify the bus before involving Autoware:

```bash
sudo apt install can-utils     # if needed
candump can0                   # chassis reports should stream when the vehicle is on
```

### Symptom when CAN is down

`pix_hooke_driver_command_node` logs rising timeouts, which is expected and harmless:

```
[pix_hooke_driver_command_node] brake command timeout = 5059.6 ms
[pix_hooke_driver_command_node] drive command timeout = 5059.6 ms
[pix_hooke_driver_command_node] steer command timeout = 5059.6 ms
```

Downstream effect: `/sensing/vehicle_velocity_converter/twist_with_covariance` has a
publisher but never publishes, so anything needing vehicle velocity stays idle.

### Persisting the bring-up (optional)

`ip link` settings do not survive a reboot. Either add a systemd unit modelled on
`/etc/systemd/system/pixkit-cyclonedds.service`, or a `systemd-networkd` `.network` file.
Deliberately **not** automated here, because auto-enabling CAN at boot means the bus is
live before anyone has checked the vehicle is safe.

## Why RViz shows no lidar points

The Ouster itself is fine — `/sensing/lidar/top/ouster/points` streams at **10 Hz** and
TF resolves (`base_link -> os_lidar_top` = `[0, 0, 1.400]`, yaw 178°).

The problem is one layer up:

```
[pointcloud_container] Component constructor threw an exception:
  Only one topic given. Need at least two topics to continue.
```

`PointCloudConcatenateDataSynchronizerComponent` requires **two or more** input clouds.
This vehicle currently has a single Ouster, so the component refuses to load and
`/sensing/lidar/concatenated/pointcloud` ends up with **0 publishers / 5 subscribers** —
and that concatenated topic is what the Autoware RViz config displays.

Options for a single-lidar setup:

1. **Relay** the raw cloud to the concatenated topic (simplest):
   ```bash
   ros2 run topic_tools relay /sensing/lidar/top/ouster/points \
                              /sensing/lidar/concatenated/pointcloud
   ```
2. Give the concat node a second (real) lidar — the Pixkit design expects three Ousters
   (`os_top_config.yaml`, `os_rl_config.yaml`, `os_rr_config.yaml`; top is `.125` in that
   config, `.126` in `os_sensor_top.launch.xml`).
3. Replace the concat component with a passthrough/crop-box chain for one lidar.

### Seeing points immediately, without localization

`/tf` is empty — no `map -> base_link`, because localization has no initial pose. With
RViz's Fixed Frame set to `map` nothing can render. To confirm the sensor visually:

- set **Fixed Frame** to `base_link` (or `os_lidar_top`)
- add a **PointCloud2** display on `/sensing/lidar/top/ouster/points`

For the full pipeline, localization needs an initial pose (`2D Pose Estimate` in RViz, or
GNSS-based auto-init once RTK is configured — see `RTK_ICHIMILL_SETUP.md`).

## Other known runtime issues

| Node | Status | Cause |
| --- | --- | --- |
| `usb_cam_node_exe` | dies | references package `pixkit_sensor_kit_launch`, which does not exist (real name `pixkit_sensor_kit_launch`). No camera connected; left unfixed on purpose. |
| `nmea_tcpclient_driver` | dies, exit 255 | GNSS NMEA TCP client to `192.168.1.110:9904`. Receiver is reachable; not yet diagnosed. |

## Lidar configuration changes made here

`launch/lidar.launch.xml` was rewritten to drive the Ouster instead of four Velodyne
VLP16s (`192.168.1.201-204`) that are not present, and `host_ip` changed from the shipped
`192.168.1.102` to this machine's `192.168.1.100`. Revert with
`use_velodyne:=true use_ouster:=false`. Originals in
`../pixkit_setup_backups/ouster_launch_change/`.

`launch/os_sensor_top.launch.xml` had its lifecycle "HACK" (fixed `sleep 3` / `sleep 5`
before `ros2 lifecycle set`, which failed with "Node not found" under load) replaced by
`launch/activate_lifecycle_node.sh`, which waits for registration then
configure → activate with retries.

## Session 2026-08-21 — actuation map wiring and two `pix_hooke_driver` bugs

Three problems were found while running with both CAN buses up. All three are fixed in the
tree; only the last one still needs a road test.

### 1. The calibrated accel/brake maps were never loaded

`ros2 param get /raw_vehicle_cmd_converter csv_path_accel_map` reported the converter
package's own default map, not the Pixkit one, even though
`autoware_launch/config/vehicle/raw_vehicle_cmd_converter/raw_vehicle_cmd_converter.param.yaml`
points at `pixkit_description/data/accel_map.csv`.

Cause: `pixkit_launch/launch/vehicle_interface.launch.xml` included the converter launch
file **bare**. `raw_vehicle_converter.launch.xml` declares

```xml
<arg name="config_file" default="$(find-pkg-share autoware_raw_vehicle_cmd_converter)/config/raw_vehicle_cmd_converter.param.yaml"/>
```

so with no `config_file` argument it silently loads its own defaults. The `autoware_launch`
config was edited but never reached the node.

Fix: pass `config_file` explicitly from `vehicle_interface.launch.xml`.

Verify after any change to this path:

```bash
ros2 param get /raw_vehicle_cmd_converter csv_path_accel_map
# must print .../install/pixkit_description/share/pixkit_description/data/accel_map.csv
```

Why it matters for the throttle complaint. The two maps disagree in the direction that
explains the symptom — at standstill, for the same requested acceleration the Pixkit map
asks for roughly twice the pedal:

| requested accel at v=0 | default map pedal | Pixkit map pedal |
| --- | --- | --- |
| 0.3 m/s² | 0.000 | 0.135 |
| 0.5 m/s² | 0.067 | 0.190 |
| 1.0 m/s² | 0.173 | 0.321 |
| 1.5 m/s² | 0.258 | 0.465 |

With the default map the controller under-commands the pedal, the vehicle does not break
static friction, the longitudinal PID integral winds up, and the pedal then ramps toward
the `max_throttle: 0.4` clamp — which matches "the throttle is too high and it stops".
Push the car by hand and static friction is already broken, so the loop closes and control
works. That is the reported behaviour exactly.

**Not yet validated on the road.** During an engage attempt, with the wheels clear and the
e-stop in reach, watch:

```bash
ros2 topic echo /control/command/actuation_cmd
ros2 topic echo /vehicle/status/velocity_status
```

### 2. `pix_hooke_driver_report_converter_node` segfaulted on start (exit -11)

```
[pix_hooke_driver_report_converter_node-6] WARN: vehicle work sta fb not received or timeout
[ERROR] process has died [exit code -11]
```

`report_converter.cpp` treats `vehicle_work_sta_fb_ptr_` as non-vital: when it is null the
timer callback only **warns** and carries on, then dereferences the same null pointer a few
lines later to read `vcu_driving_mode_fb`. The work-state frame (`0x534`) arrives slower
than the four vital frames, so there is a start-up window where everything else is present
and this is not — a race that fires on roughly every cold start.

Consequence: no `/vehicle/status/velocity_status`, no `/vehicle/status/control_mode`, so
`is_autonomous_mode_available: false` and no AUTO button, no matter how good localization is.

Fix: publish `NOT_READY` when the pointer is null instead of dereferencing it. The same
callback also filled in `hazard_lights_report_msg` and never published it; that publish was
added.

### 3. Chassis manual mode reported `NOT_READY` to Autoware

`VCU_DrivingModeFb` (frame `0x534`) is `{0: STANDBY, 1: SELF_DRIVING, 2: REMOTE, 3: MAN}`.
The switch in `report_converter.cpp` handled 0, 1 and 2 and let 3 fall through to
`default: NOT_READY`. The chassis sits in `MAN` (3) whenever it is not engaged, so Autoware
saw `ControlModeReport::NOT_READY` and would not offer the transition into autonomous.

Fix: map `VCU_DRIVINGMODEFB_MAN` to `ControlModeReport::MANUAL`.

Decoding what you see:

```bash
ros2 topic echo /vehicle/status/control_mode --once   # 1 AUTONOMOUS 4 MANUAL 5 DISENGAGED 6 NOT_READY
ros2 topic echo /pix_hooke/v2a_vehicleworkstafb --once | head -3
```

### State reached at the end of the session

| Item | State |
| --- | --- |
| Both CAN buses | up, `/from_can_bus` ~825 Hz, all seven `v2a_*` report topics ~50 Hz |
| Localization | `initialization_state: 3` (INITIALIZED), `map -> base_link` present |
| Route | `/api/routing/state: 2` (SET) |
| Accel/brake maps | Pixkit maps confirmed loaded in the node |
| Vehicle status topics | publishing after the segfault fix |
| Autonomous mode | not yet re-checked after the `MAN -> MANUAL` fix — **first thing to test next session** |

Next session, after `colcon build --symlink-install --packages-select pix_hooke_driver pixkit_launch`
and a fresh launch:

```bash
ros2 topic echo /vehicle/status/control_mode --once     # expect mode: 4
ros2 topic echo /api/operation_mode/state --once        # expect is_autonomous_mode_available: true
ros2 param get /raw_vehicle_cmd_converter csv_path_accel_map
```

### A note on stopping processes

`pkill -f <pattern>` matches the shell running the command, because the pattern is part of
that shell's own command line — it kills itself and orphans the target. The `[e]` bracket
trick does not help when the command line also contains the literal name elsewhere. Match
on the executable instead:

```bash
for d in /proc/[0-9]*; do
  case "$(readlink "$d/exe" 2>/dev/null)" in
    *report_converter_node) kill -9 "${d#/proc/}";;
  esac
done
```

## The two PCAN adapters swap names between boots

Symptom: every `/pix_hooke/v2a_*` topic silent, no `/vehicle/status/velocity_status`, and

```
[socket_can_receiver]: Error receiving CAN message: can0 - CAN Receive Timeout
[pix_hooke_driver_report_node]: drive stat fb report timeout = 95350 ms
```

while `candump can0` and `candump can1` both clearly show traffic.

Cause: the two PEAK PCAN-USB FD adapters are indistinguishable to udev — same vendor `0c72`,
same product `0012`, same `ID_SERIAL` (`PEAK-System_Technik_GmbH_PCAN-USB_FD`), and **no
unique serial exposed in sysfs**. `can0` and `can1` are therefore handed out in USB
enumeration order, which is a race and can come out either way after a reboot or a replug.

Only the *first* bridge matters: the whole `pix_hooke_driver` chain reads `/from_can_bus` and
writes `/to_can_bus`, both belonging to `socket_can_bridge.launch.xml`. The second bridge
publishes `/from_can1_bus`, which has **zero subscribers** — it only keeps the other adapter
claimed. So when the order flips, the driver is listening to the wrong bus and everything
downstream of the vehicle interface stops.

### Identify which interface has the chassis

```bash
for i in can0 can1; do echo "== $i"; timeout 3 candump -n 2000 $i | awk '{print $2}' | sort -u | tr '\n' ' '; echo; done
```

The chassis bus carries `530 531 532 536 537 539 542` (and `507 509 511`). The other bus
carries only CANopen-looking traffic — `701` heartbeats plus `600`/`201`.

### This is handled automatically

`chassis_can_interface` and `aux_can_interface` are top level arguments of
`autoware.launch.xml`, plumbed through `tier4_vehicle_launch/vehicle.launch.xml` into
`pixkit_launch/vehicle_interface.launch.xml`. Both default to `auto`, which runs

    pixkit_launch/scripts/detect_chassis_can.py --role {chassis,aux}

during launch argument evaluation. It opens a raw CAN socket on every `canN` interface that is
up, listens ~0.4 s each, and picks whichever one delivers the VCU feedback frames. Nothing has
to be passed, and the answer is right whichever order the adapters enumerated in.

A udev rule was considered and rejected: the adapters carry no distinguishing identity, so the
only thing a rule could key on is the USB port path (`udevadm info -q property -p
/sys/class/net/can0 | grep ID_PATH`), which pins the names only as long as nobody moves a
cable. Renaming straight to `can0`/`can1` also collides with the name the kernel already gave
the other adapter. Listening to the bus identifies it by what it actually carries, which is
the property we care about.

The script never fails the launch. If fewer than two `canN` interfaces are up, or no bus
answers (vehicle powered down), it warns on stderr and falls back to `can0`/`can1`.

Overriding is still available when you want to force it:

```bash
./autoware_kashiwa.sh chassis_can_interface:=can1 aux_can_interface:=can0
```

Confirm what was chosen:

```bash
ros2 param get /socket_can_receiver interface    # the chassis bridge
ros2 param get /socket_can1_receiver interface   # the unused one
```
