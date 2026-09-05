# Segway RMP dashboard

A live web view of the Segway RMP chassis — connection state, battery, mode, odometry,
firmware versions and per-board error codes.

**Read-only.** The server calls only the SDK's status getters, never `set_cmd_vel()` or
`set_enable_ctrl()`, so it cannot command motion.

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

## Running

```bash
sudo ./server.py --lib /path/to/libctrl_arm64-v8a.so
```

Then open <http://localhost:8080/>, or from another machine on the LAN,
`http://<jetson-ip>:8080/` (it binds all interfaces by default).

Options:

| Flag | Default | Meaning |
|---|---|---|
| `--lib` | *required* | Path to `libctrl_arm64-v8a.so` |
| `--serial` | `ttyUSB0` | Device name under `/dev` |
| `--port` | `8080` | HTTP port |
| `--host` | `0.0.0.0` | Bind address; use `127.0.0.1` to keep it local |

### Why root

The SDK shells out to `sudo chmod` and `sudo stty` on the serial device during
`init_control_ctrl()`. Running the server as root lets those succeed silently. Being in
the `dialout` group is still worth having, but it is not sufficient on its own.

If you would rather not run it as root, the alternative is a passwordless sudoers entry
for those two commands — not set up here.

## JSON API

`GET /api/status` returns the full snapshot, refreshed twice a second by a background
thread. Useful for scripting or feeding another tool:

```bash
curl -s localhost:8080/api/status | jq .battery
```

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
