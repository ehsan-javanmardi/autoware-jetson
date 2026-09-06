# Foxglove

Watching Autoware from an iPad or a browser, without RViz and without a screen on the
robot.

```bash
ros2 launch foxglove_bridge foxglove_bridge_launch.xml \
  port:=8765 topic_whitelist:="$(./foxglove/build_whitelist.py)"
```

Then connect from the Foxglove iPad app or `app.foxglove.dev` to:

```
ws://<jetson-ip>:8765
```

On the lab wifi that is `ws://192.168.10.15:8765`. Load a layout from
[`layouts/`](layouts) once connected.

## Why a topic allow list

The bridge serialises every advertised topic for every connected client. Advertising
everything (`.*`) on an Orin that shares one memory pool between CPU and GPU is enough to
take time away from the planner, and the raw Livox cloud alone is ~45 000 points at 10 Hz.

[`topics.yaml`](topics.yaml) is the single source of truth for what is exposed. It is
grouped so that the web UI can offer checkboxes rather than a regex box:

| Group | What | Default |
|---|---|---|
| `core` | `/tf`, `/tf_static`, `/diagnostics` | always on, cannot be switched off |
| `map` | lanelet2 vector map, pointcloud map | on |
| `localization` | kinematic state, pose with covariance, GNSS pose | on |
| `sensing` | concatenated cloud, corrected IMU | on |
| `perception` | detected, tracked and predicted objects, occupancy grid | on |
| `planning` | trajectory, route, behaviour path | on |
| `vehicle` | velocity, steering, control mode, operation mode | on |
| `heavy` | pre-preprocessing Livox cloud, cameras | **off** |

`core` carries `always: true`, so it survives any group filter — a layout without `/tf`
shows objects and clouds in the wrong place, or not at all, which is a confusing way to
discover you deselected a transform.

## Changing what is exposed

```bash
./foxglove/build_whitelist.py                          # enabled groups
./foxglove/build_whitelist.py --groups core,map,planning
./foxglove/build_whitelist.py --all                    # includes heavy
./foxglove/build_whitelist.py --format lines           # one per line, for reading
```

`foxglove_bridge` reads `topic_whitelist` **once at startup and has no reload**, so
changing the selection means restarting the bridge. That is why the web UI's Foxglove tab
restarts it rather than pushing a live update.

Plain topic names are `re.escape`d before being handed over; entries containing `.*` or
`[` are passed through as written, so `/sensing/camera/.*` works as a pattern.

## RViz and Foxglove

RViz stays available but is **off by default** on this platform — it costs GPU the Orin
would rather spend on perception, and it needs a screen. Foxglove replaces it for
day-to-day work. Turn RViz on with the launch script's `rviz:=true`.

## What is not here

`racing_kart_v2x` was expected to have Foxglove material to reuse. It does not — the
repository contains no Foxglove configuration of any kind. What it does have is
`v2x_web_monitor`, built on stdlib `http.server` plus Server-Sent Events, the same
architecture as `health_ui`. That informed the web UI work rather than this.
