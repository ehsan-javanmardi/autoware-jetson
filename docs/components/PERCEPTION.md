# Perception

What the vehicle detects around it. This page fills in as questions come up; only what has been
established on this vehicle is written down here.

## Configured for this vehicle

| | |
| --- | --- |
| Detection model | `centerpoint` (`lidar_detection_model` in [`tier4_perception_component.launch.xml`](../../src/launcher/autoware_launch/autoware_launch/launch/components/tier4_perception_component.launch.xml)) |
| Perception mode | `lidar` (no camera or radar fusion) |
| Input | `/sensing/lidar/concatenated/pointcloud`, in `base_link` |
| Ground segmentation | `ScanGroundFilterComponent`, elevation grid mode |

## The input contract

Everything in perception starts from `/sensing/lidar/concatenated/pointcloud`. How that topic comes
to exist with one lidar, and why it is a passthrough rather than the concatenate node, is in
[`../LAUNCH_CHAIN.md`](../LAUNCH_CHAIN.md) and [`../SENSORS.md`](../SENSORS.md#sensor-combinations).

Two properties of that cloud matter to everything downstream:

- **It is in `base_link`.** Ground segmentation reads heights as though they are relative to the
  vehicle. A cloud left in the sensor frame would put the ground 1.4 m below where the filter
  expects it.
- **Its point type is `PointXYZIRC`.** Autoware validates field names, datatypes and byte offsets;
  a mismatch is not rejected but silently reduced to x/y/z. See
  [`../sensors/OUSTER_OS1_128.md`](../sensors/OUSTER_OS1_128.md).

## Open items on this vehicle

- **`/perception/obstacle_segmentation/pointcloud` has not been seen publishing.** Observed
  2026-08-21 with the lidar chain healthy and localization uninitialized. Most likely explanation
  is the lidar extrinsic not matching the current mount, since ground segmentation is sensitive to
  sensor height and orientation, but this has not been confirmed.
- **Ground segmentation is tuned for a 128 beam sensor.** `grid_size_m` and `gnd_grid_buffer_size`
  in
  [`ground_segmentation.param.yaml`](../../src/launcher/autoware_launch/autoware_launch/config/perception/obstacle_segmentation/ground_segmentation/ground_segmentation.param.yaml)
  would need revisiting for the 32 beam OS-2, whose cloud is four times sparser.
- **No camera intrinsics are committed**, so traffic light recognition cannot project map positions
  into the image. See [`../sensors/CAMERA.md`](../sensors/CAMERA.md).

## Checking it is running

```bash
ros2 topic hz /perception/obstacle_segmentation/pointcloud
ros2 topic hz /perception/object_recognition/detection/objects
ros2 topic hz /perception/object_recognition/objects        # after tracking and prediction
```
