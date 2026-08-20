# Sensors

One page per sensor, covering how it is addressed, where it is configured, what it publishes and
what to change when the hardware moves to another vehicle.

| Sensor | Status | Address | Page |
| ------ | ------ | ------- | ---- |
| Ouster OS-1-128 lidar | **in use** | `192.168.1.126` | [OUSTER_OS1.md](sensors/OUSTER_OS1.md) |
| CHC CGI-410 GNSS / INS | **in use** | `192.168.1.110` | [CHC_CGI410.md](sensors/CHC_CGI410.md) |
| USB camera (traffic light) | **in use** | `/dev/video2` | [CAMERA.md](sensors/CAMERA.md) |
| Velodyne VLP-16 ×4 | not fitted | `192.168.1.201`–`.204` | [VELODYNE_VLP16.md](sensors/VELODYNE_VLP16.md) |
| Ultrasonic radar, ARS408 | not enabled | over CAN | [ULTRASONIC_RADAR.md](sensors/ULTRASONIC_RADAR.md) |

The vehicle interface itself is not a sensor but is on the same list of things that have to be up
before anything moves: see [VEHICLE_CAN_AND_RUNTIME.md](VEHICLE_CAN_AND_RUNTIME.md).

## Sensor LAN

Everything on ethernet shares one segment with the host at `192.168.1.100/24`, static and with
**no gateway**, so the default route stays on wifi or USB ethernet.

| Device | Address | Ports |
| ------ | ------- | ----- |
| This PC (`enp3s0`) | `192.168.1.100/24` | — |
| Ouster OS-1-128 | `192.168.1.126` | web `80`, data `7501`, lidar UDP `38672`, imu UDP `48215` |
| CHC CGI-410 | `192.168.1.110` | web `80`, NMEA TCP `9904` |
| Velodyne VLP-16 ×4 (absent) | `192.168.1.201`–`.204` | data UDP `2368`–`2371` |

Do not assign `.102`, `.110`, `.125`, `.126` or `.200`. Two of those are in use, and the other
three appear in configuration files that are still around.

Because the segment has no gateway, a device that needs the internet — the GNSS receiver reaching
the NTRIP caster — is routed by `pixkit-sensor-nat.service`, which masquerades `192.168.1.0/24`
out of the default-route interface. See [SETUP_STATE.md](SETUP_STATE.md).

## Common tasks

**Which sensors does a launch actually start?** `sensing.launch.xml` in the sensor kit is the top
of the tree: lidar, IMU, GNSS and camera are included, ultrasonic radar is commented out.

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
