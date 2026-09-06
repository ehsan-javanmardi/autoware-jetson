# gnss_pose_source

Makes RTK GNSS the vehicle's pose estimator, in place of NDT map matching. Selected with
`pose_source:=gnss`; it is an addition to the existing modes, not a replacement.

```text
/sensing/gnss/pose_with_covariance ─┐
/sensing/gnss/fix                  ─┼─► gnss_pose_source ─► /localization/pose_estimator/pose_with_covariance
/autoware_orientation              ─┘      (quality gate)              │
                                                                    ekf_localizer
```

That output topic is the one NDT writes in the other modes, so nothing downstream of the
EKF changes.

## The modes

| `pose_source` | What runs | Position from |
| --- | --- | --- |
| `ndt` (default) | NDT, plus the covariance modifier if enabled | Lidar against the point cloud map, optionally blended with GNSS |
| `ndt_gnss` | NDT + covariance modifier, forced on | An explicit name for the blend that `use_autoware_pose_covariance_modifier` already provided |
| **`gnss`** | **this node only** | **RTK GNSS. No map matching at all** |
| `yabloc`, `eagleye`, `artag`, `lidar-marker` | unchanged | unchanged |

`gnss` is deliberately **not** in the launch's `available_args` list. That list feeds
`pose_estimator_arbiter`, which has no plugin for a GNSS source, so listing it there would
make `ndt_gnss` spawn an arbiter that cannot manage one of its own sources. It is parsed
separately, which leaves every pre-existing mode untouched.

Twist still comes from `gyro_odometer` (IMU + wheel speed) in every mode, including this
one. `twist_source` is independent of `pose_source`.

## The gate

With no map matcher there is no second opinion, so a bad GNSS solution goes straight into
the vehicle's idea of where it is. Poses are only passed on while all of these hold:

| Check | Default | Why |
| --- | --- | --- |
| `min_navsat_status` | `2` (GBAS/RTK) | `0` is single-point positioning, metres out |
| `max_position_stddev` | `1.0` m | The receiver's own accuracy claim |
| `max_fix_age_sec` | `0.5` s | Catches the pose still arriving after the fix stopped |
| `require_ins_orientation` | `true` | Without a dual-antenna heading, `gnss_poser` derives yaw from the direction of travel — meaningless at a standstill |

**When a check fails the pose is dropped, not degraded.** The EKF then coasts on gyro and
wheel odometry, its covariance grows, and `localization_error_monitor` takes autonomous
mode away on its own. Publishing an inflated-covariance pose instead would keep the system
confident while being wrong.

`1.0 m` is a bring-up value. Tighten `max_position_stddev` to around `0.1` m before relying
on this for lane keeping.

## Covariance is passed through untouched

Whether a GNSS pose deserves trust is a question about the receiver's accuracy estimate.
Substituting a prettier number here would make the EKF confident for no reason, so this
node never rewrites the covariance — it only decides whether to pass the pose at all.

If the estimate itself is wrong, the place to fix it is the driver that produces it. That
was the case here: `nmea_navsat_driver` turns the GGA quality indicator into a covariance
of `(HDOP × epe)²`, and its default `epe_quality5 = 4.0 m` for an RTK **float** solution is
about ten times too pessimistic. A live float fix on this vehicle was reporting **2.24–3.16
m** across 264 samples. The table is corrected in
`segway_sensor_kit_launch/launch/nmea_tcpclient_driver.launch.py`:

| GGA quality | Meaning | epe |
| --- | --- | --- |
| 1 | single point | 4.0 m |
| 2 | DGPS | 1.0 m |
| 4 | RTK fixed | 0.02 m |
| 5 | RTK float | 0.4 m |
| 9 | WAAS | 3.0 m |

The same fix improves the `ndt_gnss` blend, since the covariance modifier weighs NDT
against GNSS by exactly this number.

Note that GGA quality 4, 5 and 9 all map to `NavSatStatus` 2, so `min_navsat_status` alone
cannot tell RTK fixed from float. `max_position_stddev` is what actually distinguishes
them.

## Running

```bash
./autoware_kashiwa.sh pose_source:=gnss
```

Confirm it took:

```bash
ros2 node list | grep pose_estimator
#   /localization/pose_estimator/gnss_pose_source     <- present
#   no ndt_scan_matcher

ros2 topic hz /localization/pose_estimator/pose_with_covariance   # ~10 Hz
ros2 topic echo /localization/initialization_state --once         # state: 3
ros2 run tf2_ros tf2_echo map base_link
```

The node logs each transition once rather than per message:

```
GNSS pose source accepted (status 2, 0.288 m std dev)
GNSS pose source stopped: the reported position uncertainty is too large
```

## What this does not give you

- **No map correction.** Position is only as good as the RTK solution. Under a bridge, in
  an underground car park, or beside a tall building the solution degrades and the gate
  stops publishing — by design, but it means the vehicle has no fallback.
- **Vertical accuracy is the weak axis.** GNSS height is worse than horizontal, and
  `map_projector_info.yaml` here uses EGM2008; a height error shows up as the vehicle
  floating above or sinking into the map.
- **It does not fix the CPU problem on its own.** Removing NDT frees real capacity, but the
  Ouster and the perception stack are the larger consumers.

## Tests

The gate is free of ROS types and unit tested, including the boundary behaviour and the
real float-grade numbers this vehicle produced:

```bash
colcon test --packages-select gnss_pose_source
```
