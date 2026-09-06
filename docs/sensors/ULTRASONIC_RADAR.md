# Ultrasonic radar and ARS408 — shipped, not enabled

Two sensing paths ship with the Pixkit extensions and are built, but neither is launched.

## Ultrasonic radar

The Pixkit's ultrasonic ring, read over CAN rather than over ethernet.

| | |
| --- | --- |
| Packages | `ultra_sonic_radar_driver`, `ultra_sonic_radar_detector` |
| Input | `/from_can_bus` |
| Output | `ultra_sonic_radar`, then detected objects from the detector node |
| Launch | [`ultrasonic_radar.launch.xml`](../../src/launcher/autoware_launch/sensor_kit/segway_sensor_kit_launch/segway_sensor_kit_launch/launch/ultrasonic_radar.launch.xml), [`ultra_sonic_radar_detector.launch.py`](../../src/launcher/autoware_launch/sensor_kit/segway_sensor_kit_launch/segway_sensor_kit_launch/launch/ultra_sonic_radar_detector.launch.py) |
| Status | Both includes are **commented out** in [`sensing.launch.xml`](../../src/launcher/autoware_launch/sensor_kit/segway_sensor_kit_launch/segway_sensor_kit_launch/launch/sensing.launch.xml) |

Twelve `ultrasonic_*` frames are declared in the sensor kit xacro, so the geometry is described
even though nothing publishes on those frames today. Re-enabling means uncommenting the two
includes and having the CAN bridge running, since the driver reads chassis CAN frames rather than
talking to the sensors directly.

## Continental ARS408 radar

| | |
| --- | --- |
| Packages | `pe_ars408_ros`, `ars408_driver` |
| Status | Built, never launched; no ARS408 is fitted |

## Other declared but unused frames

`sensors_calibration.yaml` also carries `base_link2rs16` and `base_link2rsbp` for RoboSense units
(`rslidar_sdk` is built), and `base_link2zed` for a ZED camera. None of these are launched either.
They are part of the stock Pixkit description rather than of this vehicle.
