# USB camera — traffic light recognition

A single USB camera, driven by `usb_cam`, published into the namespace Autoware's traffic light
pipeline expects.

## At a glance

| | |
| --- | --- |
| Device | `/dev/video2` |
| Resolution | 1920 × 1080 at 30 fps, `yuyv` |
| Frame | `camera` |
| Namespace | `/sensing/camera/traffic_light/` |
| Driver | `usb_cam_node_exe` |

## Where it is configured

| What | File |
| ---- | ---- |
| Node | [`camera_launch.py`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_launch/launch/camera_launch.py) |
| Parameters | [`params.yaml`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_launch/config/params.yaml) |
| Namespace | [`sensing.launch.xml`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_launch/launch/sensing.launch.xml) |
| Mounting position | `os_lidar_top2camera` in [`sensors_calibration.yaml`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_description/config/sensors_calibration.yaml) |

The camera is calibrated **relative to the lidar**, not to `base_link`, which is what
projection-based traffic light recognition needs.

## Changing the device

`video_device` in `params.yaml`. Note that `/dev/videoN` numbering is not stable across reboots or
across machines — a second UVC device, or an internal webcam, shifts it. For anything permanent,
use a by-id path:

```bash
ls -l /dev/v4l/by-id/
# then set video_device: "/dev/v4l/by-id/usb-...-video-index0"
```

## Verifying

```bash
v4l2-ctl --list-devices
ros2 topic hz /sensing/camera/traffic_light/image_raw
```

`usb_cam_node_exe` failing to start is a known open item in
check the device path first.

## Intrinsics

No camera info calibration file is committed. Traffic light recognition needs one to project map
positions into the image, so this has to be produced (`camera_calibration`) and wired in before
that part of the perception stack is meaningful.
