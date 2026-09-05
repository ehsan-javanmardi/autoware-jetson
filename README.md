# Autoware on Jetson

Autoware workspace for an **NVIDIA Jetson AGX Orin**, driving a
**[Segway RMP Plus 401](docs/SEGWAY_HARDWARE.md)** mobile base.

This is an upstream Autoware source tree with sensor drivers and a vehicle integration
merged in. Everything upstream Autoware does still applies; this file documents only what
is specific to this workspace.

> [!NOTE]
> **Segway bring-up is in progress.** The serial link to the chassis works and telemetry
> is live, but there is no Segway ROS 2 driver in `src/` yet. The vehicle interface
> committed there is still `pix_driver`, inherited from the Pixkit tree this was forked
> from — see [What is in this workspace](#what-is-in-this-workspace).

---

## Quick start

| I want to… | Go to |
|---|---|
| Install on a fresh Jetson | [Install](#install) · [docs/INSTALL.md](docs/INSTALL.md) |
| Talk to the Segway | [docs/SEGWAY_CONNECTING.md](docs/SEGWAY_CONNECTING.md) |
| See the chassis telemetry | [tools/segway_dashboard/](tools/segway_dashboard/) |
| Launch Autoware | [Running Autoware](#running-autoware) |
| Find a document | [docs/README.md](docs/README.md) |

```bash
git clone git@github.com:ehsan-javanmardi/autoware-jetson.git
cd autoware-jetson
bash install-jetson.sh 2>&1 | tee ~/autoware-jetson-install.log
```

---

## Platform

| | |
| --- | --- |
| Host | NVIDIA Jetson AGX Orin Developer Kit (`aarch64`) |
| L4T | R36.x (JetPack 6), kernel `5.15.185-tegra` |
| OS | Ubuntu 22.04 LTS |
| ROS | ROS 2 Humble |
| RMW | CycloneDDS (`rmw_cyclonedds_cpp`) |
| CUDA | 12.6 (`nvcc` 12.6.68) — from JetPack, at `/usr/local/cuda` |
| TensorRT | 10.3.0.30-1+cuda12.5 — from JetPack |

The NVIDIA stack comes from JetPack and is versioned with L4T. **Do not install CUDA,
cuDNN or TensorRT from NVIDIA's generic Ubuntu repositories on this machine** — see
[`docs/INSTALL.md`](docs/INSTALL.md).

### Versions

| Component | Version |
| --------- | ------- |
| **Autoware** (this repo) | **1.9.0** (tag, detached HEAD — commit `1071878`) |
| `autoware_core` | 1.9.0 |
| `autoware_universe` | 0.52.0 |
| `autoware_launch` | 0.52.0 |
| `autoware_utils` | 1.9.0 |
| Vehicle/sensor extensions | [tlab-wide/Pixkit_Autoware](https://github.com/tlab-wide/Pixkit_Autoware), merged 2026-08-20 |

> [!IMPORTANT]
> The merged extensions were authored against **Autoware 0.45.1** but sit here in
> **1.9.0**. Exposure is limited: the merge replaces only sensor drivers and sensor
> descriptions, and **no core Autoware package is replaced**. Expect any incompatibility
> to surface first in the vehicle interface or launch configuration, not in planning or
> control.

---

## The robot

The Segway RMP Plus 401 connects over USB serial at 921600 baud. The link is up and
reporting battery, mode, odometry and per-board error state.

```
Segway RMP 401 ──8-pin, TX/RX/GND──▶ CP2102 ──USB──▶ Jetson /dev/ttyUSB0 @ 921600
```

A read-only web dashboard shows all of it, with an optional touch control tab for driving
from a phone:

```bash
cd tools/segway_dashboard
sudo ./server.py --lib /home/tlab/workspace/segway_ros2/segwayrmp/lib/libctrl_arm64-v8a.so
```

Then open `http://<jetson>:8080/`. Full detail in
[`tools/segway_dashboard/README.md`](tools/segway_dashboard/README.md); wiring and
troubleshooting in [`docs/SEGWAY_HARDWARE.md`](docs/SEGWAY_HARDWARE.md); every way to
reach the machine in [`docs/SEGWAY_CONNECTING.md`](docs/SEGWAY_CONNECTING.md).

---

## Sensors

Two Ouster lidars share the top mount and run one at a time — an **OS-1-128** at
`192.168.1.126` and an **OS-2-32** at `192.168.1.120` — alongside a CHC CGI-410 GNSS/INS at
`192.168.1.110` and a USB camera for traffic lights. The four VLP-16s of the stock
configuration are not fitted.

Which lidar is launched is an argument, not a file edit:

```bash
./autoware_kashiwa.sh autoware_map lidar_profile:=os2_32   # os1_128 | os2_32 | velodyne
```

See [`docs/SENSORS.md`](docs/SENSORS.md) for the address map and a page per sensor.

---

## Maps

A point cloud map and a lanelet2 map are committed in [`autoware_map/`](autoware_map):
Kashiwanoha Campus, MGRS grid `54SVE`, 22 MB.

```text
autoware_map/
├── pointcloud_map.pcd          loaded as-is
├── lanelet2_map.osm            loaded as-is
├── map_projector_info.yaml
└── other_maps/                 variants, off the search path
```

**Nothing is auto-detected.** The launchers load exactly those two filenames. To drive a
different road network, copy it over `lanelet2_map.osm`; to use a map elsewhere, pass its
directory as the first argument to any launcher.

The map in place has every traffic light and stop line removed — with no camera, Autoware
reads every signal as unknown and holds at the stop line forever. See
[`docs/MAPS.md`](docs/MAPS.md).

---

## Install

Ubuntu 22.04 with ROS 2 Humble, about 40 GB of disk (`build/` alone is ~4.5 GB), and two
to three hours of build time on the Orin at `--parallel-workers 4`.

`src/` is committed in this repository, so **there is no `vcs import` step**. Every
package is already at the revision recorded in
[`repositories/imported-revisions.repos`](repositories/imported-revisions.repos).

### On the Jetson

```bash
bash install-jetson.sh 2>&1 | tee ~/autoware-jetson-install.log
```

That is the whole install. It covers prerequisites, system dependencies, the duplicate
check and the build.

> [!IMPORTANT]
> **Do not run the generic Ansible playbook on the Jetson.** Its `cuda` role treats every
> non-x86 host as SBSA: it adds NVIDIA's server-ARM apt repository and installs
> `nvidia-open`, a discrete-GPU driver, over the L4T stack JetPack installed. The
> `tensorrt` role does the equivalent to TensorRT. `install-jetson.sh` skips both,
> verifies JetPack's versions are present, and isolates two further roles that cannot
> work on a `-tegra` kernel. [`docs/INSTALL.md`](docs/INSTALL.md) explains each deviation.

If a stage fails, the script prints a resume command:

```bash
START_STAGE=7 bash install-jetson.sh
```

### On an x86 host

The standard Autoware Ansible playbook installs the prerequisites:

```bash
bash ansible/scripts/install-ansible.sh
ansible-galaxy collection install -f -r ansible-galaxy-requirements.yaml
ansible-playbook autoware.dev_env.install_dev_env

source /opt/ros/humble/setup.bash
rosdep update
rosdep install -y --from-paths src --ignore-src --rosdistro "$ROS_DISTRO"

colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
```

### Check for duplicate packages first

> [!IMPORTANT]
> This is the step that is easy to skip and expensive to debug. A package that exists
> **both** in `src/` and as a `ros-humble-*` Debian package will usually build against the
> wrong one.

### Build troubleshooting

| Symptom | Cause and fix |
| ------- | ------------- |
| `rosdep` aborts with `Multiple packages found with the same name "..."` | Two copies of the same package under `src/`. `catkin_pkg` refuses to scan such a tree. Delete or `COLCON_IGNORE` the copy that does not belong. |
| `no matching function for call to ...`, header under `/opt/ros/humble/include` but `.cpp` under `src/` | A Debian package is shadowing its source counterpart. Go back to the duplicate check. |
| `Could not find a package configuration file provided by "X"`, and `X` is in `src/` and built | `CMakeLists.txt` calls `find_package(X)` but `package.xml` does not declare it. colcon only exposes **declared** dependencies. Add `<depend>X</depend>`. |

---

## Running Autoware

Three launcher scripts sit at the workspace root. Each takes an optional map directory as
its first argument and forwards anything containing `:=` to `ros2 launch`.

| Script | What it starts |
| ------ | -------------- |
| [`autoware_kashiwa_os1_128.sh`](autoware_kashiwa_os1_128.sh) | Autoware with the Ouster OS-1-128 as the only lidar. The everyday one. |
| [`autoware_kashiwa_v2x.sh`](autoware_kashiwa_v2x.sh) | The same, plus `use_v2x_objects:=true`. Needs the [racing_kart_v2x](https://github.com/ehsan-javanmardi/racing_kart_v2x) stack running alongside — see [`docs/V2X.md`](docs/V2X.md). |
| [`autoware_kashiwa.sh`](autoware_kashiwa.sh) | The general-purpose launcher. Use it for any other combination. |

```bash
./autoware_kashiwa_os1_128.sh                       # autoware_map/, OS-1-128
./autoware_kashiwa_v2x.sh                           # with V2X objects enabled
./autoware_kashiwa_os1_128.sh /path/to/another/map  # a different map
./autoware_kashiwa_v2x.sh log_level:=warn           # quieter; default is debug
```

Each script is self-contained rather than wrapping the others, so editing one leaves the
rest alone — at the cost of the map handling and DDS setup being repeated in all three.

### Making the output readable

Autoware writes thousands of lines at startup, uncoloured — colour is auto-detected and
switched off whenever output is not a terminal, which is exactly what `ros2 launch` does
when it captures each node's stdout. Force it on:

```bash
export RCUTILS_COLORIZED_OUTPUT=1          # WARN yellow, ERROR red
export RCUTILS_CONSOLE_OUTPUT_FORMAT='[{severity}] [{name}]: {message}'
```

The launch scripts pass `log_level:=debug`, which is the main reason the terminal is
unreadable. Override with `log_level:=warn`. For an already-captured log, the escape codes
are not in it, so colour on the way out:

```bash
grep --color=always -E "ERROR|WARN|$" run.log | less -R
```

---

## Safety

> [!WARNING]
> **The vehicle interface can command motion.** `pix_driver` publishes to `/to_can_bus` as
> soon as Autoware runs. Both PEAK PCAN-USB FD interfaces (`can0`, `can1`) come up `DOWN`
> and ROS does not configure them, so nothing reaches a chassis controller until CAN is
> brought up by hand:
>
> ```bash
> sudo ip link set can0 up type can bitrate 500000
> ```
>
> Bring CAN up only with the vehicle in a safe state.

For the Segway, the software STOP button in the dashboard is **not** a substitute for the
hardware E-stop, which is the only thing that cuts motor power. See
[`tools/segway_dashboard/README.md`](tools/segway_dashboard/README.md).

---

## What is in this workspace

Upstream `autoware` at tag 1.9.0 ships 458 packages in `src/`. This workspace has **497**
(**492 buildable**, 5 excluded via `COLCON_IGNORE`).

<details>
<summary><b>Added — vehicle integration</b> (inherited from the Pixkit tree)</summary>

| Package | Location | Purpose |
| ------- | -------- | ------- |
| `pix_hooke_driver`, `pix_hooke_driver_msgs` | `src/vehicle/external/pix_driver/` | Vehicle interface — CAN control and status |
| `pixkit_launch`, `pixkit_description` | `src/launcher/autoware_launch/vehicle/pixkit_launch/` | Vehicle model: URDF, mesh, calibration. Selected by `vehicle_model:=pixkit` |
| `pixkit_sensor_kit_launch`, `pixkit_sensor_kit_description` | `src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/` | Sensor kit: extrinsics and bring-up. Selected by `sensor_model:=pixkit_sensor_kit` |

These sit alongside upstream's `sample_vehicle_launch` and `sample_sensor_kit_launch`.
**They still describe the Pixkit vehicle, not the Segway** — replacing them is the
outstanding work in the Segway port.

</details>

<details>
<summary><b>Added — sensor drivers</b></summary>

Built from source in `src/sensor_component/external/`:

- **LiDAR** — `velodyne_vls`, `rslidar_sdk` + `rslidar_msg`, `nebula`
- **GNSS / IMU** — `fixposition_driver`, `fixposition_gnss_tf`, `nmea_navsat_driver`, `tamagawa_imu_driver`
- **Radar / ultrasonic** — `pe_ars408_ros` (Continental ARS408), `ultra_sonic_radar_driver`, `ultra_sonic_radar_detector`

19 packages, of which 14 are built. `nebula`, `sensor_component_description`,
`sync_tooling_msgs`, `ros2_socketcan` and `transport_drivers` come from `autoware.repos`,
not from the merged extensions.

</details>

<details>
<summary><b>Added — Autoware-compatible Ouster driver</b></summary>

`src/sensor_component/external/autoware_ouster_ros/` — a standalone repository,
[ehsan-javanmardi/autoware_ouster_ros](https://github.com/ehsan-javanmardi/autoware_ouster_ros),
forked from [ouster-lidar/ouster-ros](https://github.com/ouster-lidar/ouster-ros) v0.13.9.

It adds a `point_type: xyzircaedt` that publishes `autoware::point_types::PointXYZIRCAEDT`
directly. Autoware validates an incoming cloud by field name, datatype **and byte offset**,
and a cloud that does not match is not rejected but silently reduced to x/y/z — dropping
intensity, channel and per-point timestamps, and with them distortion correction and the
ring-based outlier filters. No point type the stock driver offers matches that layout.

</details>

<details>
<summary><b>Replaced and locally modified</b></summary>

Nine packages were overwritten in place (same paths, so no duplicates): `ros2_socketcan`,
`ros2_socketcan_msgs`, and the seven `*_description` packages under
`sensor_component_description`. 106 files total, confined to `src/sensor_component/`.
**No `autoware_core` or `autoware_universe` package was modified.**

Local modifications:

- **`COLCON_IGNORE`** on `rslidar_msg/{ros1,ros2}` — three copies declare the same `<name>`.
- **Ouster driver replaced** with the Autoware-compatible fork; bring-up turns off the
  driver's static transforms and organized cloud, both of which break the pipeline.
- **Single Ouster configuration** — `lidar.launch.xml` brings up the one OS-1 actually
  mounted instead of four VLP16s, and `activate_lifecycle_node.sh` drives lifecycle
  transitions instead of a `sleep` that loses the race on a busy machine.
- **`can1` launch files** added for the second CAN interface.
- **`fixposition_driver_ros2` manifest completed** — it called `find_package` on four
  packages it never declared, so it built only while a Debian copy happened to be installed.
- **`COLCON_IGNORE`** on `yabloc_image_processing` — needs OpenCV contrib's `ximgproc`,
  absent from JetPack's OpenCV 4.8.0 build and not installable beside it. Costs YabLoc
  camera localization, which needs a camera this vehicle does not have.
- **`casadi` pinned to 3.7.2** — 3.8.0's aarch64 wheel needs `GLIBCXX_3.4.32` (GCC 13);
  jammy provides at most 3.4.30, so every acados codegen step failed at `import casadi`.
- **`cuda_blackboard` guarded for CUDA 12.6** — `cudaStreamGetDevice()` arrived in CUDA
  12.8; JetPack 6 ships 12.6 and its toolkit is versioned with L4T. Without the guard,
  `cuda_blackboard` fails to compile and takes the entire CUDA perception stack with it.
- **Launch scripts rewritten** — the upstream copies hardcoded an absolute home directory.

</details>

---

## Documentation

**[docs/README.md](docs/README.md)** is the index, organised by task: setting up the
machine, the robot base, sensors, running Autoware, and how the software fits together.

## Provenance

This tree was assembled by cloning `autowarefoundation/autoware` at tag **1.9.0** (commit
`1071878`), importing `repositories/autoware.repos`, and copying the
`tlab-wide/Pixkit_Autoware` extensions over the result. The git metadata of the imported
repositories was removed so the whole workspace could live in a single repository;
[`repositories/imported-revisions.repos`](repositories/imported-revisions.repos) is what
makes that reversible, naming the exact commit every package came from.

The x86 tree this was forked from is
[`ehsan-javanmardi/pix_autoware`](https://github.com/ehsan-javanmardi/pix_autoware),
configured here as the `upstream` remote.

## License

Apache License 2.0, as [upstream Autoware](https://github.com/autowarefoundation/autoware/blob/main/LICENSE).
See [`LICENSE`](LICENSE).
