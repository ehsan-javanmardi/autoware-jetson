# Web UI

One page at **`http://<jetson-ip>:8842`**, with tabs, replacing the separate dashboards.

```bash
ros2 launch segway_web_ui      web_ui.launch.xml       # the page,    :8842
ros2 launch segway_web_control web_control.launch.xml  # the buttons, :8843
```

Two packages, at two layers, easy to confuse with a third:

| Package | What it is |
|---|---|
| `segway_vehicle_interface` | The **chassis driver**. Talks to the Segway over `/dev/segway`. The only thing allowed to open that port. No web anything. |
| `segway_web_ui` | The **page**. Subscribes to ROS, serves HTML. Creates no publishers or service clients, so it cannot command the vehicle. |
| `segway_web_control` | The **write paths**. Owns every publisher and service client the UI needs: Autoware lifecycle, control mode, teleop. |

You only ever open `:8842` in a browser. `:8843` is a JSON API the page calls in the
background; visiting it directly returns `{"error": "not found"}`.

| Tab | Sub-tab | Shows |
|---|---|---|
| **Hardware** | Sensors | Every sensor: reachable, publishing, at what rate |
| | Vehicle chassis | Segway link, control mode, battery, speed |
| **Foxglove** | | Bridge state and the address to connect the app to |
| **Autoware** | Run | Start and stop Autoware |
| | Health | The diagnostic module tree, and what is unhealthy |
| | Events | The diagnostic event log |
| | Destinations | Engage, stop, and the goal sequencer |
| **Remote drive** | | Hold-to-drive teleop, enable/disable, and the e-stop |

Health checking sits **inside** the Autoware tab rather than beside it, because it is only
meaningful when Autoware is running; hardware health is a different question and lives in
the Hardware tab, which works whether Autoware is up or not.

When Autoware is not running the tabs say so rather than showing blank panels — the
Vehicle tab prints the command to start the interface, and the Foxglove tab the command to
start the bridge.

## Three processes, and the Remote drive tab needs all of them

| | Command | Port |
|---|---|---|
| The page | `ros2 launch segway_web_ui web_ui.launch.xml` | 8842 |
| The buttons | `ros2 launch segway_web_control web_control.launch.xml` | 8843 |
| The chassis | `ros2 launch segway_vehicle_interface segway_vehicle_interface.launch.xml allow_control:=true` | — |

The Hardware and Foxglove tabs need only the first. Autoware and Remote drive need all
three, and the tabs list every prerequisite with its state rather than reporting only the
first missing one — otherwise you start one, reload, and are told about the next.

`./autoware_kashiwa.sh` starts the vehicle interface itself, so with the full stack running
only the two web processes remain to launch.

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
| 8842 | `segway_web_ui` — this dashboard | no, by construction |
| 8765 | `foxglove_bridge` | no |
| 8843 | control backend (goals, engage, limits) | **yes** |
