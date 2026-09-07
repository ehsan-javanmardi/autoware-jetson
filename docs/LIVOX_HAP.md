# Livox HAP — lidar and IMU

The lidar on the Jetson/Segway platform, and since 2026-09-06 the source of Autoware's
IMU as well.

| | |
|---|---|
| Device | Livox HAP, `192.168.1.110` (MAC `e4:7a:2c:83:1b:60`) |
| Host | `192.168.1.101` on `eno1`, 1 Gb/s |
| Frame | `livox_frame` |
| Point cloud | `/sensing/lidar/top/livox/points` — `sensor_msgs/PointCloud2`, ~45 k points, 7.5-10 Hz |
| IMU | `/sensing/lidar/top/livox/imu` — `sensor_msgs/Imu`, ~200 Hz |

Select it with `lidar_profile:=livox`, which is the **default**. The Ouster profiles still
work; see [Switching back to the Ouster](#switching-back-to-the-ouster).

## Why the IMU comes from here

The obvious source is the u-blox ZED-F9R, which has a 3-axis gyro and 3-axis
accelerometer on die. They are not reachable: the internal IMU is reported over
**UBX-ESF-RAW**, and `ublox_dgnss` implements neither the message type (`ublox_ubx_msgs`
has `UBXEsfMeas` and `UBXEsfStatus`, no `UBXEsfRaw`) nor a `CFG_MSGOUT_UBX_ESF_RAW_USB`
key. `UBX-ESF-MEAS` is mostly the *input* path for external wheel ticks — enable its
output on this receiver and the only item that appears is `data_type: 10`, the wheel tick.

Reaching the F9R's IMU therefore means forking the driver. The HAP publishes
`sensor_msgs/Imu` natively at 200 Hz, needs no converter node, and sits in the same frame
as the point cloud. See [GNSS_IMU_UBLOX_F9R.md](GNSS_IMU_UBLOX_F9R.md) for the F9R's own
IMU, which still does its real work inside the receiver's dead-reckoning fusion.

## What had to be added

Neither the driver nor the SDK was in this workspace. Only `autoware_livox_tag_filter`
(which classifies the HAP's return `tag` field) and `livox_description` were, and neither
talks to the device.

### Livox-SDK2 — built once, into `/usr/local`

`src/sensor_component/external/Livox-SDK2` is a plain CMake library, not a ROS package,
and it carries a `COLCON_IGNORE` so colcon leaves it alone. The driver looks for it with
`find_library(... liblivox_lidar_sdk_shared.so /usr/local/lib REQUIRED)`, a hard-coded
path, so it must be installed there:

```bash
cd src/sensor_component/external/Livox-SDK2
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release && make -j6 && sudo make install
```

This is the one step a plain `colcon build` cannot do for you. Without it,
`livox_ros_driver2` fails to configure.

### livox_ros_driver2 — two local changes

Upstream expects you to run its `build.sh`, which generates `package.xml` and `launch/`
before calling colcon. This workspace commits `src/` and builds with a plain
`colcon build`, so:

- **`package.xml` and `launch/` are materialised** from `package_ROS2.xml` and
  `launch_ROS2/` and committed. Re-running upstream's `build.sh` would overwrite them.
- **`DISTRO_ROS` defaults from `$ENV{ROS_DISTRO}`** in `CMakeLists.txt`. `build.sh` passes
  `-DDISTRO_ROS=humble`; unset, the CMake silently takes a pre-humble `rosidl` typesupport
  path and the build fails. `ROS_EDITION` needs no such fix — unset already falls through
  to the ROS 2 branch.

## Configuration lives in JSON, not in the launch file

The SDK reads `livox_ros_driver2/config/HAP_config.json` directly, so **the lidar's
address is not a launch argument.** To point at a different device, edit that file:

```json
"host_net_info": { "cmd_data_ip": "192.168.1.101", ... }   <- this machine, on eno1
"lidar_configs":  [ { "ip": "192.168.1.110", ... } ]        <- the HAP
```

The shipped defaults are `192.168.1.5` for the host and `192.168.1.100` for the lidar.
Both were wrong here. Note there is a second, unidentified device on this subnet at
`192.168.1.100` (`b0:25:aa:54:47:78`) — it is not the lidar, and pinging it is not a test
that the lidar is present. The driver will tell you the truth on startup:

```
found lidar not defined in the user-defined config, ip: 192.168.1.110
```

## `xfer_format` must be 0

The driver defaults to `xfer_format: 1`, its own `livox_ros_driver2/msg/CustomMsg`, which
nothing in Autoware can read. `livox_hap.launch.xml` sets `0` for
`sensor_msgs/PointCloud2`. If `/sensing/lidar/top/livox/points` exists but every Autoware
consumer ignores it, check the message type first.

The cloud carries `x, y, z, intensity, tag, line, timestamp` at a 26-byte point step.
`tag` is the HAP return classification that `autoware_livox_tag_filter` consumes.

## The driver emits Autoware's point type

Autoware's `pointcloud_preprocessor` validates the field layout of every cloud and
**aborts** on a mismatch:

```
The pointcloud layout is not compatible with PointXYZIRCAEDT. Aborting
```

The failure is silent in the worst way: the driver publishes correctly at 10 Hz, the crop
box loads and advertises its output topic, and `/sensing/lidar/concatenated/pointcloud`
sits at 0 Hz **with a publisher attached**. Nothing downstream works, and neither the
driver nor the dashboard reports a fault.

This driver is therefore modified to publish `autoware::point_types::PointXYZIRCAEDT`
directly, the same approach `autoware_ouster_ros` takes for the Ouster:

| Field | Offset | Source |
|---|---|---|
| `x`, `y`, `z` | 0, 4, 8 | Livox, unchanged |
| `intensity` | 12 | Livox reflectivity, clamped to `uint8` |
| `return_type` | 13 | low bits of the Livox `tag` |
| `channel` | 14 | Livox `line` |
| `azimuth` | 16 | **derived**, `atan2(y, x)` |
| `elevation` | 20 | **derived**, `atan2(z, hypot(x, y))` |
| `distance` | 24 | **derived**, `sqrt(x²+y²+z²)` |
| `time_stamp` | 28 | Livox `offset_time`, ns from the cloud header |

32 bytes per point. The offsets are checked by name and position upstream, so
`AutowarePointXYZIRCAEDT` in `src/comm/comm.h` must stay inside the `#pragma pack(1)`
region.

### Why in the driver, and why the angles are computed

An earlier attempt used a separate Python converter node. It could not keep up: the cloud
crossed DDS twice, ~1.4 MB each way, and the node held ~85 % of a core while the chain
degraded from 10 Hz at the sensor to 0.9 Hz concatenated. Building the cloud in the right
layout once, in the driver, removes the round trip entirely rather than optimising it.

The polar fields are computed rather than zero-filled. An audit found nothing in the
*currently configured* pipeline that reads them — `ScanGroundFilter` derives its own from
x/y — but `ring_outlier_filter`, the polar-voxel filters and the ML detectors
(`lidar_frnet`, `ptv3`) all declare layouts containing them, and are switchable by
config. Zero-filled angles would make those produce plausible-looking wrong output rather
than fail. In C++, over a buffer already being written, three extra operations per point
cost far less than a latent trap for whoever enables a detector later.

The vendor code also built a temporary `std::vector` and `memcpy`'d it into the message;
the points are now written straight into the message buffer.

## Extrinsics are a placeholder

`livox_frame` is currently at the sensor-kit origin with zero rotation, in
[`segway_sensor_kit_description/config/sensor_kit_calibration.yaml`](../src/launcher/autoware_launch/sensor_kit/segway_sensor_kit_launch/segway_sensor_kit_description/config/sensor_kit_calibration.yaml).

**This has to be measured before driving.** Ground segmentation reads `z` as height above
`base_link`, so an unmeasured mount does not merely offset the cloud — it puts the ground
plane in the wrong place, and obstacles with it.

## Single lidar: no concatenation

`PointCloudConcatenateDataSynchronizerComponent` refuses to load with one input
(`Only one topic given. Need at least two topics to continue.`), so the `livox` profile
routes the cloud through a crop-box passthrough whose real job is the transform into
`base_link`. A plain topic relay would leave the cloud in `livox_frame`, and ground
segmentation would read sensor-relative heights as if they were vehicle-relative.

`config/lidar_profiles/livox.param.yaml` exists because the preprocessor include always
names a concatenate configuration, even when concatenation is off.

## Switching back to the Ouster

```bash
ros2 launch ... lidar_profile:=os1_128     # or os2_32, or velodyne
```

The profile selects the driver, the passthrough's input topic and its input frame
together, so nothing else needs changing.

## Verifying

```bash
ros2 topic hz   /sensing/lidar/top/livox/points     # expect 7.5-10 Hz
ros2 topic hz   /sensing/lidar/top/livox/imu        # expect ~200 Hz
ros2 topic echo /sensing/lidar/top/livox/points --once --field width   # expect ~45000
```

A `width` of 0 with the topic present means the driver is connected but the lidar is not
returning points — check the work mode in the driver's log, not the network.
