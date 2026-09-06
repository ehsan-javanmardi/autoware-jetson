# Autoware on Jetson

Autoware workspace for an **NVIDIA Jetson AGX Orin**, driving a
**[Segway RMP Plus 401](docs/SEGWAY_HARDWARE.md)** mobile base.

This is an upstream Autoware source tree with sensor drivers and a vehicle integration
merged in. Everything upstream Autoware does still applies; this file documents only what
is specific to this workspace.

> [!NOTE]
> **Driving is not yet tested.** The vehicle interface talks to the chassis and publishes
> status, remote drive is implemented, and both steering modes switch — but nothing has
> moved the robot under its own power yet. Read [Safety](#safety) before the first drive.

---

## Quick start

| I want to… | Go to |
|---|---|
| Install on a fresh Jetson | [Install](#install) · [docs/INSTALL.md](docs/INSTALL.md) |
| Open the web UI | [Web UI](#web-ui) — `http://<jetson>:8842` |
| Drive it by hand | [Web UI](#web-ui), Remote drive tab |
| Run the robot | `./segway.sh` — see [docs/RUNNING.md](docs/RUNNING.md) |
| Launch Autoware | [Running Autoware](#running-autoware) |
| Watch topics on a tablet | [`foxglove/README.md`](foxglove/README.md) |
| Talk to the Segway | [docs/SEGWAY_CONNECTING.md](docs/SEGWAY_CONNECTING.md) |
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

The Segway RMP Plus 401 connects over USB serial at 921600 baud.

```
Segway RMP 401 ──8-pin, TX/RX/GND──▶ CP2102 ──USB──▶ Jetson /dev/segway @ 921600
```

`/dev/segway` is a udev symlink, not `/dev/ttyUSB0`. The converter re-enumerates whenever
the cable is disturbed and does not come back on the same number — it was seen moving from
`ttyUSB0` to `ttyUSB1` when the robot was lifted, which presents as a chassis that has
stopped replying rather than as a missing port.

`segway_vehicle_interface` owns that port and publishes the chassis to ROS. See
[`docs/SEGWAY_VEHICLE_INTERFACE.md`](docs/SEGWAY_VEHICLE_INTERFACE.md) for the interface,
[`docs/VEHICLE_SEGWAY.md`](docs/VEHICLE_SEGWAY.md) for dimensions and frames, and
[`docs/SEGWAY_HARDWARE.md`](docs/SEGWAY_HARDWARE.md) for wiring.

> [!WARNING]
> **Only one process may open the chassis.** The vendor SDK does not arbitrate serial
> access and does not report a conflict: a second opener gets a success return and then
> reads `0xffff` for everything, while degrading the link for the first. This makes
> [`tools/segway_dashboard/`](tools/segway_dashboard/) — which drives the SDK directly —
> unsafe to run while the vehicle interface is up. It is kept for standalone bring-up
> only. Use the [Web UI](#web-ui)'s Hardware tab instead, which reads ROS topics.

---

## Web UI

One page, on the Jetson, for hardware status, Foxglove, Autoware and remote driving.

```bash
./segway.sh        # sensors, chassis, web UI and Foxglove; Autoware started from the UI
```

or, if you want them individually:

```bash
ros2 launch segway_web_ui      web_ui.launch.xml       # the page,    :8842
ros2 launch segway_web_control web_control.launch.xml  # the buttons, :8843
```

Open **`http://<jetson>:8842`**. You never open 8843 — it is a JSON API the page calls in
the background.

| Tab | Sub-tabs | What it is for |
|---|---|---|
| **Hardware** | Sensors · Vehicle chassis | Is everything reachable and publishing |
| **Foxglove** | | Bridge state, and a button that opens Foxglove already connected |
| **Autoware** | Run · Health · Events · Destinations | Start/stop Autoware, diagnostics, engage, goals |
| **Remote drive** | | Joystick, battery, steering mode, E-stop |

It runs **independently of Autoware**: Hardware and Remote drive work whether or not
Autoware has ever been launched, and the tabs say so rather than showing blank panels.

The split into two processes is a safety boundary. `segway_web_ui` creates no ROS
publishers and no service clients at all, so it cannot command the vehicle whatever goes
wrong in it. `segway_web_control` owns every write path. Detail in
[`docs/WEB_UI.md`](docs/WEB_UI.md).

---

## Sensors

| Sensor | Where | Topic |
|---|---|---|
| **Livox HAP** lidar | `192.168.1.110`, wired to `eno1` (`192.168.1.101`) | `/sensing/lidar/top/livox/points` |
| **Livox HAP** IMU | same device | `/sensing/lidar/top/livox/imu` |
| **u-blox ZED-F9R** GNSS/RTK | USB, claimed by libusb — no `/dev` node | `/sensing/gnss/fix` |

The HAP is the IMU source as well as the lidar. The F9R has its own accelerometer and
gyro, but they are only reported over `UBX-ESF-RAW`, which `ublox_dgnss` does not
implement — reaching them would mean forking the driver. See
[`docs/LIVOX_HAP.md`](docs/LIVOX_HAP.md) and
[`docs/GNSS_IMU_UBLOX_F9R.md`](docs/GNSS_IMU_UBLOX_F9R.md).

RTK corrections come from SoftBank ichimill over NTRIP. Credentials are **not** in this
repository — it is public. They live in `~/.ichimill.env`; ask the platform owner.

Which lidar is launched is an argument, not a file edit:

```bash
./autoware_kashiwa.sh lidar_profile:=os1_128   # livox (default) | os1_128 | os2_32 | velodyne
```

The two Ouster lidars and the CHC CGI-410 GNSS/INS belong to the Pixkit platform this tree
was forked from. Their profiles still work if one is connected, but neither is fitted, and
`192.168.1.110` is now the Livox rather than the CHC. Pinging that address is **not** a
test that a particular sensor is present — the driver's own startup log is.

See [`docs/SENSORS.md`](docs/SENSORS.md) for the address map.

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

Ubuntu 22.04 with ROS 2 Humble. Measured on this Orin: `build/` 5.2 GB, `install/`
405 MB, ONNX artifacts 3.7 GB — about 15 GB all in, and roughly three hours of build time
at `--parallel-workers 6`.

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
| [`autoware_kashiwa.sh`](autoware_kashiwa.sh) | **The everyday one.** Autoware with the Livox HAP, the Segway vehicle interface, and the GNSS. |
| [`autoware_kashiwa_v2x.sh`](autoware_kashiwa_v2x.sh) | The same, plus `use_v2x_objects:=true`. Needs the [racing_kart_v2x](https://github.com/ehsan-javanmardi/racing_kart_v2x) stack running alongside — see [`docs/V2X.md`](docs/V2X.md). |
| [`autoware_kashiwa_os1_128.sh`](autoware_kashiwa_os1_128.sh) | Forces the Ouster OS-1-128. Kept from the Pixkit platform; that lidar is not fitted. |

All three pass `vehicle_model:=segway` and `sensor_model:=segway_sensor_kit`.

**They start the sensors and the vehicle interface too**, so do not also launch those
separately — you would get two Livox drivers and two processes fighting over the chassis
serial port. The web UI and the Foxglove bridge are separate and must be started by hand.

```bash
./autoware_kashiwa.sh                          # autoware_map/, Livox HAP
./autoware_kashiwa_v2x.sh                      # with V2X objects enabled
./autoware_kashiwa.sh /path/to/another/map     # a different map
./autoware_kashiwa.sh log_level:=warn          # quieter; default is debug
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
> **A full-stack launch can move the robot.** `./autoware_kashiwa.sh` brings up the
> vehicle interface with `allow_control:=true`. Engaging Autoware, or arming remote drive,
> will drive the base.
>
> This is deliberate. The previous default could not move at all, which meant Autoware
> would plan, engage and command control with every layer reporting healthy while the
> robot sat still — a worse failure, because nothing looked wrong.

To bring the stack up with **no possibility of motion**, launch the interface on its own:

```bash
ros2 launch segway_vehicle_interface segway_vehicle_interface.launch.xml
```

Without `allow_control:=true` the SDK's write functions are never bound, so there is no
callable path to motion in the process at all.

### What actually stops the robot

In order of how much you should trust them:

1. **The chassis E-stop.** The only thing that cuts motor power. Nothing in software
   substitutes for it.
2. **The RC's enable switch.** Manual: down enables the chassis, up disables it.
3. **The 0.5 s command watchdog** in the vehicle interface. If commands stop arriving —
   a crashed planner, a closed browser, a dropped wifi link — the command is zeroed. This
   matters more here than on a car: the chassis holds its last velocity indefinitely, so
   without it a crashed planner leaves the robot driving.
4. **The E-STOP button** in the web UI. Zeroes the command and disables the motors. It is
   software over wifi, so it is the last of these, not the first.

### Before the first drive

- Wheels off the ground, or the E-stop in your hand.
- Check the RC's sticks are centred and its enable switch is where you expect. A chassis
  in vehicle-control mode follows whatever input has control, and an off-centre stick has
  already caused the robot to turn on its own here.
- `livox_frame`'s mounting height is derived from the manual's geometry, **not measured**.
  Ground segmentation reads it as height above `base_link`, so an error there misplaces
  the ground plane. See [`docs/VEHICLE_SEGWAY.md`](docs/VEHICLE_SEGWAY.md).

### Steering modes

The RMP steers its **front wheels** and cannot turn tighter than a 1.36 m radius, so it
must be moving to turn. It also supports spinning on the spot, but the manual warns of
excessive rear-wheel current and a locked-rotor alarm after about 5 seconds, so the
interface stops a spin at 5 s. Ackermann is the default; spin-in-place is a manoeuvre you
select deliberately in the Remote drive tab.

---

## What is in this workspace

Upstream `autoware` at tag 1.9.0 ships 458 packages in `src/`. This workspace builds
**514**, with 7 excluded via `COLCON_IGNORE`.

<details>
<summary><b>Added — vehicle integration</b> (inherited from the Pixkit tree)</summary>

| Package | Location | Purpose |
| ------- | -------- | ------- |
| `segway_vehicle_interface` | `src/vehicle/external/segway_vehicle_interface/` | **The vehicle interface in use.** Wraps the vendor SDK over serial |
| `segway_launch`, `segway_description` | `src/launcher/autoware_launch/vehicle/segway_launch/` | Vehicle model from the RMP manual. Selected by `vehicle_model:=segway` |
| `pix_hooke_driver`, `pix_hooke_driver_msgs` | `src/vehicle/external/pix_driver/` | Pixkit CAN interface. Still built, no longer launched |
| `pixkit_launch`, `pixkit_description` | `src/launcher/autoware_launch/vehicle/pixkit_launch/` | Pixkit vehicle model. Still built, no longer launched |
| `segway_sensor_kit_launch`, `segway_sensor_kit_description` | `src/launcher/autoware_launch/sensor_kit/segway_sensor_kit_launch/` | Sensor kit: extrinsics and bring-up. Selected by `sensor_model:=segway_sensor_kit` |

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
- **`yabloc_image_processing` exec_depend dropped** from `tier4_localization_launch` —
  colcon skips any package with an unavailable declared dependency, so the ignore above
  otherwise cascades to `tier4_simulator_launch` and then `autoware_launch` itself.
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
