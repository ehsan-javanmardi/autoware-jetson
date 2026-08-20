# How the sensing launch works

From `autoware.launch.xml` to a point cloud on
`/sensing/lidar/concatenated/pointcloud`. Every file named here is in this repository, so the
chain can be followed by opening them in order.

## The chain

```
autoware.launch.xml                                     autoware_launch
│   vehicle_model:=pixkit  sensor_model:=velodyne_pixkit_sensor_kit
│
├── pointcloud_container.launch.py                      autoware_launch
│      creates /pointcloud_container, EMPTY. Components are loaded into it
│      later, by name, from launch files that know nothing about each other.
│
├── vehicle.launch.xml                                  tier4_vehicle_launch
│      robot_state_publisher, from $(sensor_model)_description/config
│      → every TF frame: base_link, os_lidar_top, gnss_link, camera ...
│
└── components/tier4_sensing_component.launch.xml       autoware_launch
    └── sensing.launch.xml                              tier4_sensing_launch
        │   push-ros-namespace "sensing"     ← where every /sensing/... name comes from
        │   sensor_launch_pkg = $(find-pkg-share $(var sensor_model)_launch)
        │
        └── sensing.launch.xml                          velodyne_pixkit_sensor_kit_launch
            ├── lidar.launch.xml            ← the profile lives here
            │   ├── os_sensor_top.launch.xml         Ouster driver + activation
            │   ├── (velodyne block, off unless the profile asks for it)
            │   ├── single lidar passthrough   → loaded into /pointcloud_container
            │   └── pointcloud_preprocessor.launch.py
            │         concatenate node        → loaded into /pointcloud_container
            ├── imu.launch.xml               imu_corrector, source selected here
            ├── gnss.launch.xml              CHC CGI-410 over NMEA TCP
            └── camera_launch.py             usb_cam
```

## The three mechanisms worth understanding

### `sensor_model` selects a package by name

```xml
<let name="sensor_launch_pkg" value="$(find-pkg-share $(var sensor_model)_launch)"/>
```

`sensor_model:=velodyne_pixkit_sensor_kit` resolves to the package
`velodyne_pixkit_sensor_kit_launch`, and Autoware then includes **that package's**
`launch/sensing.launch.xml`. Nothing else connects the two: the name is the contract. The same
trick appears twice more, for `$(var sensor_model)_description` (the TF frames and extrinsics) and
`$(var vehicle_model)_description` (vehicle dimensions).

This is why a new vehicle means a new pair of packages named `<model>_launch` and
`<model>_description`, and why a *different lidar set on the same vehicle* does not — see
[SENSORS.md](SENSORS.md#sensor-combinations).

### The namespace is pushed once, high up

`tier4_sensing_launch/sensing.launch.xml` pushes `sensing`, and the sensor kit pushes `lidar`,
`top`, and so on beneath it. That is the entire reason the Ouster ends up on
`/sensing/lidar/top/ouster/points`. Nothing in the driver knows that name.

The consequence to watch for: **relative names inside a pushed namespace resolve into it**. A
composable node loaded with `target="pointcloud_container"` from inside the `lidar` group looks
for `/sensing/lidar/pointcloud_container`, which does not exist. The passthrough in
`lidar.launch.xml` targets `/$(var pointcloud_container_name)` with a leading slash for exactly
this reason.

### The container is filled by strangers

`autoware.launch.xml` creates `/pointcloud_container` empty. Sensing loads the concatenate node or
the passthrough into it; localization loads its crop box into the same container; perception loads
lidar_centerpoint. They are composed at runtime into one process for zero-copy point cloud
transport, and none of the launch files involved reference each other.

Two failure modes follow from that, and neither is loud:

- **A load can fail while everything else comes up normally.** The container stays alive and empty,
  and downstream nodes just wait. Check with `ros2 node list | grep pointcloud_container` and
  compare against what you expect to be inside it.
- **The container is a shared name.** Two launches that both create it, or a stale one left over
  from a previous run, produce a graph where the wrong instance answers.

## Where the lidar profile fits

`lidar.launch.xml` is the only file that knows which lidars exist. `lidar_profile` decides three
things at once, and they must agree:

| | `os1_128` / `os2_32` | `velodyne` |
| --- | --- | --- |
| Driver started | Ouster, at the profile's address | four VLP-16 |
| Loaded into the container | passthrough (crop box, transform only) | concatenate node |
| Parameter file | `config/lidar_profiles/<profile>.param.yaml` | same |

The passthrough exists because the concatenate node refuses to construct with a single input
topic. Both paths publish `/sensing/lidar/concatenated/pointcloud` in `base_link`, which is the
contract the rest of Autoware depends on.

## Following it yourself

```bash
# what the top level accepts
ros2 launch autoware_launch autoware.launch.xml --show-args

# which package a sensor_model resolves to
ros2 pkg prefix velodyne_pixkit_sensor_kit_launch

# what actually ended up in the container
ros2 node list | grep -v "^/sensing\|^/perception"   # components appear as their own nodes
ros2 component list                                   # grouped by container

# where a topic really comes from
ros2 topic info /sensing/lidar/concatenated/pointcloud --verbose
```

When something in sensing does not appear, the order that finds it fastest is: does the driver
process exist → is it publishing its own topic → did the container get its component → is the
topic named what you think, after all the namespace pushes.
