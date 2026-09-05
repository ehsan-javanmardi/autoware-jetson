# Planning and control

How a route becomes wheel commands, and what has to be true before anything moves. This page fills
in as questions come up.

## The chain

```
route (from RViz or the API)
  └─▶ mission_planner ──▶ behavior_path_planner ──▶ behavior_velocity_planner
        └─▶ motion_velocity_planner ──▶ trajectory
              └─▶ trajectory_follower  ──▶ control command
                    └─▶ raw_vehicle_cmd_converter ──▶ pix_hooke_driver ──▶ CAN
```

Planning refuses to start until it has, at minimum, **a route, an initial pose and odometry**. The
`waiting for route` / `waiting for odometry` lines from `behavior_path_planner` are it saying so,
and they resolve on their own once localization initializes.

## What reaches the vehicle

The last two stages are Pixkit specific:

| | |
| --- | --- |
| `autoware_raw_vehicle_cmd_converter` | Autoware control command → actuation (throttle, brake, steer) |
| `pix_hooke_driver` | actuation → CAN frames on `can0` / `can1`, 500 kbit/s |
| Vehicle dimensions used by planning | `vehicle_info.param.yaml` in the vehicle description package |

> [!WARNING]
> With `can0` and `can1` up and Autoware running, control frames reach the chassis controller.
> There is no software interlock between "the stack is running" and "the vehicle can move". Bring
> CAN up only with the wheels clear or the vehicle on blocks, and the e-stop in reach. See
> the vehicle interface package in `src/vehicle/`.

To run the stack with no possibility of movement, either leave CAN down or pass
`launch_vehicle_interface:=false`.

## Vehicle dimensions are not cosmetic

`vehicle_info.param.yaml` is read by the planners, the controllers and the crop box filters alike.
A wrong `wheel_base` produces a vehicle that consistently cuts corners or swings wide, and nothing
reports an error; the trajectory simply does not match what the vehicle does.

## Open items on this vehicle

- **Nothing has been driven under autonomy yet.** Everything recorded here so far is bring-up.
- **`pix_hooke_driver` reports partial CAN timeouts** even with the chassis talking: the three main
  status topics publish while some expected reports never arrive. Observed 2026-08-20; not yet
  traced to which report IDs are missing.

## Checking it is running

```bash
ros2 topic hz /vehicle/status/velocity_status          # the vehicle is talking
ros2 topic echo /planning/scenario_planning/trajectory --once --no-arr
ros2 topic echo /control/command/control_cmd --once    # what would reach the chassis
```
