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

**The converter does not stay connected.** It enumerated correctly once, then dropped
after five seconds and never returned.

From `dmesg`, on the current boot:

```
[ 197.767] usb 1-4.2: new full-speed USB device number 4 using tegra-xusb
[ 197.947] usb 1-4.2: Detected FT232RL
[ 197.951] FTDI USB Serial Device converter now attached to ttyUSB0
[ 202.791] usb 1-4.2: USB disconnect, device number 4
[ 202.794] ftdi_sio 1-4.2:1.0: device disconnected
```

After `t=202 s` there are **no further USB events**, across nearly three hours of
uptime. A 90-second replug watch produced nothing: no enumeration, no error, no
device-present signal at all. `/sys/bus/usb/devices/` shows the hub `1-4` with no child.

### What this means

The five seconds of clean operation prove the converter, its FTDI chip, and the driver
stack all work. There were **no USB errors** — no `error -71`, no descriptor-read
failure, no over-current. That is the signature of a connection that is *electrically
absent*, not one that is failing to negotiate.

Ranked causes:

1. **The mini-USB cable is charge-only or has broken data lines.** Very common with
   mini-USB. A charge-only cable would give exactly this: nothing on the bus.
2. **The mini-USB connector is loose or intermittent.** Mini-USB retention is weak and
   wears out; the 5-second window looks like a connection that seated briefly.
3. Converter lost power.

A merely *flaky* cable usually shows repeated connect/disconnect cycles or enumeration
errors. One clean connect, one clean disconnect, then silence points at the cable or
connector rather than at the converter or the Jetson.

### Next steps

1. **Swap the mini-USB cable** for a known-good data cable. This is the single most
   likely fix.
2. Watch enumeration live while plugging in:

   ```bash
   sudo dmesg -w | grep -iE 'usb|ftdi|ttyUSB'
   ```

   Expect `Detected FT232RL` then `attached to ttyUSB0` within a second.
3. Try a different USB port — preferably a direct Jetson port rather than through the
   Realtek hub, to take the hub out of the picture.
4. Confirm the port survives: `ls /dev/ttyUSB0` a minute after plugging in.

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
