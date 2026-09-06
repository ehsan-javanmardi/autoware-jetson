# Running this robot

Two ways to bring the system up. **Never both at once.**

## The everyday one: `./segway.sh`

```bash
./segway.sh
```

Starts everything that should stay up — Livox, GNSS/RTK, the vehicle interface, the web
UI and the Foxglove bridge — and nothing that shouldn't.

```
web UI    http://<jetson>:8842
foxglove  ws://<jetson>:8765
logs      ~/.segway/logs/
```

**Autoware is not part of it.** Start Autoware from the web UI's Autoware → Run tab, and
stop it again, as many times as you like: the sensors, the chassis and this page are
untouched by either. That is the whole reason the platform and the autonomy stack are
separate process trees.

When the platform is up, the control backend notices and starts Autoware with
`launch_sensing_driver:=false launch_vehicle_interface:=false`, so Autoware is only the
autonomy layer. The Run tab tells you which mode it is about to use.

| Variable | Default | |
|---|---|---|
| `ALLOW_CONTROL` | `true` | `false` brings the platform up unable to move the base |
| `WITH_SENSORS` | `true` | `false` skips the Livox and GNSS |
| `WITH_FOXGLOVE` | `true` | |
| `LOG_DIR` | `~/.segway/logs` | |

## The self-contained one: `./autoware_all.sh`

```bash
./autoware_all.sh [map_dir] [args...]
```

Autoware plus its own sensor drivers and vehicle interface, plus the web UI and Foxglove,
in one process tree. Ctrl-C stops the lot. Use it when a single Autoware run is the point
and nothing needs to outlive it.

## Who starts the sensors

This surprises people, so it is worth stating plainly.

| | Started by |
|---|---|
| Sensor **drivers** (Livox, u-blox, NTRIP) | **`segway.sh`** |
| The `/sensing` chain — `gnss_poser`, `imu_corrector`, pointcloud preprocessing | **Autoware** |

`launch_sensing_driver:=false` disables only the drivers. `launch_sensing` stays true, so
Autoware still builds the processing chain around whatever is already publishing. That is
what lets Autoware start and stop without the sensors restarting with it.

### The namespace has to match, and it is easy to get wrong

`gnss.launch.xml` pushes a **relative** `gnss` namespace. Launched at the root it puts the
receiver on `/gnss/fix`, while Autoware's own `gnss_poser` waits on `/sensing/gnss/fix`.
You then get **two `gnss_poser` nodes, one of them starved**, and a localization stack with
no GNSS — with no error that names the cause.

`platform_sensors.launch.xml` exists for this. It pushes `sensing` and starts **only the
drivers**, leaving `gnss_poser`, `imu_corrector` and the pointcloud preprocessing to
Autoware, which would otherwise duplicate them.

The Livox launch is unaffected either way because its remaps are absolute, but it goes
through the same file so that everything the platform starts is described in one place.

If GNSS looks dead with Autoware running, check this first:

```bash
ros2 node list | grep gnss_poser        # expect exactly one, under /sensing
ros2 topic info /sensing/gnss/fix       # expect one publisher
```

## Why they must not overlap

> [!WARNING]
> Both start a vehicle interface, and **two cannot share the chassis serial port.**
>
> The vendor SDK does not report the conflict. The second process to open the port gets a
> success return and `serial open success` in its log, then reads `0xffff` for every
> value — while degrading the link for the first. Neither process looks broken. The
> chassis simply stops making sense, and the obvious conclusion is that the hardware has
> failed.
>
> Both scripts check for this at startup and refuse rather than let it happen. That check
> is worth more than this warning: a documented hazard only helps someone who read the
> document.

The same applies to the sensors, less dangerously — two Livox drivers fight over the same
UDP ports, and neither gets a full point cloud.

## What runs where

| | `segway.sh` | `autoware_all.sh` | Started from the UI |
|---|---|---|---|
| Livox HAP | ✅ | ✅ (via Autoware) | — |
| GNSS + RTK | ✅ | ✅ (via Autoware) | — |
| Vehicle interface | ✅ | ✅ (via Autoware) | — |
| Web UI + control | ✅ | ✅ | — |
| Foxglove bridge | ✅ | ✅ | — |
| **Autoware** | ❌ | ✅ | ✅ autonomy layer only |

## Stopping

Ctrl-C in the terminal running the script. Both stop their children in reverse order, so
the vehicle interface shuts down last — after nothing is still publishing to it, and while
its own shutdown path can still zero the command and disable the motors.

Stopping Autoware from the web UI sends SIGINT to its whole process group, because
`ros2 launch` spawns children that killing the shell alone would orphan.
