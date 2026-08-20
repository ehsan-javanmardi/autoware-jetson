# Ouster OS-1-128 — 128 beam lidar

The 128 beam Ouster, and the default lidar of this workspace: `lidar_profile:=os1_128`. It runs
the [autoware_ouster_ros](https://github.com/ehsan-javanmardi/autoware_ouster_ros) driver, a fork
that publishes Autoware's point type natively.

## At a glance

| | |
| --- | --- |
| Model | Ouster OS-1, 128 beams |
| Address | `192.168.1.126` (mDNS `os-122345000355.local`, web UI `:80`, data `:7501`) |
| Host address | `192.168.1.100/24` on the sensor LAN, static, **no gateway** |
| UDP ports | lidar `38672`, imu `48215` |
| Mode | `1024x10`, profile `RNG19_RFL8_SIG16_NIR16` |
| Point type | `xyzircaedt` — `autoware::point_types::PointXYZIRCAEDT` |
| Topic | `/sensing/lidar/top/ouster/points` |
| Frames | `os_sensor_top` → `os_lidar_top`, `os_imu_top` |
| Driver | `src/sensor_component/external/autoware_ouster_ros/` |

## Where it is configured

| What | File |
| ---- | ---- |
| Which lidar is used at all | [`lidar.launch.xml`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_launch/launch/lidar.launch.xml) — `lidar_profile` (default `os1_128`), `os1_128_ip`, `host_ip` |
| Driver parameters | [`os_sensor_top.launch.xml`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_launch/launch/os_sensor_top.launch.xml) |
| Mounting position | [`sensors_calibration.yaml`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_description/config/sensors_calibration.yaml) — `base_link2os_lidar_top` |
| Frame declaration | [`sensors.xacro`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_description/urdf/sensors.xacro) |
| Which topic Autoware consumes | [`config/lidar_profiles/`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_launch/config/lidar_profiles/os1_128.param.yaml) |

The launch file sets six parameters that matter and that are easy to get wrong:

```xml
<param name="point_type"      value="xyzircaedt"/>   <!-- Autoware's point layout      -->
<param name="intensity_source" value="reflectivity"/> <!-- 0-255, on every udp profile  -->
<param name="organized"       value="false"/>         <!-- no NaN padding into the pipeline -->
<param name="pub_static_tf"   value="false"/>         <!-- the URDF owns the frames     -->
<param name="min_range"       value="0.5"/>
<param name="timestamp_mode"  value="TIME_FROM_ROS_TIME"/>
```

`organized` and `pub_static_tf` break the Autoware pipeline if left at their driver defaults: an
organized cloud emits one point per beam and column including the ones with no return, as NaN, and
the concatenate node copies them straight through; and the driver's own static transform for
`os_lidar_top` collides with the one the URDF publishes, giving that frame two parents on
`/tf_static` where the last message latched wins.

## Bringing it up on a new vehicle

1. **Wire and power it.** The sensor and the host must be on the same LAN segment. On this vehicle
   that is `enp3s0`.

2. **Give the host a static address on that LAN**, with no gateway, so the default route stays on
   wifi or the USB ethernet:

   ```bash
   nmcli con add type ethernet ifname enp3s0 con-name sensor-lan \
       ipv4.method manual ipv4.addresses 192.168.1.100/24 ipv4.never-default yes
   ```

   If the interface gets no IPv4 at all, see the NetworkManager note in
   [`SETUP_STATE.md`](../SETUP_STATE.md): Ubuntu ships `unmanaged-devices=*,except:type:wifi`,
   which leaves every wired NIC unmanaged, and `.local` names will not resolve either because
   avahi does not do IPv4 mDNS on an interface without an IPv4 address.

3. **Find the sensor and note its address.** Out of the box it takes DHCP or link-local:

   ```bash
   avahi-browse -rt _roger._tcp          # or check the DHCP lease
   ping os-<serial>.local
   ```

   Either give it the static address `192.168.1.126` through its web UI, or keep whatever address
   it has and pass it at launch.

4. **Point the launch at it.** Nothing needs editing if the address matches; otherwise:

   ```bash
   ros2 launch autoware_launch autoware.launch.xml \
       vehicle_model:=pixkit sensor_model:=pixkit_sensor_kit \
       map_path:=$PWD/autoware_map
   # or override for a one-off:
   #   lidar_profile:=os1_128 os1_128_ip:=192.168.1.130 host_ip:=192.168.1.100
   ```

   To change it permanently, edit the `os1_128_ip` and `host_ip` defaults in `lidar.launch.xml`.
   `host_ip` becomes the driver's `udp_dest`: the sensor sends its packets there, so it has to be
   the host's address **on the sensor LAN**, not its wifi address.

5. **Measure the mounting.** `base_link2os_lidar_top` in `sensors_calibration.yaml` is currently
   `z: 1.4`, `yaw: 3.1075` — the sensor faces backwards relative to `base_link`. This is specific
   to how the lidar sits on this vehicle; a new mount needs its own numbers, and localization will
   not converge if they are wrong.

6. **Verify**, in this order, before blaming Autoware:

   ```bash
   ping 192.168.1.126                                    # network
   ros2 topic hz /sensing/lidar/top/ouster/points        # ~10 Hz
   ros2 topic echo --field fields /sensing/lidar/top/ouster/points --once
   ros2 run tf2_ros tf2_echo base_link os_lidar_top      # extrinsics
   ```

   The `fields` output must list exactly ten entries: `x, y, z, intensity, return_type, channel,
   azimuth, elevation, distance, time_stamp`. Anything else means the driver is publishing a layout
   Autoware will silently reduce to x/y/z.

## Time synchronization

`timestamp_mode` is `TIME_FROM_ROS_TIME`, which stamps each cloud with the arrival time of its
first packet. That works, but distortion correction and the concatenate node's time matching both
assume the cloud stamp shares a clock with the rest of the system. `TIME_FROM_PTP_1588` is the
right setting once a PTP master is running on the vehicle; the per point `time_stamp` field is
already relative to the message stamp, so nothing else has to change.

## Known issues and gotchas

- **The driver is a lifecycle node.** It comes up unconfigured and does nothing until it is
  configured and activated. [`activate_lifecycle_node.sh`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_launch/launch/activate_lifecycle_node.sh)
  waits for the node to register and then drives the transitions. The upstream approach used two
  fixed `sleep` calls and loses that race on a busy machine, leaving the driver silent with no
  publishers and no error.
- **`os_top_config.yaml`, `os_rl_config.yaml` and `os_rr_config.yaml` are dead.** No launch file
  references them, and `os_top_config.yaml` still names `192.168.1.125`. Ignore them; the live
  configuration is in `os_sensor_top.launch.xml`.
- **Two more Ouster launch files exist** (`os_sensor_rl.launch.xml`, `os_sensor_rr.launch.xml`) for
  rear-left and rear-right units that this vehicle does not have. `lidar.launch.xml` does not
  include them.
- **Reserved addresses.** See the address map in [`SENSORS.md`](../SENSORS.md) before assigning anything on the sensor LAN.

## Driver documentation

The fork documents its own parameters, the field mapping and an Autoware preset parameter file in
[`src/sensor_component/external/autoware_ouster_ros/README.md`](../../src/sensor_component/external/autoware_ouster_ros/README.md).
