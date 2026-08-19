# Pixkit Autoware

Autoware workspace adapted for the **[Pixkit 2.0](https://www.pixmoving.com/pixkit)** research vehicle
equipped with a Velodyne VLP LiDAR.

This is an **upstream Autoware source tree with the Pixkit vehicle and sensor integration merged in**.
Everything upstream Autoware does still applies; this file documents only what is specific to this
workspace. The original upstream README is preserved as
[`README.upstream-autoware.md`](README.upstream-autoware.md).

---

## Version

| Component | Version |
| --------- | ------- |
| **Autoware** (this repo) | **1.9.0** (tag, detached HEAD — commit `1071878`) |
| `autoware_core` | 1.9.0 |
| `autoware_universe` | 0.52.0 |
| `autoware_launch` | 0.52.0 |
| `autoware_utils` | 1.9.0 |
| Pixkit extensions | [tlab-wide/Pixkit_Autoware](https://github.com/tlab-wide/Pixkit_Autoware), merged 2026-08-20 |

### Platform

| | |
| --- | --- |
| OS | Ubuntu 22.04 LTS |
| ROS | ROS 2 Humble |
| RMW | CycloneDDS (`rmw_cyclonedds_cpp`) |
| CUDA | 12.8 (`nvcc` 12.8.93) |
| TensorRT | 10.1.0.27 |
| cuDNN | 8.4.1.50 |

> [!IMPORTANT]
> **Version caveat.** The Pixkit extensions were authored against **Autoware 0.45.1**, but are merged
> here into **1.9.0**. In practice the exposure is limited: the merge replaces only sensor drivers and
> sensor descriptions, and **no core Autoware package is replaced** — see
> [What differs from upstream Autoware](#what-differs-from-upstream-autoware). Expect any
> incompatibility to surface first in `pix_hooke_driver` (vehicle interface) or in the Pixkit launch
> configuration, not in planning or control.

---

## What differs from upstream Autoware

Upstream `autoware` at tag 1.9.0 ships 458 packages in `src/`. This workspace has **497**
(**492 buildable**, 5 excluded via `COLCON_IGNORE`).

### 1. Added — Pixkit vehicle integration

| Package | Location | Purpose |
| ------- | -------- | ------- |
| `pix_hooke_driver`, `pix_hooke_driver_msgs` | `src/vehicle/external/pix_driver/` | Pixkit (PIX Hooke) vehicle interface — CAN control and status |
| `pixkit_launch`, `pixkit_description` | `src/launcher/autoware_launch/vehicle/pixkit_launch/` | Vehicle model: URDF, mesh, calibration. Selected by `vehicle_model:=pixkit` |
| `velodyne_pixkit_sensor_kit_launch`, `velodyne_pixkit_sensor_kit_description` | `src/launcher/autoware_launch/sensor_kit/velodyne_pixkit_sensor_kit_launch/` | Sensor kit: extrinsics and sensor bring-up. Selected by `sensor_model:=velodyne_pixkit_sensor_kit` |

These sit alongside upstream's `sample_vehicle_launch` and `sample_sensor_kit_launch`, following the
standard Autoware vehicle/sensor-kit layout.

> [!NOTE]
> This repository holds the **complete source tree**, `src/` included. The upstream repositories were
> imported once with `vcs import` and then committed here, so a clone is immediately buildable and
> every package is at a known revision. The revision each imported repository was taken from is
> recorded in [`repositories/imported-revisions.repos`](repositories/imported-revisions.repos).

### 2. Added — sensor drivers

Built from source in `src/sensor_component/external/`:

- **LiDAR** — `velodyne_vls` (`velodyne_driver`, `velodyne_pointcloud`, `velodyne_msgs`),
  `ouster-ros` (`ouster_ros`, `ouster_sensor_msgs`) — the
  [ehsan-javanmardi/autoware_ouster_ros](https://github.com/ehsan-javanmardi/autoware_ouster_ros)
  fork, which publishes `autoware::point_types::PointXYZIRCAEDT` natively (`point_type: xyzircaedt`)
  instead of a layout Autoware silently reduces to x/y/z,
  `rslidar_sdk` + `rslidar_msg`,
  `nebula` (`nebula_ros`, `nebula_decoders`, `nebula_hw_interfaces`, `nebula_common`, and message packages)
- **GNSS / IMU** — `fixposition_driver` (`_lib`, `_ros2`, `_odometry_converter_ros2`),
  `fixposition_gnss_tf`, `nmea_navsat_driver`, `tamagawa_imu_driver`
- **Radar / ultrasonic** — `pe_ars408_ros` (Continental ARS408),
  `ultra_sonic_radar_driver`, `ultra_sonic_radar_detector`

34 packages added and built, plus 3 shipped with an upstream `COLCON_IGNORE`
(`velodyne`, `velodyne_laserscan`, `bag_to_pcap`).

### 3. Replaced

Nine packages were overwritten in place by the Pixkit versions (same paths, so no duplicates):

- `src/sensor_component/ros2_socketcan/` — `ros2_socketcan`, `ros2_socketcan_msgs` (both 1.3.0 → 1.3.0, same version)
- `src/sensor_component/external/sensor_component_description/` — `camera_description`,
  `imu_description`, `livox_description`, `pandar_description`, `radar_description`,
  `velodyne_description`, `vls_description`

106 files total were overwritten, confined to `src/sensor_component/`. **No files in the core
`autoware_launch` package, and no `autoware_core` / `autoware_universe` package, were modified.**

### 4. Local modifications

- **`COLCON_IGNORE` added** to `src/sensor_component/external/rslidar_msg/{ros1,ros2}`.
  Upstream Pixkit ships `rslidar_msg` three times (root, `ros1/`, `ros2/`) all declaring the same
  `<name>`, which colcon rejects as a duplicate package name. The root copy is the ROS 2
  (`ament_cmake`) variant and is the one built; `ros1/` is catkin-only.
- **Ouster driver replaced** with the Autoware compatible fork, see
  [section 2](#2-added--sensor-drivers). The sensor kit bring-up
  (`os_sensor_top.launch.xml`) selects `point_type: xyzircaedt` and turns off the driver's own
  static transforms and its organized (NaN padded) cloud, both of which break the Autoware
  pipeline.
- **Single Ouster lidar configuration.** `lidar.launch.xml` brings up the one OS-1 that is actually
  mounted instead of the four VLP16s the Pixkit configuration assumes, `activate_lifecycle_node.sh`
  drives the driver's lifecycle transitions instead of the upstream `sleep`-based approach that
  loses the race on a busy machine, and the concatenate node is configured for that single input.
- **`can1` launch files** added to `src/sensor_component/ros2_socketcan/ros2_socketcan/launch/`
  for the second CAN interface.
- **`autoware_velodyne_kashiwa.sh` rewritten.** The upstream copy hardcoded
  `/home/autoware/pixkit_autoware_0.45.1/...`. It now resolves the workspace from its own location,
  accepts the map path as an argument or `$AUTOWARE_MAP_PATH`, and fails with a clear message if the
  workspace is unbuilt or the map is missing.

---

## Build

Prerequisites are installed by the standard Autoware Ansible playbook (see the
[source installation guide](https://autowarefoundation.github.io/autoware-documentation/main/installation/autoware/source-installation/)):

```bash
cd pixkit_autoware
bash ansible/scripts/install-ansible.sh
ansible-galaxy collection install -f -r ansible-galaxy-requirements.yaml
ansible-playbook autoware.dev_env.install_dev_env
```

`src/` is committed in this repository, so there is nothing to import. Resolve the system
dependencies and build:

```bash
source /opt/ros/humble/setup.bash
rosdep update
rosdep install -y --from-paths src --ignore-src --rosdistro "$ROS_DISTRO"
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
```

## Run on Pixkit

```bash
./autoware_velodyne_kashiwa.sh /path/to/your/map
```

Equivalent to:

```bash
source install/setup.bash
ros2 launch autoware_launch autoware.launch.xml \
    vehicle_model:=pixkit \
    sensor_model:=velodyne_pixkit_sensor_kit \
    map_path:=/path/to/your/map \
    log_level:=debug
```

A point cloud map and lanelet2 map are **not** included in this repository and must be supplied
separately.

---

---

## Running on the vehicle

> [!WARNING]
> **Vehicle CAN can move the vehicle.** Both PEAK PCAN-USB FD interfaces (`can0`, `can1`)
> come up `DOWN`; ROS does not configure them. `pix_hooke_driver` publishes to
> `/to_can_bus` as soon as Autoware runs, so the moment CAN is brought up those frames
> reach the chassis controller. Bring CAN up only with the vehicle in a safe state.
>
> ```bash
> sudo ip link set can0 up type can bitrate 500000
> sudo ip link set can1 up type can bitrate 500000
> ```

See **[VEHICLE_CAN_AND_RUNTIME.md](VEHICLE_CAN_AND_RUNTIME.md)** for CAN bring-up and
verification, why RViz may show no lidar points (the concatenate component needs two or
more lidars), how to view the single Ouster without localization, and the current list of
known runtime issues.

Sensor/network addressing and the host-level settings that make it work are in
**[SETUP_STATE.md](SETUP_STATE.md)**; RTK corrections in
**[RTK_ICHIMILL_SETUP.md](RTK_ICHIMILL_SETUP.md)**.

## Provenance and rollback

This tree was assembled by cloning `autowarefoundation/autoware` at tag **1.9.0** (commit
`1071878`), importing `repositories/autoware.repos`, and copying the `tlab-wide/Pixkit_Autoware`
extensions over the result. The 180 upstream files the Pixkit copy overwrote are listed in
[`pixkit_merge_overwritten_files.txt`](pixkit_merge_overwritten_files.txt); their stock 1.9.0
contents can be recovered from the revisions recorded in
[`repositories/imported-revisions.repos`](repositories/imported-revisions.repos).

The git metadata of the imported repositories was removed so that the whole workspace could live in
a single repository. `repositories/imported-revisions.repos` is what makes that reversible: it names
the exact commit every package came from, so any of them can be re-cloned and diffed against what is
committed here.

The Pixkit extension repository's own README is kept as
[`README.pixkit-extensions.md`](README.pixkit-extensions.md).

## Upstream documentation

- [Autoware documentation](https://autowarefoundation.github.io/autoware-documentation/main/)
- [Autoware Foundation](https://www.autoware.org/)
- [Pixkit extensions upstream](https://github.com/tlab-wide/Pixkit_Autoware)
- Original upstream README: [`README.upstream-autoware.md`](README.upstream-autoware.md)

## License

Apache License 2.0, as [upstream Autoware](https://github.com/autowarefoundation/autoware/blob/main/LICENSE).
See [`LICENSE`](LICENSE).
