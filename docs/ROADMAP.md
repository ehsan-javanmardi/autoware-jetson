# Roadmap — Jetson + Segway platform

The working checklist for moving this workspace off its Pixkit inheritance and onto the
Jetson AGX Orin / Segway RMP / Livox HAP platform, with a web operator interface.

Tracked here rather than in GitHub issues, by choice. Keep it current: tick items as they
land, and record decisions inline so the reasoning survives.

## Decisions taken

Settled 2026-09-06 before any code was written.

| Question | Decision | Why it matters |
|---|---|---|
| Monitoring vs control | **Separate processes.** The monitor keeps its no-publisher, no-service-client guarantee; a second process owns every write path. | The dashboard runs on a tablet next to a powered mobile base. "It cannot move the robot" should be a structural fact, not a command-line flag. |
| Ouster | **Keep, not default.** A `lidar_model` arg defaults to `livox`, mirroring the existing `gnss_receiver` pattern. | Swapping back needs a launch argument, not a revert. |
| Segway interface | **Purpose-built package** wrapping the vendor `.so`. | `segway_ros2` targets the RMP220, not the 401, and its protocol is closed source, so a mismatch could not be patched. The dashboard has already proven the SDK against this chassis. |
| IMU source | **Livox HAP's built-in IMU.** | `ublox_dgnss` implements neither `UBXEsfRaw` nor `CFG_MSGOUT_UBX_ESF_RAW_USB`, so the F9R's accel/gyro are unreachable without forking the driver. The HAP publishes `sensor_msgs/Imu` natively. |
| Foxglove | **`foxglove_bridge` + versioned layouts**, connect from the Foxglove app. | Full Foxglove feature set with nothing to maintain in 3D. `app.foxglove.dev` blocks iframing, so embedding was not viable. |
| Goal sequencing | **Both modes, selectable in the UI.** | Step-by-step is observable and fails at a known point; single-route drives through without stopping. Different jobs. |
| RViz | **Launch flag, default off.** | Saves the Orin's GPU. Spawning a GUI from a web server needs a working `DISPLAY` and breaks headless. |

## 1. Sensors

- [x] **Livox HAP driver.** `livox_ros_driver2` + Livox-SDK2 vendored into `src/sensor_component/external/`. See [LIVOX_HAP.md](LIVOX_HAP.md).
- [x] **Single-lidar pipeline.** `lidar_profile:=livox` is the default; `PointCloud2` at ~7.5 Hz, ~45 k points, through the crop-box passthrough into `base_link`.
- [x] **IMU from the HAP.** `/sensing/lidar/top/livox/imu`, `sensor_msgs/Imu` at ~200 Hz, into `imu_corrector`.
- [x] **GNSS/RTK.** u-blox ZED-F9R over `ublox_dgnss` with ichimill NTRIP — see [GNSS_IMU_UBLOX_F9R.md](GNSS_IMU_UBLOX_F9R.md). RTK fix still unproven pending sky view.

> [!IMPORTANT]
> **`livox_frame` extrinsics are a placeholder** (kit origin, zero rotation). Measure the
> HAP's mounting on the Segway before driving: ground segmentation reads `z` as height
> above `base_link`, so an unmeasured mount misplaces the ground plane.

## 2. Vehicle

- [ ] **Segway vehicle interface.** New package: Autoware `control_cmd` in, vehicle status and odometry out, wrapping `libctrl_arm64-v8a.so`.
- [ ] **Retire `pix_driver`** from the launch path once the Segway interface works.
- [ ] **Vehicle model.** Segway dimensions and `base_link` placement, replacing `pixkit_description`.

## 3. Observability

- [ ] **Health monitor.** Port `health_ui` from the `upstream` remote (`pix_autoware`), re-targeted at these sensors and this vehicle interface.
- [ ] **Foxglove bridge.** `ros-humble-foxglove-bridge` (3.4.3 in apt, arm64), with a topic allow-list.
- [ ] **Foxglove layouts**, versioned in the repo. Reuse what applies from `racing_kart_v2x`.

## 4. Unified web UI

One page, tabs, replacing the separate dashboards. Shows "Autoware is not running" when the
graph is absent rather than blank panels.

- [ ] **Shell + tabs**, absorbing `tools/segway_dashboard` and the health monitor.
- [ ] **Foxglove topic configuration** editable from the UI.

## 5. Operator control

Separate backend process. Everything here is a write path.

- [ ] **Goal setter** — single goal, ordered multi-goal, and repeat mode looping last→first until stopped.
- [ ] **Sequencing mode switch** — step-by-step (advance on arrival) or single route with waypoints.
- [ ] **Operation buttons** — engage, operation mode, and stop.

## 6. Documentation

Not a phase. Every item above lands with its README written or revised in the same commit.

- [ ] Revise the top-level README for the Jetson/Segway/Livox platform.
