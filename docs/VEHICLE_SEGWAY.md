# Segway RMP Plus 401 — vehicle model

Dimensions, frames, and where each sensor sits. The interface that drives the chassis is
documented separately in [SEGWAY_VEHICLE_INTERFACE.md](SEGWAY_VEHICLE_INTERFACE.md).

## Dimensions

From Table 1, "System parameters", of the RMP Plus 401 user manual (2023-03-01), committed
at [`user-manual-for-rmp-plus-401-20230301.pdf`](user-manual-for-rmp-plus-401-20230301.pdf).

| | Manual | In `vehicle_info.param.yaml` |
|---|---|---|
| Length × width × height | 672 × 617 × 274 mm | `vehicle_height: 0.274` |
| Wheelbase | 456 mm | `wheel_base: 0.456` |
| Track ("wheel base" in the manual) | 545 mm | `wheel_tread: 0.545` |
| Ground clearance | 58 mm | — |
| Tyre | 8.5 inch | `wheel_radius: 0.108` |
| Weight / nominal load | 28 kg / 28 kg | — |
| Max speed | 3.56 m/s | limited to 1.0 by the interface |
| Max steering speed | 2 rad/s | limited to 1.5 by the interface |
| Min turning radius | 1.36 m | — |

Two values are **derived rather than measured**:

- **Overhangs**, 108 mm front and rear, as `(672 − 456) / 2`. That assumes the axles sit
  symmetrically in the body. Same for the 36 mm lateral overhangs.
- **`wheel_width` 0.06 m** is a guess; the manual gives no tyre width. It affects only the
  drawn footprint.

## Frames

`base_link` is at the **centre of the rear axle, on the ground** — the Autoware
convention. `sensor_kit_base_link` is directly above it at the top of the chassis,
z = 0.274.

| Frame | x | y | z | Source |
|---|---|---|---|---|
| `sensor_kit_base_link` | 0 | 0 | 0.274 | chassis height, manual |
| `livox_frame` | 0.564 | 0 | 0 | front of chassis, laterally centred |
| `gnss_link` | 0 | 0 | 0 | over the rear axle centre |

`livox_frame`'s x is `wheelbase 0.456 + front overhang 0.108`. Offsets in
`sensor_kit_calibration.yaml` are relative to `sensor_kit_base_link`, so z = 0 means
chassis top, 274 mm above the ground.

> [!IMPORTANT]
> These positions come from the manual's geometry plus a description of where each sensor
> was fitted. They are **not** the output of a calibration. If a sensor sits on a riser, or
> its optical centre is above its mounting face, that height is missing.
>
> The one that bites hardest is `livox_frame`'s z. Ground segmentation reads z as height
> above `base_link`; get it wrong and the ground plane moves, so the floor is classified as
> obstacle or obstacles as floor. Everything downstream of that looks broken in confusing
> ways.

### What the Pixkit values would have done

`sensor_kit_base_link` was at **z = 1.4** — correct for the Pixkit, absurd on a robot
274 mm tall. Every sensor would have been placed more than a metre above where it is, which
does not merely offset the cloud: the ground plane lands above the sensor and every real
return is classified as below ground.

`wheel_base` was 1.9 m against an actual 0.456, and `wheel_tread` 1.465 against 0.545. A
controller planning for a 1.9 m wheelbase turns a 0.456 m robot far more sharply than it
intends.

## Steering, on a robot that cannot steer

The RMP is differential-drive: no steered axle, no steering angle to report. Autoware
nonetheless speaks a bicycle model, so `max_steer_angle` is a **virtual** limit on what the
controller may command, and the interface converts it to a yaw rate:

```
yaw_rate = v * tan(steer) / wheel_base
```

`max_steer_angle: 0.70` rad is chosen so that at the interface's 1.0 m/s cap the result
stays inside the chassis limit:

```
1.0 * tan(0.70) / 0.456 = 1.85 rad/s     chassis limit 2.0 rad/s
```

Raising `max_linear_mps` without revisiting this will command yaw rates the chassis cannot
deliver, and it will simply saturate — the robot under-turns, and the controller integrates
an error it cannot fix.

> [!WARNING]
> `wheel_base` appears in **two** files and they must agree:
> `segway_description/config/vehicle_info.param.yaml` and
> `segway_vehicle_interface/config/segway.param.yaml`. If they diverge, Autoware and the
> chassis mean different things by the same steering command, and the symptom is a steady
> tracking offset that reads as a controller tuning problem. The interface logs its value
> at startup so the mismatch is findable:
>
> ```
> wheel_base 0.456 m (must equal vehicle_info.param.yaml), limits 1.0 m/s and 1.5 rad/s
> ```

## No mesh

There is no CAD model for this chassis, so the URDF draws a 672 × 617 × 274 mm box. It is
right for footprint and collision checking, and merely plain in RViz and Foxglove.

`mirror.param.yaml` is a zero-sized crop box: the RMP has no mirrors, but the pointcloud
preprocessor loads the file unconditionally, so it must exist and remove nothing.
