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
| `usb_cam_node_exe` | dies | references package `pixkit_sensor_kit_launch`, which does not exist (real name `velodyne_pixkit_sensor_kit_launch`). No camera connected; left unfixed on purpose. |
| `nmea_tcpclient_driver` | dies, exit 255 | GNSS NMEA TCP client to `192.168.1.110:9904`. Receiver is reachable; not yet diagnosed. |

## Lidar configuration changes made here

`launch/lidar.launch.xml` was rewritten to drive the Ouster instead of four Velodyne
VLP16s (`192.168.1.201-204`) that are not present, and `host_ip` changed from the shipped
`192.168.1.102` to this machine's `192.168.1.20`. Revert with
`use_velodyne:=true use_ouster:=false`. Originals in
`../pixkit_setup_backups/ouster_launch_change/`.

`launch/os_sensor_top.launch.xml` had its lifecycle "HACK" (fixed `sleep 3` / `sleep 5`
before `ros2 lifecycle set`, which failed with "Node not found" under load) replaced by
`launch/activate_lifecycle_node.sh`, which waits for registration then
configure → activate with retries.
