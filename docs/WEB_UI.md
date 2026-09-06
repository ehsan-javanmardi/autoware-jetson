# Web UI

One page at **`http://<jetson-ip>:8842`**, with tabs, replacing the separate dashboards.

```bash
ros2 launch autoware_health_ui health_ui.launch.xml
```

| Tab | Shows |
|---|---|
| Overview | Autoware's diagnostic module tree, and what is unhealthy |
| Devices | Every sensor: reachable, publishing, at what rate |
| Events | The diagnostic event log |
| Vehicle | Segway chassis: mode, speed, yaw rate, battery, link state |
| Foxglove | Whether the bridge is up, and which topic groups it exposes |

When Autoware is not running the tabs say so rather than showing blank panels — the
Vehicle tab prints the command to start the interface, and the Foxglove tab the command to
start the bridge.

## Read-only by construction

This process creates **no ROS publishers and no service clients**. It subscribes, it pings,
and it serves a web page. That is a structural property, not a setting: there is no code
path from the dashboard to the vehicle, so no bug in it can move the robot.

Everything that writes — setting goals, engaging, changing speed limits, changing which
topics Foxglove exposes — belongs to a **separate control backend** on its own port. The
Foxglove tab is read-only for exactly this reason: changing the topic selection restarts
the bridge, and restarting a process is a write.

## The Vehicle tab does not touch the chassis

It reads `/vehicle/status/*` from ROS. That matters more than it looks.

> [!WARNING]
> **Only one process may hold `/dev/ttyUSB0`.** The Segway SDK does not arbitrate serial
> access and does not report a conflict. A second process calling `init_control_ctrl()`
> gets a success return and an open port, then reads `0xffff` for every value — and while
> it is attached, the link is unreliable for the vehicle interface too.
>
> Confirmed here: with `segway_vehicle_interface` running, a second probe reported
> `serial open success` and `central_version 0xffff` at the same time.
>
> `segway_vehicle_interface` owns the port. Anything else that wants chassis data reads the
> topics. This is why `tools/segway_dashboard`, which opens the SDK directly, **must not be
> run while Autoware is up** — it would degrade the control link, not merely show stale
> numbers.

To make that possible the vehicle interface publishes what the old dashboard read directly:

| Topic | Carries |
|---|---|
| `/vehicle/status/battery` | `sensor_msgs/BatteryState` — charge, voltage, chassis-present |
| `/diagnostics` | odometer, chassis mode, control source, firmware versions, control state |

## Distinguishing stopped from silent

A stationary robot and a dead interface both report zero speed. `/api/vehicle` therefore
returns `running` and `age_s` alongside the values, derived from when the last message
arrived, and the tab renders "not publishing" rather than a plausible-looking zero.

The same idea runs through the Devices tab: a sensor that answers its IP but publishes
nothing is broken, not absent, and is graded accordingly.

## Ports

| Port | Process | Writes? |
|---|---|---|
| 8842 | `autoware_health_ui` — this dashboard | no, by construction |
| 8765 | `foxglove_bridge` | no |
| 8843 | control backend (goals, engage, limits) | **yes** |
