# Documentation

Everything written for this workspace, grouped by what you are trying to do. Start at the
section that matches your task rather than reading top to bottom.

---

## 1. Getting the machine running

New Jetson, or rebuilding one from scratch.

**[INSTALL.md](INSTALL.md)** — Installing on the Jetson AGX Orin. The generic Autoware
Ansible playbook will install a discrete-GPU NVIDIA stack over the one JetPack put there,
so two roles are skipped and two more isolated. This explains each deviation, walks
through the nine stages of [`install-jetson.sh`](../install-jetson.sh), and shows how to
resume a failed stage without redoing the finished work.

**[WORKSPACE_VERSIONS.md](WORKSPACE_VERSIONS.md)** — Keeping the version that works on the
robot buildable while developing the next one. Uses a second working copy rather than
branch switching, because a half-built `install/` is worse than a stale one.

---

## 2. The robot base

The Segway RMP Plus 401 that this workspace drives.

**[SEGWAY_HARDWARE.md](SEGWAY_HARDWARE.md)** — Start here. What the chassis is, how it is
wired, and how the link was brought up. Contains the connector pinout that matters most:
only pins 3, 4 and 5 of the 8-pin connector are the serial port, the ground is the *white*
wire rather than the black one, and TX/RX are named from the chassis's point of view. Also
covers the 921600 baud rate (which appears nowhere in the manual), how to probe the
chassis read-only, and the vendor SDK's version-mismatch warning.

**[SEGWAY_CONNECTING.md](SEGWAY_CONNECTING.md)** — Once it works: every route to the
Jetson (Tailscale from anywhere, lab WiFi, the direct LAN cable), how to start and stop the
dashboard server, the RC handset's switches and how to map them to your own transmitter,
and how to drive from a phone or tablet.

**[../tools/segway_dashboard/](../tools/segway_dashboard/)** — The web dashboard itself:
live telemetry, and an optional touch control tab. Its README documents the JSON API and
the four independent layers that stop the chassis when something goes wrong.

The manual is committed here as
[`user-manual-for-rmp-plus-401-20230301.pdf`](user-manual-for-rmp-plus-401-20230301.pdf),
because the vendor's CDN blocks automated downloads.

---

## 3. Sensors

**[SENSORS.md](SENSORS.md)** — The index: what is fitted, the sensor LAN address map, and
how `lidar_profile` selects between them without editing files.

Then one page per sensor, each covering its addressing, configuration files, topics and
frames:

| | |
|---|---|
| [OUSTER_OS1_128.md](sensors/OUSTER_OS1_128.md) | The everyday lidar |
| [OUSTER_OS2_32.md](sensors/OUSTER_OS2_32.md) | The alternate lidar; shares the top mount |
| [CHC_CGI410.md](sensors/CHC_CGI410.md) | GNSS/INS, two antennas — Pixkit platform, not fitted to the Jetson |
| [CAMERA.md](sensors/CAMERA.md) | USB camera for traffic lights |
| [VELODYNE_VLP16.md](sensors/VELODYNE_VLP16.md) | Not fitted; kept for the stock configuration |
| [ULTRASONIC_RADAR.md](sensors/ULTRASONIC_RADAR.md) | Ultrasonic and Continental ARS408 |

**[../foxglove/README.md](../foxglove/README.md)** — Watching Autoware from an iPad without
RViz: the bridge, why the topic allow list is deliberate rather than `.*`, and how to change
what is exposed.

**[SEGWAY_VEHICLE_INTERFACE.md](SEGWAY_VEHICLE_INTERFACE.md)** — Autoware's vehicle
interface for the RMP: how a bicycle-model steering command becomes a differential-drive
yaw rate, the three safety properties, and why the vendor headers cannot be trusted about
which symbols exist.

**[LIVOX_HAP.md](LIVOX_HAP.md)** — The Livox HAP: what had to be vendored and why a plain
`colcon build` could not do it alone, the JSON that holds the device address, the
`xfer_format` that decides whether Autoware can read the cloud at all, and why the IMU
comes from here rather than from the GNSS receiver.

**[GNSS_IMU_UBLOX_F9R.md](GNSS_IMU_UBLOX_F9R.md)** — The SparkFun GPS-RTK Dead Reckoning
kit (u-blox ZED-F9R) on the Jetson: which ROS 2 driver actually closes the NTRIP loop over
USB and why the obvious one does not, RTK over ichimill, and what the receiver does and
does not give Autoware. **Start here for GNSS on this platform.**

**[GNSS_RTK.md](GNSS_RTK.md)** — RTK corrections over SoftBank ichimill for the **CHC
CGI-410** over Ethernet, both via a `str2str` relay and via the receiver's own built-in
NTRIP client. Pixkit platform; none of its network setup applies to a USB receiver.

---

## 4. Running Autoware

**[MAPS.md](MAPS.md)** — What is in `autoware_map/`, what each variant contains as
measured, what the traffic-light edit removed and why, and what to check before committing
a new map. Nothing is auto-detected: the launchers load two files by exact name.

**[V2X.md](V2X.md)** — Accepting vehicles reported over V2X as detected objects: the
`use_v2x_objects` flag, why they need a topic of their own, and how to see them.

---

## 5. How the software fits together

Read these when something is not behaving and you need to know where to look.

**[LAUNCHING.md](LAUNCHING.md)** — How a launch gets from `autoware.launch.xml` to a point
cloud: which file includes which, how `sensor_model` selects this workspace's packages,
where the namespaces come from, and how the shared pointcloud container is filled.

**[components/LOCALIZATION.md](components/LOCALIZATION.md)** — What estimates the pose:
GNSS for initialization, NDT and gyro odometry for the running estimate, and what each
initialization failure actually means.

**[components/PERCEPTION.md](components/PERCEPTION.md)** — The detection stack and the
point-cloud contract it depends on. Explains why a cloud with the wrong field layout is
silently reduced to x/y/z rather than rejected.

**[components/PLANNING_CONTROL.md](components/PLANNING_CONTROL.md)** — Route to trajectory
to vehicle command, what must be true before anything moves, and how to run with no
possibility of movement.

---

## 6. Reference

**[UPSTREAM_AUTOWARE.md](UPSTREAM_AUTOWARE.md)** — The upstream Autoware README, which
this workspace's [root README](../README.md) replaces.

The Ouster driver documents itself in
[`src/sensor_component/external/autoware_ouster_ros/README.md`](../src/sensor_component/external/autoware_ouster_ros/README.md)
— the `xyzircaedt` point type, the `intensity_source` parameter, and the Autoware preset
parameter file.

External:
[Autoware documentation](https://autowarefoundation.github.io/autoware-documentation/main/)
· [Autoware Foundation](https://www.autoware.org/)
