# CHC CGI-410 — GNSS / INS

Supplies both the GNSS fix Autoware initializes localization from and the IMU that
`autoware_imu_corrector` consumes. It is the `chc` option of the sensor kit's GNSS launch, which is
the default.

## At a glance

| | |
| --- | --- |
| Address | `192.168.1.110`, web UI `:80` (`admin` / `password`) |
| NMEA | TCP `192.168.1.110:9904` |
| Driver | `nmea_navsat_driver` (TCP client variant) |
| Fix topic | `fix` → `/sensing/gnss/...` |
| IMU topic | `/sensing/gnss/chc/imu` → corrected to `imu_data` |
| Frame | `gnss_link` |
| Coordinates | MGRS (`coordinate_system: 1`) |

## Where it is configured

| What | File |
| ---- | ---- |
| Receiver selection | [`gnss.launch.xml`](../../src/launcher/autoware_launch/sensor_kit/velodyne_pixkit_sensor_kit_launch/velodyne_pixkit_sensor_kit_launch/launch/gnss.launch.xml) — `gnss_receiver` is `ublox`, `septentrio`, `chc` or `fixposition` |
| TCP endpoint | [`nmea_tcpclient_driver.yaml`](../../src/launcher/autoware_launch/sensor_kit/velodyne_pixkit_sensor_kit_launch/velodyne_pixkit_sensor_kit_launch/config/nmea_tcpclient_driver.yaml) |
| IMU source | [`imu.launch.xml`](../../src/launcher/autoware_launch/sensor_kit/velodyne_pixkit_sensor_kit_launch/velodyne_pixkit_sensor_kit_launch/launch/imu.launch.xml) |
| Mounting position | `base_link2gnss` in [`sensors_calibration.yaml`](../../src/launcher/autoware_launch/sensor_kit/velodyne_pixkit_sensor_kit_launch/velodyne_pixkit_sensor_kit_description/config/sensors_calibration.yaml) — `x: -0.9, z: 0.3` |

`imu.launch.xml` selects `/sensing/gnss/chc/imu`; two alternatives are commented out in that file,
the Ouster's built-in IMU (`/sensing/lidar/top/ouster/imu`) and the Fixposition
(`/fixposition/corrimu`). Switching IMU source is a one-line change there.

## Changing the address

Edit `nmea_tcpclient_driver.yaml`. That file is the only place the receiver's address appears, and
it is a plain node parameter file, so the change takes effect on the next launch.

## RTK

Corrections come from SoftBank ichimill over NTRIP. The receiver runs the NTRIP client itself
rather than the host relaying with `str2str`. Full setup, including the caster address, the mount
point and the routing that lets a receiver on a gateway-less LAN reach the internet, is in
[`RTK_ICHIMILL_SETUP.md`](../RTK_ICHIMILL_SETUP.md).

The routing part is easy to miss: the sensor LAN has no gateway, so `pixkit-sensor-nat.service`
masquerades `192.168.1.0/24` out of whichever interface holds the default route. Without it the
receiver cannot reach the caster and silently stays in single-point fix.

## Verifying

```bash
ping 192.168.1.110
nc -vz 192.168.1.110 9904          # NMEA stream is reachable
ros2 topic echo /sensing/gnss/fix --once
ros2 topic hz /sensing/gnss/chc/imu
```

A fix with `status: 0` is a standalone solution; RTK fixed is `status: 2`. Autoware's GNSS pose
initialization is only as good as the fix quality, so a vehicle that will not initialize is worth
checking here first.
