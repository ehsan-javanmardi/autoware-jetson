# Segway vehicle interface

Autoware's vehicle interface for the Segway RMP Plus 401, in
[`src/vehicle/external/segway_vehicle_interface`](../src/vehicle/external/segway_vehicle_interface).
It replaces `pix_hooke_driver`, which drives the Pixkit chassis this tree was forked from.

```bash
# status only; cannot move the base
ros2 launch segway_vehicle_interface segway_vehicle_interface.launch.xml

# motion enabled
ros2 launch segway_vehicle_interface segway_vehicle_interface.launch.xml allow_control:=true
```

### Two defaults, deliberately different

| Launched via | `allow_control` | Because |
|---|---|---|
| `segway_vehicle_interface.launch.xml` directly | **false** | Launching the interface on its own is for looking at the chassis. Nothing should move. |
| `./autoware_kashiwa.sh` (`vehicle_model:=segway`) | **true** | Launching the full stack means intending to drive. |

The second default was chosen deliberately after the first caused a real trap: Autoware
plans a route, engages, and commands control, every layer reports healthy — and the robot
does not move, because the SDK's write functions were never bound. A stack that silently
cannot move is worse than one that obviously cannot.

The safeguards that matter are the chassis E-stop, the RC's enable switch, and the
watchdog below. Not a launch argument.

## What it publishes

| Topic | Type | Rate |
|---|---|---|
| `/vehicle/status/velocity_status` | `VelocityReport` | 50 Hz |
| `/vehicle/status/steering_status` | `SteeringReport` | 50 Hz |
| `/vehicle/status/control_mode` | `ControlModeReport` | 50 Hz |
| `/vehicle/status/gear_status` | `GearReport` | 50 Hz |

It subscribes to `/control/command/control_cmd` and `/control/command/gear_cmd`, and
serves `/control/control_mode_request`.

## Bicycle in, differential out

Autoware speaks a bicycle model: a steering tire angle and a longitudinal velocity. The
RMP is a differential-drive base whose SDK takes linear and angular velocity. The
conversion is the bicycle model solved for yaw rate:

```
angular_z = linear_x * tan(steering_tire_angle) / wheel_base
```

`wheel_base` is **virtual** — the RMP has no steered axle. It sets how sharply a given
steering command turns the base, and it **must match `wheel_base` in the vehicle
description**. If the two disagree, Autoware's controller and the chassis mean different
things by the same command, and the error shows up as persistent tracking offset that
looks like a tuning problem rather than a units problem.

`tan()` rather than the small-angle approximation, because Autoware commands large
steering angles at low speed, where the two diverge.

Two things the chassis cannot tell us:

- **Steering angle.** There is no steered axle to report one. The interface echoes the
  last commanded angle, so the controller does not integrate error against a constant zero.
- **Yaw rate.** Derived from the left/right wheel-speed difference, with the track width
  folded into `wheel_base` as an approximation. Once the EKF is running, the IMU is the
  better source.

## Safety

Three properties, in the order they matter.

**Motion is opt-in at the binding level.** With `allow_control: false` the SDK's
`set_cmd_vel` and `set_enable_ctrl` are *never bound* — not merely unused. The object has
no callable route to motion, so a logic error cannot reach one. This is the same
structural approach the health dashboard takes.

**Motors are enabled only on an explicit AUTONOMOUS request**, never at startup. A
control mode request arriving while the node is read-only is refused and logged.

**A watchdog zeroes the command after `command_timeout_s` (0.5 s).** This matters more on
a differential base than on a car: the chassis holds its last commanded velocity
indefinitely, so a planner that crashes or pauses leaves the robot driving. Leaving
AUTONOMOUS and shutting the node down both zero the command and disable the motors.

## The vendor library

`libctrl_arm64-v8a.so`, from the `segway_rmp` branch of
[`adeeb10abbas/segway_ros2`](https://github.com/adeeb10abbas/segway_ros2). It is not
vendored into this repository. Point at it with `library_path`, or `SEGWAY_SDK_LIB`; the
default is `/home/tlab/workspace/segway_ros2/segwayrmp/lib/`.

> [!WARNING]
> **The vendor headers declare functions the library does not export.**
> `comm_ctrl_navigation.h` declares `get_encode_speed_L` and `get_encode_speed_R`; the
> library exports `get_encode_speed_FL/FR/RL/RR` — four wheels, not two. Binding the
> header's names fails at load with a bare `AttributeError`. Treat the headers as
> documentation of intent, not of the ABI, and check before binding anything new:
>
> ```bash
> nm -D --defined-only libctrl_arm64-v8a.so | grep <name>
> ```
>
> `sdk.py` now raises a message naming the missing symbol instead.

Scaling constants come from the vendor header and are not guessable: **3600 raw = 1 m/s**,
**1000 raw = 1 rad/s**.

## Verified

Against the powered chassis, 2026-09-06:

| | |
|---|---|
| Link | `central 0x2028`, `motor 0x2028`, `host 0x2027` (the SDK's own) |
| Battery | 45 %, 36.4 V |
| Status topics | all four at ~50 Hz |
| Velocity while stationary | `0.0` |
| Control mode at startup | `4` (MANUAL) |
| Health dashboard | sees the vehicle group |

**Motion has not been tested.** Everything above ran with `allow_control: false`. Before
the first `allow_control:=true` run, put the wheels off the ground or keep the E-stop in
reach — `set_enable_ctrl` energises the motors and the base will move on the next command.

## Parameters

See [`config/segway.param.yaml`](../src/vehicle/external/segway_vehicle_interface/config/segway.param.yaml).
`wheel_base`, `max_linear_mps` and `max_angular_radps` are placeholders pending
measurement of the actual chassis.
