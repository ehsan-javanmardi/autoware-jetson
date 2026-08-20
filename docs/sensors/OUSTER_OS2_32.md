# Ouster OS-2-32 — 32 beam long range lidar

The second Ouster available for this vehicle. It uses the same driver, the same point type and the
same top mount as the [OS-1-128](OUSTER_OS1_128.md); what differs is the address, the beam count
and the field of view. Select it with `lidar_profile:=os2_32`.

## At a glance

| | |
| --- | --- |
| Model | Ouster OS-2, 32 beams |
| Address | `192.168.1.120` |
| Host address | `192.168.1.100/24` on the sensor LAN, static, **no gateway** |
| UDP ports | lidar `38672`, imu `48215` (shared with the OS-1 profile) |
| Point type | `xyzircaedt` — `autoware::point_types::PointXYZIRCAEDT` |
| Topic | `/sensing/lidar/top/ouster/points` |
| Frames | `os_sensor_top` → `os_lidar_top`, `os_imu_top` |
| Concat config | `config/lidar_profiles/os2_32.param.yaml` |

Only one Ouster runs at a time, so the OS-2-32 reuses the topic and frames of the top mount rather
than introducing its own. Nothing downstream has to change when the units are swapped.

## Running it

```bash
ros2 launch autoware_launch autoware.launch.xml \
    vehicle_model:=pixkit sensor_model:=velodyne_pixkit_sensor_kit \
    map_path:=$PWD/autoware_map \
    lidar_profile:=os2_32
```

Or through the script, which passes extra arguments through:

```bash
./autoware_velodyne_kashiwa.sh autoware_map lidar_profile:=os2_32
```

A different address for one run:

```bash
... lidar_profile:=os2_32 os2_32_ip:=192.168.1.105
```

## What has to be checked when swapping units

1. **The extrinsic.** `base_link2os_lidar_top` in
   [`sensors_calibration.yaml`](../../src/launcher/autoware_launch/sensor_kit/velodyne_pixkit_sensor_kit_launch/velodyne_pixkit_sensor_kit_description/config/sensors_calibration.yaml)
   describes one physical mount. The OS-2 is a different size from the OS-1, so unless it sits in
   exactly the same place with the same orientation, that entry has to be re-measured before this
   profile localizes correctly. Wrong extrinsics do not raise an error, they produce scan matching
   that drifts or never converges.
2. **The address.** `.120` keeps the lidars together in `.12x` and leaves `.100` to the host,
   which is where the rest of the setup expects it. Set it through the sensor's web UI, or pass
   `os2_32_ip:=<address>` for a one-off run.
3. **`host_ip`.** The sensor sends its UDP stream to whatever `host_ip` names. On a machine whose
   sensor LAN address is not `192.168.1.100`, pass `host_ip:=<that address>` or the driver will
   connect, configure the sensor and receive nothing.

## Differences from the OS-1-128 that matter downstream

| | OS-1-128 | OS-2-32 |
| --- | --- | --- |
| Beams (`channel` values) | 128 | 32 |
| Vertical field of view | wide | narrow, longer range |
| Points per scan at `1024x10` | 131,072 | 32,768 |

The narrower vertical field of view is the part worth thinking about: ground segmentation and
scan matching both rely on seeing enough of the ground plane near the vehicle. The ground
segmentation parameters in
[`ground_segmentation.param.yaml`](../../src/launcher/autoware_launch/autoware_launch/config/perception/obstacle_segmentation/ground_segmentation/ground_segmentation.param.yaml)
were tuned for a 128 beam sensor, and a four times sparser cloud may need
`grid_size_m` and `gnd_grid_buffer_size` revisited.

## Verifying

```bash
ping 192.168.1.120
ros2 topic hz /sensing/lidar/top/ouster/points                    # ~10 Hz
ros2 topic echo --field fields /sensing/lidar/top/ouster/points --once   # 10 fields
ros2 topic echo --field height /sensing/lidar/top/ouster/points --once   # 1 (unorganized)
ros2 run tf2_ros tf2_echo base_link os_lidar_top
```
