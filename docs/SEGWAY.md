# Segway RMP base (RMP Plus 401 / 14 P01R POLUS)

Notes for driving the Segway chassis from the Jetson AGX Orin.

State as of 2026-09-05. **The serial link has not yet been verified** — see
[Current status](#current-status) for what is blocking it.

## References

- [User manual — RMP Plus 401 (2023-03-01)](https://cdn.robotshop.com/rbm/e40a85cf-9ab9-4664-b045-f28aab26e201/2/201cdb19-ab7b-4e20-965c-085db56b8ddf/d5af6b63_user-manual-for-rmp-plus-401-20230301.pdf)
  — RobotShop CDN. Blocks automated fetching (HTTP 403); download it in a browser.
- [`adeeb10abbas/segway_ros2`](https://github.com/adeeb10abbas/segway_ros2)
  — ROS 2 driver. The low-level code is on the **`segway_rmp` branch**, not `main`.

## Hardware

| | |
|---|---|
| Chassis | Segway RMP Plus 401, part `14 P01R POLUS` |
| Host | NVIDIA Jetson AGX Orin Developer Kit |
| L4T | R36.5.0 (JetPack 6), kernel `5.15.185-tegra` |
| Link | TX / RX / GND on the 40-pin header (no USB-serial adapter present) |

## Serial ports on this Jetson

The chassis is wired to the 40-pin header, so it lands on a Tegra hardware UART
(`ttyTHS*`), not a `ttyUSB*`. `lsusb` shows no USB-serial adapter, which confirms this.

```
/dev/ttyTHS1  ->  3100000.serial   (UARTA)
/dev/ttyTHS2  ->  3110000.serial   (UARTB)
```

**No console conflict.** On many Jetson setups a getty holds the 40-pin UART and fights
the robot for the port. Not the case here — the serial consoles are on other ports:

```
console=ttyTCU0,115200 console=ttyAMA0,115200   # /proc/cmdline
serial-getty@ttyTCU0 / @ttyAMA0 / @ttyGS0       # running
```

Nothing is bound to `ttyTHS1` or `ttyTHS2`, so no `systemctl disable` step is needed.

## Current status

The link **cannot be tested yet**. Two things block it, both needing `sudo`:

**1. The `tlab` user is not in `dialout`.** The ports are `crw-rw---- root dialout`, so
opening either one fails outright:

```bash
sudo usermod -aG dialout $USER
# then log out and back in (or `newgrp dialout` for the current shell only)
id -nG | grep dialout      # confirm before continuing
```

**2. `pyserial` is not installed**, needed for the check script below:

```bash
sudo apt install python3-serial      # or: pip3 install pyserial
```

## Verifying the link

Once the two blockers above are cleared, listen **passively** first. The chassis streams
feedback frames on its own; if bytes arrive, TX/RX/GND are correct and the baud matches.
This sends nothing to the robot, so it cannot cause motion.

```bash
python3 - <<'PY'
import serial, time
PORT = "/dev/ttyTHS1"          # try ttyTHS2 if silent
for baud in (115200, 460800, 230400, 921600):
    with serial.Serial(PORT, baud, timeout=0.5) as s:
        s.reset_input_buffer()
        data = b""
        t = time.time()
        while time.time() - t < 2:
            data += s.read(256)
        print(f"{baud:>7}: {len(data):5d} bytes  {data[:24].hex(' ')}")
PY
```

Reading the result:

- **Steady, repeating framing at one baud** — link is good, note that baud.
- **Bytes at every baud, all garbage** — wrong baud, or TX/RX swapped.
- **Zero bytes everywhere** — try `ttyTHS2`; then check TX↔RX are *crossed*
  (chassis TX → Jetson RX), that grounds are common, and that the chassis is powered
  and out of E-stop.

The baud rate is **not documented in the driver source** — it is computed inside a
closed prebuilt library (see below). Confirm it from the manual or empirically above;
do not assume 115200.

## ROS 2 driver

`segway_ros2` is a thin ROS 2 wrapper. Clone the `segway_rmp` branch:

```bash
git clone -b segway_rmp https://github.com/adeeb10abbas/segway_ros2.git
```

Its `segwayrmp` package selects the transport at init:

```cpp
n->declare_parameter<std::string>("segwaySmartCarSerial", "ttyUSB0");
set_smart_car_serial(serial.c_str());
set_comu_interface(comu_serial);   // or comu_can
init_control_ctrl();
```

Set `segwaySmartCarSerial` to `ttyTHS1` — the default `ttyUSB0` does not exist here.

Feedback topics come from `segway_msgs`: `BmsFb` (battery), `ChassisModeFb`, `SpeedFb`,
`TicksFb` (encoders), `ErrorCodeFb`, `MotorWorkModeFb`, `ChassisMileageMeterFb`.
Control is via services — `RosSetChassisEnableCmd` (enable motors),
`RosSetVelMaxCmd`, `RosSetChassisPoweroffCmd`, and the rotate/buzzer commands.

### Two caveats before relying on this driver

**It targets the RMP220, not the 401.** Its README says it drives "the RMP220 chassis",
and it derives from [`LuckierDodge/ROS2_ws_for_RMP220`](https://github.com/LuckierDodge/ROS2_ws_for_RMP220).
The RMP Plus 401 is a different chassis. The wire protocol may well be shared across the
RMP family, but that is an assumption to test, not a given — verify against the manual
before trusting odometry scaling or velocity limits.

**The protocol is closed source.** All framing lives in a prebuilt
`lib/libctrl_arm64-v8a.so`. It is genuine `ARM aarch64` and unstripped, so it will link
and run on the Orin, but the packet format cannot be inspected or patched — if the 401
differs from the 220, there is no source-level fix.

### CAN as an alternative

The driver supports CAN (`set_comu_interface(comu_can)`), and this Jetson already has
`can0`/`can1` (currently `DOWN`). If the UART proves troublesome, CAN is a supported
path — see [VEHICLE_CAN_AND_RUNTIME.md](VEHICLE_CAN_AND_RUNTIME.md) for bring-up on
this machine.

## Safety

The RMP is a powered mobile base. When testing:

- Wheels off the ground, or E-stop within reach.
- Listen passively before writing anything to the port.
- `RosSetChassisEnableCmd` energises the motors — expect movement after it.
