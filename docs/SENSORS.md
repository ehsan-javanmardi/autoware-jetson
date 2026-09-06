# Sensors

One page per sensor, covering how it is addressed, where it is configured, what it publishes and
what to change when the hardware moves to another vehicle.

| Sensor | Status | Address | Page |
| ------ | ------ | ------- | ---- |
| Ouster OS-1-128 lidar | **in use** | `192.168.1.126` | [OUSTER_OS1_128.md](sensors/OUSTER_OS1_128.md) |
| Ouster OS-2-32-U3 lidar | **in use** | `192.168.1.120` | [OUSTER_OS2_32.md](sensors/OUSTER_OS2_32.md) |
| CHC CGI-410 GNSS / INS | **in use** | `192.168.1.110` | [CHC_CGI410.md](sensors/CHC_CGI410.md) |
| USB camera (traffic light) | **in use** | `/dev/video2` | [CAMERA.md](sensors/CAMERA.md) |
| Velodyne VLP-16 ×4 | not fitted | `192.168.1.201`–`.204` | [VELODYNE_VLP16.md](sensors/VELODYNE_VLP16.md) |
| Ultrasonic radar, ARS408 | not enabled | over CAN | [ULTRASONIC_RADAR.md](sensors/ULTRASONIC_RADAR.md) |

The vehicle interface itself is not a sensor but is on the same list of things that have to be up
before anything moves.

## Sensor LAN

Everything on ethernet shares one segment with the host at `192.168.1.100/24`, static and with
**no gateway**, so the default route stays on wifi or USB ethernet.

| Device | Address | Ports |
| ------ | ------- | ----- |
| This PC (`enp3s0`) | `192.168.1.100/24` | — |
| Ouster OS-1-128 | `192.168.1.126` | web `80`, data `7501`, lidar UDP `38672`, imu UDP `48215` |
| Ouster OS-2-32-U3 | `192.168.1.120` | web `80`, data `7501`, lidar UDP `38672`, imu UDP `48215` |
| CHC CGI-410 | `192.168.1.110` | web `80`, NMEA TCP `9904` |
| Velodyne VLP-16 ×4 (absent) | `192.168.1.201`–`.204` | data UDP `2368`–`2371` |

The scheme is **`.100` the host**, `.110` GNSS, `.12x` lidars, `.20x` the legacy Velodynes. Do not
assign `.100`, `.110`, `.120`, `.125`, `.126`, `.102` or `.200`: the first four are in use, the
rest appear in configuration files that are still around.

`.100` is deliberately the host rather than a sensor. On a /24 the low round numbers read as
infrastructure, and a sensor sitting on one invites the mistake of pointing `host_ip` at it, which
tells the lidar to send its point cloud to another device and produces a driver that connects,
configures the sensor and then waits forever without an error.

Because the segment has no gateway, a device that needs the internet — the GNSS receiver reaching
the NTRIP caster — is routed by `pixkit-sensor-nat.service`, which masquerades `192.168.1.0/24`
out of the default-route interface.

## Sensor combinations

The lidar set changes between experiments: one Ouster, the other Ouster, the four Velodynes, or a
mixture. This is handled with a **`lidar_profile` argument inside the one sensor kit**, not with a
sensor kit per combination.

```bash
ros2 launch autoware_launch autoware.launch.xml \
    vehicle_model:=segway sensor_model:=segway_sensor_kit \
    map_path:=$PWD/autoware_map \
    lidar_profile:=os2_32
```

| Profile | Fitted lidars | Concat config |
| ------- | ------------- | ------------- |
| `os1_128` (default) | Ouster OS-1-128 at `.126` | `config/lidar_profiles/os1_128.param.yaml` |
| `os2_32` | Ouster OS-2-32 at `.120` | `config/lidar_profiles/os2_32.param.yaml` |
| `velodyne` | four VLP-16s at `.201`–`.204` | `config/lidar_profiles/velodyne.param.yaml` (untested) |

A profile decides two things, and they have to agree with each other:

1. **Which drivers start**, through `use_ouster` / `use_velodyne` and the address the Ouster
   driver is pointed at.
2. **Which clouds the concatenate node waits for.** `input_topics`, `lidar_timestamp_offsets` and
   `lidar_timestamp_noise_window` need one entry per cloud that will actually arrive. Too many
   entries and the node waits forever for a topic nobody publishes; mismatched array lengths are a
   startup error.

### Adding a combination

Copy an existing profile file, list every input topic, give each one an offset and a noise window,
and add the profile name to the `lidar_profile` conditions in
[`lidar.launch.xml`](../src/launcher/autoware_launch/sensor_kit/segway_sensor_kit_launch/segway_sensor_kit_launch/launch/lidar.launch.xml).
The conditions are plain string tests, so a name like `os1_128_velodyne` already starts the Ouster
(it starts with `os`) and the Velodynes (it contains `velodyne`) without any further edit — only
the matching `.param.yaml` has to exist.

Extrinsics do not need to be part of a profile. Every mount can have its own frame and its own
entry in `sensors_calibration.yaml`, and frames belonging to sensors that are not running simply
sit unused in the TF tree. The exception is two sensors sharing one physical mount, like the two
Ousters here: they share `os_lidar_top`, so that entry has to describe whichever unit is bolted on.

### Why not one sensor kit per combination

A sensor kit is the natural unit for **a vehicle**, not for a configuration of one vehicle. It
carries the GNSS, IMU, camera and CAN bring-up as well as the lidars, and none of that changes when
a lidar is swapped. Splitting by lidar set would copy `gnss.launch.xml`, `imu.launch.xml`,
`camera_launch.py`, `sensing.launch.xml` and the whole description package into every kit, and
those copies drift: a fix to the GNSS launch would have to be applied N times, and the one that
gets missed is discovered on the vehicle.

Make a second sensor kit when the **vehicle** differs — a different `base_link` geometry, a
different vehicle interface, a different set of non-lidar sensors. Use a profile when the same
vehicle carries a different lidar set.

## Common tasks

**Which sensors does a launch actually start?** `sensing.launch.xml` in the sensor kit is the top
of the tree: lidar, IMU, GNSS and camera are included, ultrasonic radar is commented out. See
[LAUNCHING.md](LAUNCHING.md) for how Autoware reaches that file and what happens after it.

**Add a sensor to the vehicle.** Three things have to line up, and forgetting any one of them
produces a silent failure rather than an error:

1. a driver launched from `sensing.launch.xml` or something it includes,
2. a frame declared in `sensors.xacro` **and** an extrinsic in `sensors_calibration.yaml`,
3. a consumer — for a lidar, an entry in the concatenate node's `input_topics`, whose
   `lidar_timestamp_offsets` and `lidar_timestamp_noise_window` arrays need one element per topic.

**Check what is publishing right now:**

```bash
ros2 topic list | grep sensing
ros2 topic hz /sensing/lidar/top/ouster/points
ros2 run tf2_tools view_frames        # writes a PDF of the frame tree
```
