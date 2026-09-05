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

**Working.** The chassis communicates over serial and reports live telemetry.
Verified 2026-09-05.

```
serial open success! serial port:/dev/ttyUSB0, baud:921600

  host_version      : 0x2027      <- the SDK library
  central_version   : 0x2028      <- chassis central board, replying
  motor_version     : 0x2028      <- motor board, replying
  chassis_mode      : 3           <- emergency stop mode
  work_model        : 0           <- wheels unpowered
  bat_soc           : 53 %
  bat_mvol          : 37080 mV    <- 37.1 V on a 36 V pack
  vehicle_meter     : 2977 m
  err_state(Central): 0x00000000  <- no faults
  version_matched   : 0x0002      <- host library older than chassis firmware
```

`0xFFFF` on any version field means no reply; anything else means the chassis is
answering. See [Probing the chassis](#probing-the-chassis) to re-test.

### Two things to know about this state

**The E-stop is engaged.** `chassis_mode: 3` is emergency-stop mode and `work_model: 0`
means the wheels have no power. This is the safe resting state, not a fault — note
`err_state` is clean. Per Appendix 1, the sequence to motion is:

```
E-stop released      -> mode 0 (lock mode)
enable command sent  -> mode 1 (vehicle control mode)   <- wheels live
```

**The SDK library is older than the chassis firmware.** `version_matched: 0x0002` is the
SDK's "host version older" code (`0x2027` vs `0x2028`), and it prints
`host firmware version is older!`. Basic telemetry and control work regardless, but
newer chassis features may not be exposed. This is expected — the library shipped with
the RMP220 driver, not with the 401.

### How it was fixed

The link was dead until the chassis wiring was corrected against the manual's pinout
(below). The Jetson side needed only the `dialout` group fix; the converter, cable, port
and driver stack were all fine once the chassis wires were right.

Diagnostic history, for reference: an FT232RL enumerated for 5 s then vanished and never
returned across two cable swaps; a CP2102 was substituted and has been stable since.
Whether the FTDI unit is faulty was never established.

### Connector pinout (manual, Appendix 3)

The chassis 8-pin connector. **Only pins 3, 4, 5 are the serial port:**

| Pin | Signal | Colour | Group |
|-----|--------|--------|-------|
| 1 | CANH | Red | CAN |
| 2 | CANL | Gray | CAN |
| **3** | **TX** | **Blue** | **Serial port** |
| **4** | **RX** | **Green** | **Serial port** |
| **5** | **GND** | **White** | **Serial port** |
| 6 | 5V | Brown | Remote-control receiver |
| 7 | GND | Black | Remote-control receiver |
| 8 | S.B PPM | Yellow | Remote-control receiver |

The 2-pin connector is power only: Power+ (Red), Power− (Black), AWG16.

**Two wiring traps this table exposes:**

1. **The serial ground is pin 5, the WHITE wire** — not the black one. Black (pin 7) is
   the *remote-control receiver* ground. Using black for serial ground is the obvious
   mistake, since black conventionally means ground.
2. **TX/RX are named from the chassis's point of view.** Pin 3 "TX" is the chassis
   transmitting. So it must go to the converter's **RX**:

   ```
   chassis pin 3 TX   (Blue)  ->  converter RX
   chassis pin 4 RX   (Green) ->  converter TX
   chassis pin 5 GND  (White) ->  converter GND
   ```

   Wiring blue-to-TX and green-to-RX "matching the labels" is wrong and produces exactly
   the silence observed.

### What the manual does NOT specify

- **No baud rate anywhere in the 59 pages.** The only source remains the SDK's own
  output: **921600**.
- **No signal voltage** (3.3 V vs 5 V TTL). The spec table lists the communication
  interface as **"UART, CAN"** — so it is TTL-level, *not* RS-232. A CP2102/FT232 TTL
  bridge is therefore the right class of converter; an RS-232 transceiver would be wrong.

### Remaining causes

With the host side proven and the pinout known, the fault is in the chassis wiring:

1. **TX/RX not crossed** — see the trap above. Most likely cause.
2. **Wrong ground wire** — black (pin 7) used instead of white (pin 5).
3. **Chassis state** — powered, out of E-stop, and not in a mode that disables serial
   control. See the mode-switching table in Appendix 1.

### Probing the chassis

A minimal read-only probe against the vendor SDK, useful for re-testing after rewiring.
It calls only the connect path and status getters — never `set_cmd_vel` or
`set_enable_ctrl`, so it cannot command motion:

```c
set_smart_car_serial("ttyUSB0");
set_comu_interface(comu_serial);
init_control_ctrl();
/* then poll get_chassis_central_version(), get_bat_soc(), ... */
```

Build against the SDK (needs an rpath — `sudo` strips `LD_LIBRARY_PATH`):

```bash
gcc -o rmp_probe rmp_probe.c -I segwayrmp/include \
    -L segwayrmp/lib -lctrl_arm64-v8a -lpthread -Wl,-rpath,$PWD/segwayrmp/lib
sudo ./rmp_probe
```

`central_version` reading anything other than `0xffff` means the chassis is talking.

The SDK also prints a request for a `password.txt` from Ninebot and an administrator
password. That is only for the firmware-upgrade (IAP) paths — basic communication works
without it, as shown above.

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

## Live dashboard

A read-only web view of everything above lives in
[`tools/segway_dashboard/`](../tools/segway_dashboard/):

```bash
sudo tools/segway_dashboard/server.py --lib /path/to/libctrl_arm64-v8a.so
# then open http://<jetson-ip>:8080/
```

It shows connection state, battery, chassis mode, odometry, firmware versions and
per-board error codes, and exposes the same data as JSON at `/api/status`. It never
sends motion commands. See its README for details.

## Safety

The RMP is a powered mobile base. When testing:

- Wheels off the ground, or E-stop within reach.
- Listen passively before writing anything to the port.
- `RosSetChassisEnableCmd` energises the motors — expect movement after it.
