# Segway RMP dashboard

A live web view of the Segway RMP chassis — connection state, battery, mode, odometry,
firmware versions and per-board error codes — plus an optional touch **Control** tab for
driving it from a phone or tablet.

**Read-only by default.** Without `--allow-control` the server never binds
`set_cmd_vel()` or `set_enable_ctrl()` at all, so it has no callable path to motion.

![layout](https://img.shields.io/badge/stack-python%20stdlib%20only-blue)

## What it shows

| Panel | Contents |
|---|---|
| Banner | Whether the port is open and whether the chassis is actually replying |
| Battery | State of charge, voltage, current, temperature, charging flag, voltage sparkline |
| Chassis mode | FSM state decoded to a name, wheel power, control source, load setting |
| Odometer | Total distance, plus the chassis's own speed limits |
| Link | Port, baud, open/replying status |
| Firmware | Central, motor and host-library versions, and whether they match |
| Error state | `get_err_state()` for host, central, both motor boards and BMS |

A version reading `0xFFFF` means the chassis sent no reply; the UI dims and says so
rather than showing stale numbers.

## Requirements

- Python 3 (standard library only — no pip install)
- The vendor SDK `libctrl_arm64-v8a.so`, which ships with the `segway_rmp` branch of
  [`adeeb10abbas/segway_ros2`](https://github.com/adeeb10abbas/segway_ros2):

  ```bash
  git clone -b segway_rmp https://github.com/adeeb10abbas/segway_ros2.git
  # library lands at segway_ros2/segwayrmp/lib/libctrl_arm64-v8a.so
  ```

The library is **not vendored here** — it is a third-party binary blob, and pinning a
copy in this repo would hide upstream changes.

**On this Jetson it is already installed at:**

```
/home/tlab/workspace/segway_ros2/segwayrmp/lib/libctrl_arm64-v8a.so
```

## Running

```bash
# read-only dashboard
sudo ./server.py --lib /home/tlab/workspace/segway_ros2/segwayrmp/lib/libctrl_arm64-v8a.so

# with the Control tab enabled
sudo ./server.py --lib /home/tlab/workspace/segway_ros2/segwayrmp/lib/libctrl_arm64-v8a.so \
    --allow-control --max-linear 0.4 --max-angular 0.6
```

To leave it running after you disconnect:

```bash
sudo setsid nohup ./server.py --lib <path> >/dev/null 2>&1 < /dev/null &
```

Discarding stdout matters — the SDK prints `host firmware version is older!` on a loop
(see Notes), which will fill a log file otherwise.

Then open <http://localhost:8080/>, or from another machine on the LAN,
`http://<jetson-ip>:8080/` (it binds all interfaces by default).

Options:

| Flag | Default | Meaning |
|---|---|---|
| `--lib` | *required* | Path to `libctrl_arm64-v8a.so` |
| `--serial` | `ttyUSB0` | Device name under `/dev` |
| `--port` | `8080` | HTTP port |
| `--host` | `0.0.0.0` | Bind address; use `127.0.0.1` to keep it local |
| `--allow-control` | *off* | Expose the motion endpoints and the Control tab |
| `--max-linear` | `0.5` | Linear speed cap, m/s |
| `--max-angular` | `0.8` | Angular speed cap, rad/s |

### Why root

The SDK shells out to `sudo chmod` and `sudo stty` on the serial device during
`init_control_ctrl()`. Running the server as root lets those succeed silently. Being in
the `dialout` group is still worth having, but it is not sufficient on its own.

If you would rather not run it as root, the alternative is a passwordless sudoers entry
for those two commands — not set up here.

## Driving from a phone or tablet

Start with `--allow-control`, open `http://<jetson-ip>:8080/` on the device, and switch
to the **Control** tab.

1. **Release the hardware E-stop.** While it is engaged the chassis reports mode 3 and
   shields both speed and enable commands — the UI says so and keeps Enable disabled.
2. **Press Enable.** This calls `set_enable_ctrl(1)`; the chassis moves from lock mode
   into vehicle control mode.
3. **Hold the joystick.** Up is forward, left/right turns. The knob springs back to
   centre on release and a zero command is sent immediately.

### Safety design

Driving a robot over WiFi from a browser fails in specific ways, so there are four
independent layers that stop the chassis:

| Layer | Behaviour |
|---|---|
| Chassis firmware | Declares communication failure and leaves control mode if it gets no command for **150 ms** (manual, `set_cmd_vel`). This is the backstop and needs no cooperation from us. |
| Server deadman | If no client command arrives for **400 ms**, the server zeroes the target, calls `set_enable_ctrl(0)`, and marks the deadman tripped. Covers a dropped phone, a locked screen, a dead WiFi link. |
| Browser | Releasing the knob, switching tabs, backgrounding the page, or losing the server all send zero and stop the transmit loop. |
| Speed caps | `--max-linear` / `--max-angular` clamp **server-side**, so a malformed or hostile POST cannot exceed them. The slider only scales within that cap. |

The transmit rates are layered deliberately: the browser posts at 10 Hz, the server
retransmits to the chassis at 20 Hz, and the chassis gives up at 150 ms. Each layer is
faster than the one it protects.

The red **STOP** button zeroes velocity and drops the enable. It is a software stop —
**it is not a substitute for the hardware E-stop**, which is the only thing that cuts
motor power.

### Before the first drive

Wheels off the ground, or a clear space with the hardware E-stop in reach. Start with
`--max-linear 0.2` to confirm the direction conventions before opening it up.

## JSON API

`GET /api/status` returns the full snapshot, refreshed twice a second by a background
thread. Useful for scripting or feeding another tool:

```bash
curl -s localhost:8080/api/status | jq .battery
```

With `--allow-control`, three POST endpoints exist. Each returns JSON:

```bash
curl -X POST localhost:8080/api/enable  -d '{"on":true}'
curl -X POST localhost:8080/api/cmd_vel -d '{"linear":0.2,"angular":0.0}'
curl -X POST localhost:8080/api/estop
```

`cmd_vel` must be repeated inside the 400 ms deadman window or the chassis is disabled.
Without `--allow-control` all three return HTTP 403.

```json
{
  "link":     { "port": "/dev/ttyUSB0", "baud": 921600,
                "port_open": true, "chassis_responding": true },
  "mode":     { "raw": 3, "name": "Emergency stop", "wheels": "Wheels unpowered" },
  "battery":  { "soc": 53, "millivolts": 37080, "milliamps": 130 },
  "versions": { "central": "0x2028", "match": "host-older" },
  "any_error": false
}
```

## Notes

- **`host-older` is expected.** The bundled SDK is the RMP220 build (`0x2027`) and this
  chassis runs `0x2028`. Telemetry and control work regardless, but newer chassis
  features may not be exposed.
- **Speed and encoder ticks are not shown.** Those arrive through the SDK's callback
  registration (`aprctrl_datastamped_jni_register`) rather than simple getters, which
  needs a C shim to bridge into Python. Everything on the dashboard comes from
  poll-style getters.
- See [`docs/SEGWAY.md`](../../docs/SEGWAY.md) for wiring, the connector pinout, and the
  troubleshooting history.
