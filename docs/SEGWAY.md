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

**Not communicating.** The port opens and the Jetson UART is healthy, but the chassis
sends nothing. Tested 2026-09-05.

### What was fixed

`tlab` was not in `dialout`, so the ports could not be opened at all. Fixed:

```bash
sudo usermod -aG dialout tlab      # done; re-login for it to apply to your shell
```

### What was measured

Passive listen on both UARTs, 2 s each, four baud rates — **zero bytes everywhere**:

```
ttyTHS1 @ 115200/230400/460800/921600 :  0 bytes
ttyTHS2 @ 115200/230400/460800/921600 :  0 bytes
```

Holding `ttyTHS1` open for 5 s, the interrupt counter for `3100000.serial` did **not
move** (stayed at 2), and the only bytes ever captured were `00 00`:

```
112:   2   GICv3 144 Level  3100000.serial     # before and after 5 s of listening
$ xxd /tmp/ths1.bin
00000000: 0000                                 ..
```

Two null bytes with no interrupt activity is the signature of a **break condition or a
floating/idle-low RX line**, not data. Nothing is driving the Jetson's RX pin.

### What this rules in and out

- **Not a permissions problem** — fixed, ports now open.
- **Not a console conflict** — consoles are on `ttyTCU0`/`ttyAMA0`/`ttyGS0`.
- **Not a disabled UART** — `serial@3100000` and `serial@3110000` are both `status=okay`,
  and the IRQ registers when the port is opened.
- **The port is the right one.** `UART1_TX_PR2` / `UART1_RX_PR3` is controller
  `serial@3100000` = `/dev/ttyTHS1`, which is 40-pin header **pin 8 (TX)** and
  **pin 10 (RX)**. Use `ttyTHS1`.

### Prime suspect: signal levels

The Jetson 40-pin UART is **3.3 V TTL**. If the RMP's serial port is **RS-232**
(±12 V, typical of a DB9 on this class of chassis), then wiring TX/RX/GND straight to
the header will not communicate — and can damage the Jetson pin. **Confirm the chassis
serial voltage in the manual before applying power to that link again.** If it is
RS-232, an isolating transceiver (MAX3232-based) or a USB-RS232 adapter is required.

### Next steps, in order

1. **Loopback-test the Jetson UART.** Power down, jumper header **pin 8 to pin 10**
   (nothing else), then:

   ```bash
   stty -F /dev/ttyTHS1 115200 raw -echo
   (timeout 2 cat /dev/ttyTHS1 | xxd &) ; sleep 0.3 ; printf 'PING' > /dev/ttyTHS1 ; sleep 2
   ```

   `PING` echoed back proves the UART, pinmux and wiring path are all fine, and moves
   the fault to the robot side. Nothing echoed means the problem is on the Jetson.

2. **Check the RMP serial voltage level** in the manual (see Prime suspect above).

3. **Confirm TX/RX are crossed** — Jetson TX (pin 8) → chassis RX, Jetson RX (pin 10)
   → chassis TX. A straight-through pairing is silent in exactly this way.

4. **Only then** consider whether the chassis needs a host request before it will talk.
   Some RMP firmware stays silent until the host sends a heartbeat. That means writing
   to a powered base, so resolve items 1-3 first.

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
