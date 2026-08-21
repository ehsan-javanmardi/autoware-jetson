# The vehicle

Pixkit 3.0. This page collects what the rest of the workspace assumes about the vehicle itself:
where its origin is, its dimensions, and where the sensors sit relative to it.

## `base_link`

Autoware's convention, which this vehicle follows: **the centre of the rear axle, projected onto
the ground**. Not the vehicle centre, not the front bumper, not the sensor mast. Every extrinsic in
[`sensors_calibration.yaml`](../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_description/config/sensors_calibration.yaml)
is measured from that point, and so is the lever arm the GNSS receiver wants.

```
            front                                   rear
              │                                       │
    ┌─────────┴───────────────────────────────────────┴──┐
    │   ●  front axle                    ●  rear axle    │
    └──────────────────────┬─────────────┬───────────────┘
                           │             │
              wheel_base 1.9 m      base_link  ── 0.32 m ──▶ rear bumper
                                    (on the ground)
```

## Dimensions

From [`vehicle_info.param.yaml`](../src/launcher/autoware_launch/vehicle/pixkit_launch/pixkit_description/config/vehicle_info.param.yaml),
which planning, control and the crop box filters all read:

| parameter | value | meaning |
| --------- | ----- | ------- |
| `wheel_base` | 1.9 m | front axle to rear axle |
| `wheel_tread` | 1.465 m | left wheel centre to right wheel centre |
| `wheel_radius` | 0.13 m | 26 cm diameter |
| `wheel_width` | 0.1 m | |
| `front_overhang` | 0.32 m | front axle to the front of the vehicle |
| `rear_overhang` | 0.32 m | rear axle to the back of the vehicle, so `base_link` sits 0.32 m ahead of the rear bumper |
| `left_overhang` / `right_overhang` | 0.0 m | the body does not extend past the wheels |
| `vehicle_height` | 1.4 m | |
| `max_steer_angle` | 0.4125 rad | 23.6° |

Overall footprint: **2.54 m long** (`0.32 + 1.9 + 0.32`), **1.465 m wide**.

## Where the sensors are

Measured from `base_link`, positive x forward, y left, z up:

| sensor | offset | note |
| ------ | ------ | ---- |
| Ouster lidar (`os_lidar_top`) | `x 0.0, y 0.0, z 1.4`, yaw 3.1075 rad | 178°, so it faces **backwards** relative to `base_link` |
| GNSS antenna (`gnss_link`) | `x -0.9, y 0.0, z 0.3` | 90 cm behind the rear axle, the **rear** antenna |
| Camera | relative to the lidar, not to `base_link` | projection needs the camera-to-lidar transform |

The yaw on the lidar is not a mistake: the sensor is physically mounted facing the rear of the
vehicle, and the extrinsic is what makes its point cloud come out the right way round.

> [!IMPORTANT]
> These numbers describe one physical build. Swapping a sensor for a different model, or
> re-mounting one, invalidates the entry until it is re-measured, and nothing at runtime detects
> the mismatch: localization simply fails to converge. The Ouster entry currently describes the
> OS-1-128 mount.

## The two GNSS antennas

Pixkit 3.0 carries **two** antennas, and they are not interchangeable
([vendor documentation](https://pixmoving-moveit.github.io/pixkit-documentation-en/install-sensors/GNSS-installation/)):

| antenna | receiver port | role |
| ------- | ------------- | ---- |
| **Rear** | GNSS1 | **primary — position** |
| **Front** | GNSS2 | secondary — **heading** |

The baseline between them gives true heading, which is why the vehicle knows its orientation while
stationary, with no motion to infer it from. Only the rear antenna is a position reference, and
only it has a frame in this workspace (`gnss_link`). The front antenna needs none: heading arrives
as a computed field inside the GPCHC sentence rather than as a separate measurement.

### Lever arms, and not counting them twice

The receiver has its own offset settings, configured in its console, separate from anything here:

- **IMU → positioning antenna**, so it can project its INS solution to the antenna.
- **Positioning antenna → rear wheel centre**, so it can output the solution at the rear axle.

If that second one is configured in the receiver, its output is already referenced to
`base_link`, and Autoware's `base_link2gnss` offset would apply the same 0.9 m a second time. At
RTK accuracy that error dominates everything else, so establish which convention the receiver is
set for before trusting GNSS pose. See [`sensors/CHC_CGI410.md`](sensors/CHC_CGI410.md).

## Vehicle interface

Two USB CAN adapters, `can0` and `can1`, both at 500 kbit/s, driven by `pix_hooke_driver`. Bring-up
and the safety implications are in [`VEHICLE_CAN_AND_RUNTIME.md`](VEHICLE_CAN_AND_RUNTIME.md).
