# Segway RMP base (RMP Plus 401 / 14 P01R POLUS)

Notes for driving the Segway chassis from the Jetson AGX Orin.

State as of 2026-09-05. **The link is not working** — the USB-serial converter drops off
the bus. See [Current status](#current-status).

## References

- [User manual — RMP Plus 401 (2023-03-01)](https://cdn.robotshop.com/rbm/e40a85cf-9ab9-4664-b045-f28aab26e201/2/201cdb19-ab7b-4e20-965c-085db56b8ddf/d5af6b63_user-manual-for-rmp-plus-401-20230301.pdf)
  — RobotShop CDN. Blocks automated fetching (HTTP 403); download it in a browser.
- [`adeeb10abbas/segway_ros2`](https://github.com/adeeb10abbas/segway_ros2)
  — ROS 2 driver. The low-level code is on the **`segway_rmp` branch**, not `main`.

## Hardware and connection path

| | |
|---|---|
| Chassis | Segway RMP Plus 401, part `14 P01R POLUS` |
| Host | NVIDIA Jetson AGX Orin Developer Kit |
| L4T | R36.5.0 (JetPack 6), kernel `5.15.185-tegra` |

The chassis is **not** wired to the 40-pin header. The path is:

```
RMP chassis  --TX/RX/GND-->  converter board (per manual)  --mini-USB-->  USB  -->  Jetson
```

The converter is an **FTDI FT232RL**. When present it enumerates as `/dev/ttyUSB0`,
behind the Realtek hub at USB path `1-4.2`. The `ftdi_sio` driver is already in the
kernel and binds automatically — no driver install is needed.

Because the converter handles the level conversion, the Jetson's 3.3 V header pins are
not involved and `ttyTHS*` is irrelevant here.

## Current status

**Serial link is up. The chassis does not transmit unsolicited.** Tested 2026-09-05.

### Connection resolved

The port now enumerates and stays stable:

```
Bus 001 Device 006: ID 10c4:ea60 Silicon Labs CP210x UART Bridge
[15:24:03] usb 1-4.2: cp210x converter now attached to ttyUSB0
```

Note this is a **CP2102**, a different converter from the **FT232RL** seen earlier at
12:17 — that one enumerated for five seconds and never returned. Two cables were tried
against the FTDI with no effect; the working setup uses the CP210x. Whether the FTDI
unit is faulty is untested.

`/dev/ttyUSB0` held for 10 s with no dropout, which the FTDI never managed.

### But the chassis is silent

Passive listen on `/dev/ttyUSB0`, 2 s per rate — **zero bytes at every baud**:

```
115200 / 230400 / 460800 / 921600 / 57600 / 9600  ->  0 bytes
```

Modem lines read `CTS: low, DSR: low, CD: low`. That is expected here and **not** a
fault — only TX/RX/GND are wired, so the handshake lines are simply absent.

### Interpretation

The RMP does not appear to stream feedback on its own; it needs the host to initiate.
This matches the SDK design, where `init_control_ctrl()` opens the port and starts a
comms thread rather than merely listening.

Remaining unknowns, in the order they should be resolved:

1. **Does the chassis need a host request?** Likely. Confirming means writing to a
   powered mobile base — see Safety before doing it.
2. **Are TX and RX crossed correctly?** Converter TX → chassis RX, converter RX →
   chassis TX. Silence looks identical either way, so this cannot be ruled out from
   software.
3. **What baud does the 401 use?** Not in the driver source; it is computed inside the
   closed library. Get it from the manual.

### Toolchain on this machine

**ROS 2 is not installed** (`/opt/ros` does not exist), so the `segway_ros2` driver
cannot be built or launched here yet. `gcc` is available, so the vendor SDK
(`libctrl_arm64-v8a.so`, aarch64) can be linked directly from a small C program for a
first handshake test without a full ROS 2 install.

## Verifying the link

Once `/dev/ttyUSB0` is stable, listen **passively** first. The chassis may stream
feedback on its own; if bytes arrive, the wiring and baud are right. This sends nothing
to the robot, so it cannot cause motion.

```bash
for baud in 115200 230400 460800 921600; do
  stty -F /dev/ttyUSB0 $baud raw -echo
  n=$(timeout 2 cat /dev/ttyUSB0 | wc -c)
  echo "$baud: $n bytes"
done
```

- **Steady framing at one baud** — link good, note that baud.
- **Bytes at every baud, all garbage** — wrong baud, or TX/RX swapped at the converter.
- **Zero bytes** — check TX/RX are crossed (chassis TX → converter RX), grounds common,
  chassis powered and out of E-stop. Some RMP firmware also stays silent until the host
  sends a heartbeat; that means writing to a powered base, so resolve the wiring first.

The baud rate is **not documented in the driver source** — it is computed inside a
closed prebuilt library (see below). Confirm it from the manual or empirically; do not
assume 115200.

### Permissions

`tlab` was not in `dialout`, which would have blocked port access independently of the
cable fault. Fixed 2026-09-05:

```bash
sudo usermod -aG dialout tlab      # done; re-login for it to apply to your shell
id -nG | grep dialout              # confirm
```

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

The default `ttyUSB0` matches this setup, so no parameter override is needed — provided
the converter stays enumerated and is the only USB-serial device attached.

Feedback topics come from `segway_msgs`: `BmsFb` (battery), `ChassisModeFb`, `SpeedFb`,
`TicksFb` (encoders), `ErrorCodeFb`, `MotorWorkModeFb`, `ChassisMileageMeterFb`.
Control is via services — `RosSetChassisEnableCmd` (enable motors), `RosSetVelMaxCmd`,
`RosSetChassisPoweroffCmd`, and the rotate/buzzer commands.

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
`can0`/`can1` (currently `DOWN`). If the USB link stays unreliable, CAN avoids the
converter and its cable entirely — see
[VEHICLE_CAN_AND_RUNTIME.md](VEHICLE_CAN_AND_RUNTIME.md) for bring-up on this machine.

## Safety

The RMP is a powered mobile base. When testing:

- Wheels off the ground, or E-stop within reach.
- Listen passively before writing anything to the port.
- `RosSetChassisEnableCmd` energises the motors — expect movement after it.
