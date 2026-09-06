# Velodyne VLP-16 ×4 — not fitted

The stock Pixkit configuration drives four VLP-16s. **None are mounted on this vehicle**, and the
whole block is disabled: `use_velodyne` defaults to `false` in
[`lidar.launch.xml`](../../src/launcher/autoware_launch/sensor_kit/segway_sensor_kit_launch/segway_sensor_kit_launch/launch/lidar.launch.xml).
The driver packages are still built, so the configuration only needs a launch argument to come back.

## The stock four

| Position | Address | Data port | Frame | Max range | Scan phase | Azimuth window |
| -------- | ------- | --------- | ----- | --------- | ---------- | -------------- |
| top | `192.168.1.201` | 2368 | `velodyne_top` | 250 m | 300° | full |
| left | `192.168.1.202` | 2369 | `velodyne_left` | 5 m | 180° | 300°–60° |
| right | `192.168.1.203` | 2370 | `velodyne_right` | 5 m | 180° | 300°–60° |
| rear | `192.168.1.204` | 2371 | `velodyne_rear` | 1.5 m | 180° | 300°–60° |

Each is launched through `common_sensor_launch/velodyne_VLP16.launch.xml` with `host_ip` set to
the host's sensor LAN address. The three short-range units are there for close-in obstacle
detection, which is why their ranges and azimuth windows are clipped.

## Turning them back on

```bash
ros2 launch autoware_launch autoware.launch.xml \
    vehicle_model:=segway sensor_model:=segway_sensor_kit \
    map_path:=$PWD/autoware_map \
    lidar_profile:=velodyne
```

Running both lidars at once needs more than the two flags:

1. **The concatenate node has to know about every input.**
   [`config/lidar_profiles/`](../../src/launcher/autoware_launch/sensor_kit/segway_sensor_kit_launch/segway_sensor_kit_launch/config/lidar_profiles/os1_128.param.yaml)
   currently lists one topic, and `lidar_timestamp_offsets` and `lidar_timestamp_noise_window`
   need one entry per input topic. A mismatched array length is a startup failure.
2. **The Velodyne driver publishes `PointXYZIRC`-incompatible clouds** unless run through the
   Autoware preprocessing chain. The Ouster fork publishes `PointXYZIRCAEDT` directly, so mixing
   the two means the concatenate node reduces everything to the lowest common layout.
3. **Extrinsics.** `velodyne_rear_base_link` exists in
   [`sensors_calibration.yaml`](../../src/launcher/autoware_launch/sensor_kit/segway_sensor_kit_launch/segway_sensor_kit_description/config/sensors_calibration.yaml);
   the other three positions come from the sensor kit xacro and would need checking against the
   actual mounts.

## Packages

`src/sensor_component/external/velodyne_vls/` — `velodyne_driver`, `velodyne_pointcloud`,
`velodyne_msgs`. Three more packages in that repository (`velodyne`, `velodyne_laserscan`,
`bag_to_pcap`) ship with a `COLCON_IGNORE` and are not built.
