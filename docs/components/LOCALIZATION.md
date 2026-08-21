# Localization

How this vehicle knows where it is. Answers accumulate here as they come up.

## What estimates the pose

Two different jobs, often confused:

| | used for | source |
| --- | -------- | ------ |
| **GNSS** | the **initial** pose, once | CHC CGI-410 → `gnss_poser` |
| **NDT** | the **continuous** pose, forever after | Ouster point cloud matched against `pointcloud_map.pcd` |
| **gyro odometry** | the twist the pose is propagated with | IMU angular rate + vehicle velocity from CAN |

Configured in
[`tier4_localization_component.launch.xml`](../../src/launcher/autoware_launch/autoware_launch/launch/components/tier4_localization_component.launch.xml):

```
pose_source:  ndt
twist_source: gyro_odom
```

### Initialization

```
/sensing/gnss/fix → gnss_poser → /sensing/gnss/pose_with_covariance
   → automatic_pose_initializer → /api/localization/initialize
   → pose_initializer: takes the GNSS pose as a first guess, runs an NDT alignment
     around it, publishes the aligned result
   → ekf_localizer activates → map → base_link exists
```

GNSS answers *roughly where are we*, to about a metre. NDT refines it against the map. Without a
guess NDT would have to search the entire map, which is why nothing at all happens until an initial
pose exists — and why an empty RViz usually means uninitialized localization rather than a dead
sensor.

Since GNSS only has to be good enough to seed the search, RTK float versus fixed barely matters
here. What matters is being inside the mapped area.

### Steady state

```
lidar ─▶ ndt_scan_matcher ─▶ pose_with_covariance ─┐
                                                    ├─▶ ekf_localizer ─▶ map → base_link
IMU + vehicle velocity ─▶ gyro_odometer ─▶ twist ──┘
```

NDT against a prior map beats GNSS in the environments Autoware targets: it is centimetre level and
consistent *with the map*, since the vehicle is localized against the same cloud the lanelets were
drawn on. Raw GNSS drifts relative to a map, loses fix beside buildings, and jumps when fix quality
changes — discontinuities the planner would be steering through.

## Fusing GNSS into the running estimate

**Enabled on this vehicle.** By default Autoware drops GNSS entirely once initialized; the switch
that changes this is `use_autoware_pose_covariance_modifier`, declared at the top of
[`pose_twist_estimator.launch.xml`](../../src/launcher/autoware_launch/tier4_universe_launch/tier4_localization_launch/launch/pose_twist_estimator/pose_twist_estimator.launch.xml).
It is not exposed as a top level launch argument, so the default in that file is the control.

With it on, the topic wiring changes:

```
off:  ndt_scan_matcher ──────────────────────────▶ /localization/pose_estimator/pose_with_covariance
on:   ndt_scan_matcher ─▶ .../ndt_scan_matcher/pose_with_covariance ─┐
      gnss_poser ──────▶ /sensing/gnss/pose_with_covariance ─────────┼▶ pose_covariance_modifier
                                                                     └▶ /localization/pose_estimator/pose_with_covariance
```

The modifier compares the two covariances and decides which to trust, rather than blindly
averaging. Thresholds live in
`autoware_pose_covariance_modifier/config/pose_covariance_modifier.param.yaml`:

| parameter | default | effect |
| --------- | ------- | ------ |
| `threshold_gnss_stddev_yaw_deg_max` | 0.3° | above this, trust NDT only |
| `threshold_gnss_stddev_z_max` | 0.1 m | above this, trust NDT only |
| `threshold_gnss_stddev_xy_bound_lower` | 0.1 m | below this, trust GNSS only |
| `threshold_gnss_stddev_xy_bound_upper` | 0.25 m | above this, trust NDT only |

Those are tight. A GNSS solution has to be RTK **fixed** with good heading to be trusted at all; at
float it will mostly fall back to NDT, which is the intended behaviour rather than a failure.

It earns its place in open areas where NDT is weak — feature poor roads, wide car parks — and costs
a second pose source to reason about when localization misbehaves. If diagnosing something strange,
setting it back to `false` is the first thing to try.

## When it does not initialize

The error text names the cause precisely; they are unrelated to each other.

| message | cause |
| ------- | ----- |
| `status code 1 'The vehicle is not stopped.'` | the stop check reads `/localization/kinematic_state`, fed from vehicle velocity over CAN. With CAN down there is no velocity, so it cannot confirm the vehicle is stationary. Bring CAN up, or run with `system_run_mode:=logging_simulation`, which disables the check |
| `status code 3 'The GNSS pose has not arrived.'` | no GNSS pose. Walk the chain in [`sensors/CHC_CGI410.md`](../sensors/CHC_CGI410.md); the driver dying on a missing dependency looks identical to an unreachable receiver |
| `The node is not activated. Provide initial pose to pose_initializer` | the EKF saying it is waiting. A consequence, not a cause |

No initial pose means no `map` frame, and the RViz config uses `map` as its fixed frame, so
**nothing renders at all**. Set the fixed frame to `base_link` to see sensor data before
localization works.

## Checking it is running

```bash
ros2 run tf2_ros tf2_echo map base_link                        # exists only after initialization
ros2 topic hz /localization/pose_estimator/pose_with_covariance
ros2 topic hz /localization/kinematic_state                    # the fused output
ros2 topic echo /localization/pose_estimator/exe_time_ms       # NDT cost per scan
```
