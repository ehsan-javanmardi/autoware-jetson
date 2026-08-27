# Pixkit Autoware

Autoware workspace adapted for the **[Pixkit 3.0](https://www.pixmoving.com/pixkit)** research vehicle
equipped with a Velodyne VLP LiDAR.

This is an **upstream Autoware source tree with the Pixkit vehicle and sensor integration merged in**.
Everything upstream Autoware does still applies; this file documents only what is specific to this
workspace. The original upstream README is preserved as
[`docs/README_UPSTREAM_AUTOWARE.md`](docs/README_UPSTREAM_AUTOWARE.md).

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
| `pixkit_sensor_kit_launch`, `pixkit_sensor_kit_description` | `src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/` | Sensor kit: extrinsics and sensor bring-up. Selected by `sensor_model:=pixkit_sensor_kit` |

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
  `rslidar_sdk` + `rslidar_msg`,
  `nebula` (`nebula_ros`, `nebula_decoders`, `nebula_hw_interfaces`, `nebula_common`, and message packages)
- **GNSS / IMU** — `fixposition_driver` (`_lib`, `_ros2`, `_odometry_converter_ros2`),
  `fixposition_gnss_tf`, `nmea_navsat_driver`, `tamagawa_imu_driver`
- **Radar / ultrasonic** — `pe_ars408_ros` (Continental ARS408),
  `ultra_sonic_radar_driver`, `ultra_sonic_radar_detector`

19 packages in total, of which 14 are built. Five carry a `COLCON_IGNORE`: `velodyne`,
`velodyne_laserscan` and `bag_to_pcap` ship with one from upstream, and `rslidar_msg/{ros1,ros2}`
were given one here (see [Local modifications](#5-local-modifications)).

`nebula`, `sensor_component_description`, `sync_tooling_msgs`, `ros2_socketcan` and
`transport_drivers` are **not** in this list: they come from `autoware.repos`, not from Pixkit.

### 3. Added — Autoware compatible Ouster driver

`src/sensor_component/external/autoware_ouster_ros/` (`ouster_ros`, `ouster_sensor_msgs`)

This one is **not** part of the Pixkit extensions and is not the stock Ouster driver either. It is a
standalone repository, [ehsan-javanmardi/autoware_ouster_ros](https://github.com/ehsan-javanmardi/autoware_ouster_ros),
forked from [ouster-lidar/ouster-ros](https://github.com/ouster-lidar/ouster-ros) v0.13.9 and
maintained separately so it can be used on other vehicles. The copy committed here is a plain
directory, not a submodule, so the workspace builds without extra steps.

What it adds is a `point_type: xyzircaedt` that publishes
`autoware::point_types::PointXYZIRCAEDT` directly. Autoware validates an incoming cloud against
that struct by field name, datatype **and byte offset**, and a cloud that does not match is not
rejected but silently reduced to x/y/z, dropping intensity, channel and the per point timestamps,
and with them distortion correction and the ring based outlier filters. No point type the stock
driver offers matches that layout.

See the driver's own [README](src/sensor_component/external/autoware_ouster_ros/README.md) for
the field mapping, the `intensity_source` parameter and the Autoware preset parameter file.

### 4. Replaced

Nine packages were overwritten in place by the Pixkit versions (same paths, so no duplicates):

- `src/sensor_component/ros2_socketcan/` — `ros2_socketcan`, `ros2_socketcan_msgs` (both 1.3.0 → 1.3.0, same version)
- `src/sensor_component/external/sensor_component_description/` — `camera_description`,
  `imu_description`, `livox_description`, `pandar_description`, `radar_description`,
  `velodyne_description`, `vls_description`

106 files total were overwritten, confined to `src/sensor_component/`. **No files in the core
`autoware_launch` package, and no `autoware_core` / `autoware_universe` package, were modified.**

### 5. Local modifications

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
- **`fixposition_driver_ros2` manifest completed.** Its `CMakeLists.txt` calls `find_package` on
  `autoware_sensing_msgs`, `tf2`, `tf2_eigen` and `tf2_ros`, none of which were declared in
  `package.xml`. colcon only exposes declared dependencies to a package's build, so it configured
  successfully only while a Debian copy of `autoware_sensing_msgs` happened to be installed.
- **`autoware_velodyne_kashiwa.sh` rewritten.** The upstream copy hardcoded
  `/home/autoware/pixkit_autoware_0.45.1/...`. It now resolves the workspace from its own location,
  accepts the map path as an argument or `$AUTOWARE_MAP_PATH`, and fails with a clear message if the
  workspace is unbuilt or the map is missing.

---

## Install and build

Ubuntu 22.04 with ROS 2 Humble. Roughly 40 minutes of build time and 30 GB of disk
(`build/` alone is ~4.5 GB).

### 1. Clone

```bash
git clone git@github.com:ehsan-javanmardi/pix_autoware.git
cd pix_autoware
```

`src/` is committed in this repository, so **there is no `vcs import` step**. Every package is
already at the revision recorded in
[`repositories/imported-revisions.repos`](repositories/imported-revisions.repos).

### 2. Prerequisites

Installed by the standard Autoware Ansible playbook (see the
[source installation guide](https://autowarefoundation.github.io/autoware-documentation/main/installation/autoware/source-installation/)):

```bash
bash ansible/scripts/install-ansible.sh
ansible-galaxy collection install -f -r ansible-galaxy-requirements.yaml
ansible-playbook autoware.dev_env.install_dev_env
```

### 3. System dependencies

```bash
source /opt/ros/humble/setup.bash
rosdep update
rosdep install -y --from-paths src --ignore-src --rosdistro "$ROS_DISTRO"
```

### 4. Check that no Autoware package is installed twice

> [!IMPORTANT]
> This is the one step that is easy to skip and expensive to debug. A package that exists **both**
> in `src/` and as a `ros-humble-*` Debian package will usually build against the wrong one:
> `/opt/ros/humble/include` is a single flat directory that sits near the front of the include
> path, so its headers shadow the workspace's own, no matter what CMake resolved the package
> directory to. When the two copies are different versions, the result is a compile error that
> points at source code which is perfectly correct.

List the packages that exist in both places:

```bash
comm -12 \
  <(colcon list --base-paths src --names-only | sort) \
  <(dpkg-query -W -f='${Package}\n' 'ros-humble-*' | sed 's/^ros-humble-//; s/-/_/g' | sort)
```

Ideally this prints nothing. If it lists packages, remove those Debian packages — this workspace
builds them from source:

```bash
sudo apt-get remove -y <the packages, as ros-humble-name-with-hyphens>
sudo apt-get autoremove -y
```

Read what `apt` says it will remove before confirming. On a machine that only ever built this
workspace the list is empty; it fills up when `rosdep` was previously run against a **different**
Autoware tree, because rosdep installs a Debian package for every dependency it cannot find in
`src/`.

### 5. Build

```bash
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
```

510 packages, about 40 minutes on an 8-core machine. Memory, not compile errors, is the usual
failure mode: if a job is killed, retry with `--parallel-workers 4` (or fewer). A failed build can
be resumed by re-running the same command; packages that already finished are skipped.

Success looks like `Summary: 510 packages finished` with no `packages failed` and no `aborted`
line. Several dozen packages report `stderr output`; those are compiler warnings, not failures.

### 6. Run

See [Run on Pixkit](#run-on-pixkit) below. The Kashiwanoha map is committed in
[`autoware_map/`](autoware_map), so there is nothing else to fetch.

### Troubleshooting

| Symptom | Cause and fix |
| ------- | ------------- |
| `rosdep` aborts with `Multiple packages found with the same name "..."` | Two copies of the same package under `src/`. `catkin_pkg` refuses to scan such a tree. Find them with the `colcon list` command above and delete or `COLCON_IGNORE` the copy that does not belong. This is what happens when a Pixkit release built against an older Autoware is copied over a newer `src/`: the packages it ships may have been restructured upstream since, so the copy lands beside the current ones instead of replacing them. |
| `no matching function for call to ...`, where the header in the error path is under `/opt/ros/humble/include` while the `.cpp` is under `src/` | A Debian package is shadowing its source counterpart. Go back to step 4. |
| `Could not find a package configuration file provided by "X"`, and `X` is in `src/` and built | The package's `CMakeLists.txt` calls `find_package(X)` but its `package.xml` does not declare `X`. colcon only puts the prefixes of **declared** dependencies on `CMAKE_PREFIX_PATH`, so a package that builds only because a Debian copy of `X` happens to be installed will break the moment that copy is removed. Add `<depend>X</depend>` to the manifest. |

## Sensors

Two Ouster lidars share the top mount and run one at a time — an **OS-1-128** at `192.168.1.126`
and an **OS-2-32** at `192.168.1.120` — alongside a CHC CGI-410 GNSS/INS at `192.168.1.110` and a
USB camera for traffic lights. The four VLP-16s of the stock Pixkit configuration are not fitted.

Which lidars are launched is chosen with one argument rather than by editing files:

```bash
./autoware_velodyne_kashiwa.sh autoware_map lidar_profile:=os2_32   # os1_128 | os2_32 | velodyne
```

See [`docs/SENSORS.md`](docs/SENSORS.md) for the address map, the profile mechanism and a page per
sensor — [OS-1-128](docs/sensors/OUSTER_OS1_128.md), [OS-2-32](docs/sensors/OUSTER_OS2_32.md),
[GNSS/INS](docs/sensors/CHC_CGI410.md), [camera](docs/sensors/CAMERA.md),
[Velodyne](docs/sensors/VELODYNE_VLP16.md), [ultrasonic and radar](docs/sensors/ULTRASONIC_RADAR.md).

## Vehicle

`base_link` is the centre of the rear axle projected onto the ground; the vehicle is 2.54 m long
and 1.465 m wide with a 1.9 m wheel base. See [`docs/VEHICLE.md`](docs/VEHICLE.md) for the full
geometry, where each sensor sits relative to it, and the front/rear GNSS antenna split.

## Maps

A point cloud map and a lanelet2 map are committed in [`autoware_map/`](autoware_map): Kashiwanoha
Campus, MGRS grid `54SVE`, 22 MB. This is what the launch script loads unless told otherwise.

See [`docs/MAPS.md`](docs/MAPS.md) for what each file is, how to point Autoware at a different
map, and what to check before committing a new one.

## Run on Pixkit

```bash
./autoware_velodyne_kashiwa.sh /path/to/your/map
```

Equivalent to:

```bash
source install/setup.bash
ros2 launch autoware_launch autoware.launch.xml \
    vehicle_model:=pixkit \
    sensor_model:=pixkit_sensor_kit \
    map_path:=/path/to/your/map \
    log_level:=debug
```

The map directory defaults to [`autoware_map/`](autoware_map); pass another path as the first
argument to use a different map. See [Maps](#maps).

### Making the output readable

Autoware writes thousands of lines at startup and, by default, none of them are coloured. Colour is
auto-detected and switched off whenever output is not a terminal, which is exactly what `ros2
launch` does when it captures each node's stdout to prefix it with `[node_name-N]`. Force it on:

```bash
export RCUTILS_COLORIZED_OUTPUT=1          # WARN yellow, ERROR red
export RCUTILS_CONSOLE_OUTPUT_FORMAT='[{severity}] [{name}]: {message}'
```

To keep it across GUI-launched runs, put it beside the DDS settings, which are session-wide for the
same reason:

```bash
echo 'RCUTILS_COLORIZED_OUTPUT=1' >> ~/.config/environment.d/10-ros-dds.conf
```

The bring-up script passes `log_level:=debug`, which is the main reason the terminal is
unreadable. Override it:

```bash
./autoware_velodyne_kashiwa.sh log_level:=warn
```

For a log file already captured, the escape codes are not in it, so colour on the way out:

```bash
grep --color=always -E "ERROR|WARN|$" run.log | less -R      # -R renders the escapes
```

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

See **[docs/VEHICLE_CAN_AND_RUNTIME.md](docs/VEHICLE_CAN_AND_RUNTIME.md)** for CAN bring-up and
verification, why RViz may show no lidar points (the concatenate component needs two or
more lidars), how to view the single Ouster without localization, and the current list of
known runtime issues.

Sensor/network addressing and the host-level settings that make it work are in
**[docs/SETUP_STATE.md](docs/SETUP_STATE.md)**; RTK corrections in
**[docs/RTK_ICHIMILL_SETUP.md](docs/RTK_ICHIMILL_SETUP.md)**.

## Provenance and rollback

This tree was assembled by cloning `autowarefoundation/autoware` at tag **1.9.0** (commit
`1071878`), importing `repositories/autoware.repos`, and copying the `tlab-wide/Pixkit_Autoware`
extensions over the result. The 180 upstream files the Pixkit copy overwrote are listed in
[`docs/PIXKIT_MERGE_OVERWRITTEN_FILES.txt`](docs/PIXKIT_MERGE_OVERWRITTEN_FILES.txt); their stock 1.9.0
contents can be recovered from the revisions recorded in
[`repositories/imported-revisions.repos`](repositories/imported-revisions.repos).

The git metadata of the imported repositories was removed so that the whole workspace could live in
a single repository. `repositories/imported-revisions.repos` is what makes that reversible: it names
the exact commit every package came from, so any of them can be re-cloned and diffed against what is
committed here.

The Pixkit extension repository's own README is kept as
[`docs/README_PIXKIT_EXTENSIONS.md`](docs/README_PIXKIT_EXTENSIONS.md).

## Documentation

Everything written for this vehicle lives in [`docs/`](docs/):

| Document | What it covers |
| -------- | -------------- |
| [`docs/components/LOCALIZATION.md`](docs/components/LOCALIZATION.md) | What estimates the pose: GNSS for initialization, NDT and gyro odometry for the running estimate, how GNSS is fused in, and what each initialization failure means. |
| [`docs/components/PERCEPTION.md`](docs/components/PERCEPTION.md) | The detection stack, the point cloud contract it depends on, and what is still open on this vehicle. |
| [`docs/components/PLANNING_CONTROL.md`](docs/components/PLANNING_CONTROL.md) | Route to trajectory to CAN, what must be true before anything moves, and how to run with no possibility of movement. |
| [`docs/VEHICLE.md`](docs/VEHICLE.md) | Where `base_link` is, the vehicle dimensions planning and control read, where each sensor sits relative to it, and the two GNSS antennas. |
| [`docs/PARALLEL_VERSIONS.md`](docs/PARALLEL_VERSIONS.md) | Keeping the version that runs on the vehicle buildable while developing the next one, with a second working copy rather than by switching branches. |
| [`docs/LAUNCH_CHAIN.md`](docs/LAUNCH_CHAIN.md) | How a launch gets from `autoware.launch.xml` to a point cloud: which file includes which, how `sensor_model` selects this vehicle's packages, where the namespaces come from, and how the shared pointcloud container is filled. |
| [`docs/SENSORS.md`](docs/SENSORS.md) | Index of the sensors on this vehicle, the sensor LAN address map, and a page per sensor under [`docs/sensors/`](docs/sensors) covering its addressing, configuration files, topics and frames. |
| [`docs/V2X.md`](docs/V2X.md) | Accepting vehicles reported over V2X as detected objects: the `use_v2x_objects` flag, why they need a topic of their own, and how to see them. The V2X stack itself is a separate workspace. |
| [`docs/MAPS.md`](docs/MAPS.md) | The maps in `autoware_map/`, what each file is for, and what to check before adding another one. |
| [`docs/SETUP_STATE.md`](docs/SETUP_STATE.md) | Setup state and handover notes: what is configured, what is not, and where each subsystem stands. Read this first when resuming work. |
| [`docs/VEHICLE_CAN_AND_RUNTIME.md`](docs/VEHICLE_CAN_AND_RUNTIME.md) | CAN bring-up and the runtime picture from a real launch: interfaces, topics, and what has to be running before autonomy engages. |
| [`docs/RTK_ICHIMILL_SETUP.md`](docs/RTK_ICHIMILL_SETUP.md) | RTK corrections over SoftBank ichimill, both the `str2str` relay and the receiver's built-in NTRIP client. |
| [`docs/PIXKIT_MERGE_OVERWRITTEN_FILES.txt`](docs/PIXKIT_MERGE_OVERWRITTEN_FILES.txt) | The 180 upstream files the Pixkit extension copy overwrote in this tree. |
| [`docs/README_PIXKIT_EXTENSIONS.md`](docs/README_PIXKIT_EXTENSIONS.md) | The Pixkit extension repository's own README, kept as it was received. |
| [`docs/README_UPSTREAM_AUTOWARE.md`](docs/README_UPSTREAM_AUTOWARE.md) | The upstream Autoware README, replaced at the root by this file. |

The Ouster driver documents itself in
[`src/sensor_component/external/autoware_ouster_ros/README.md`](src/sensor_component/external/autoware_ouster_ros/README.md).

### Upstream

- [Autoware documentation](https://autowarefoundation.github.io/autoware-documentation/main/)
- [Autoware Foundation](https://www.autoware.org/)
- [Pixkit extensions upstream](https://github.com/tlab-wide/Pixkit_Autoware)

## License

Apache License 2.0, as [upstream Autoware](https://github.com/autowarefoundation/autoware/blob/main/LICENSE).
See [`LICENSE`](LICENSE).
