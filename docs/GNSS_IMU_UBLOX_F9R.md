# SparkFun GPS-RTK Dead Reckoning (u-blox ZED-F9R) — RTK over ichimill

The GNSS/INS receiver for the Jetson + Segway platform.

> [!IMPORTANT]
> **Brought up on 2026-09-05. Everything works except the fix itself, which needs sky
> view.** Verified on this Jetson: the receiver enumerates, the driver drives it over
> libusb, `sensor_msgs/NavSatFix` publishes, and the NTRIP client authenticates to
> ichimill and holds an established TCP session. Not yet verified: an actual RTK fix,
> because the antenna had no sky view indoors. See
> [Verified state](#verified-state) for exactly what was and was not proven.

## The hardware

| | |
|---|---|
| Product | SparkFun GPS-RTK Dead Reckoning Kit (SMA), `KIT-23452` |
| Receiver | **u-blox ZED-F9R** |
| Constellations | GPS, GLONASS, Galileo, BeiDou (+ QZSS) |
| RTK | Rover only — needs a base or an NTRIP caster |
| IMU | Onboard 3D IMU, used by the receiver's own Automotive Dead Reckoning (ADR) fusion |
| Host interface | USB-C (also UART / I²C on the breakout) |

The **F9R** is the dead-reckoning variant, not the F9P. The distinction matters here: it
fuses its internal IMU, wheel ticks and a vehicle dynamics model with the GNSS solution,
so it keeps producing a position through short outages — tunnels, garages, under bridges.
On a Segway indoors that is the difference between a usable pose and none at all.

Dead reckoning needs the receiver rigidly mounted and its orientation configured
(`CFG_SFIMU_*`), and it self-calibrates while driving. Until that is done it behaves as a
plain GNSS receiver.

## What to install

Three apt packages, all available for arm64 on ROS 2 Humble. **No Autoware source changes
are needed for the receiver itself** — only sensor-kit launch wiring (below).

```bash
sudo apt install -y ros-humble-ublox-dgnss ros-humble-ublox-ubx-msgs
```

`ros-humble-ublox-dgnss` 0.7.5 pulls in `ublox_dgnss_node`, `ublox_nav_sat_fix_hp_node`
and `ntrip_client_node`.

### Why `ublox_dgnss` and not `ublox_gps`

The sensor kit's existing `ublox` branch points at `ublox_gps`, and it will not work here
for two independent reasons:

1. **`ublox_gps` cannot receive RTCM from ROS.** Its high-precision rover product only
   *monitors* the rate of RTCM arriving at the receiver, for diagnostics
   (`hpg_rov_product.hpp` declares `freq_rtcm_`, `kRtcmFreqMin`, and nothing that
   subscribes). It assumes corrections reach the receiver over a hardware port — a radio
   on UART2. Over a single USB CDC port there is no such path, so NTRIP corrections could
   never get in.
2. **The config it names does not exist.** `gnss.launch.xml` loads
   `$(find-pkg-share ublox_gps)/c94_f9p_rover.yaml`. `ublox_gps` 2.3.0 ships
   `c94_m8p_{base,rover}`, `c94_m8t_{base,rover}`, `neo_m8u_rover`, `nmea` and
   `zed_f9p` — there is no `c94_f9p_rover.yaml`, and no ZED-F9R config at all.

`ublox_dgnss` is built for this case: it drives the receiver over USB with libusb (no
`/dev/ttyACM` at all), names the ZED-F9R explicitly as a supported device, and ships an
NTRIP client whose RTCM output the driver node subscribes to. The topic
`ntrip_client/rtcm` is compiled into `libublox_dgnss_node.so`, so the loop closes inside
ROS with no serial-port sharing.

## "Can I just give it a gateway?" — no, and here is the distinction

Worth settling early, because the other receiver on this project works the opposite way.

The ZED-F9R has an **internal RTK engine**. It takes RTCM 3.x correction messages in on
any of its ports, and computes the centimetre-level fix itself. Nothing on the Jetson does
any RTK maths.

What it does **not** have is a **network stack**. It is a USB device — no IP address, no
Ethernet, no Wi-Fi, no TCP. It cannot open a socket to a caster, so there is nothing to
give a default gateway *to*. Corrections cannot reach it by routing; some process on the
host has to fetch the bytes and hand them over.

| | CHC CGI-410 ([GNSS_RTK.md](GNSS_RTK.md)) | ZED-F9R (this page) |
|---|---|---|
| Host link | Ethernet, own IP `192.168.1.110` | USB |
| Has an IP stack | Yes — web UI, own NTRIP client | **No** |
| Who connects to the caster | **The receiver** | **The Jetson** (`ntrip_client_node`) |
| What the host must provide | An IP route: static IP, NAT, `never-default` | Nothing at the network layer |
| RTK computed by | The receiver | The receiver |

So for the CGI-410, "give the receiver a gateway" is the whole job, and that is what the
NAT service in [GNSS_RTK.md](GNSS_RTK.md) exists for. For the F9R that idea does not
apply — there is no host to route.

The Jetson is still the gateway, just one layer up: it terminates the NTRIP connection
itself and relays RTCM into the receiver over USB. `ntrip_client_node` is that gateway.
It needs ordinary internet access on the Jetson (Wi-Fi or the USB modem) and no routing
configuration at all.

## Dataflow

```
ichimill caster                      Jetson                        ZED-F9R
ntrip.ales-corp.co.jp:2101
  │  RTCM 3.2 MSM7
  │                        ntrip_client_node
  └───────────────────────►   │
                              │  ntrip_client/rtcm  (rtcm_msgs/Message)
                              ▼
                         ublox_dgnss_node ──USB(libusb)──► receiver  ◄── corrections in
                              │
                              │  ubx_nav_hp_pos_llh  (UBXNavHPPosLLH)
                              ▼
                      ublox_nav_sat_fix_hp_node
                              │
                              │  sensor_msgs/NavSatFix
                              ▼
                    autoware_gnss_poser ──► /sensing/gnss/pose_with_covariance
```

The receiver also needs to send its own position back up to the caster as NMEA GGA —
ichimill's mount points are `nmea-required=1`, and a VRS caster cannot pick a base
without knowing roughly where you are. `ntrip_client_node` handles the GGA uplink.

## Credentials — keep them out of this repository

> [!WARNING]
> **This repository is public.** Do not commit the ichimill account IDs or passwords.
> There are four paid accounts on this contract; a leaked one is someone else using your
> correction stream.

`ntrip_client.launch.py` already defaults its `username` and `password` arguments from the
environment (`NTRIP_USERNAME`, `NTRIP_PASSWORD`), which is exactly the hook needed. Put
them in an untracked file:

```bash
cat > ~/.ichimill.env <<'EOF'
export NTRIP_USERNAME=<id>
export NTRIP_PASSWORD=<pass>
EOF
chmod 600 ~/.ichimill.env
```

Then `source ~/.ichimill.env` before launching. `~` is outside the repo, so there is
nothing to gitignore and nothing to leak by accident.

The non-secret half of the configuration is safe to record, and is here:

| Parameter | Value |
|---|---|
| Caster host | `ntrip.ales-corp.co.jp` |
| Port | `2101` (plain NTRIP — **not** HTTPS) |
| Mount point | `RTCM32M7S` — RTCM 3.2 MSM7, five constellations, crustal-deformation correction, automatic base handover |
| Fallback mount point | `RTCM32M5S` (MSM5) if the receiver rejects MSM7 |
| Accounts | Four ID/password pairs exist, one per simultaneous connection. Ask the platform owner; they are not in this repo. |

The ZED-F9R supports MSM7, so `RTCM32M7S` is the one to use.

## Bring-up

### 1. Confirm the receiver enumerates

```bash
lsusb | grep 1546          # u-blox vendor ID; expect a ZED-F9R
```

The kernel binds `cdc_acm` first, so `/dev/ttyACM0` *does* appear — but `ublox_dgnss`
does not use it. The driver claims the interface through libusb, at which point the
kernel logs:

```
cdc_acm: probe of 1-4.1:1.0 failed with error -16
```

`-16` is `EBUSY` and is **expected**: libusb took the interface. `/dev/ttyACM0` becomes
inert, and `dialout` group membership is irrelevant to this driver. What does matter is
the raw USB node under `/dev/bus/usb/`, which is `root:root` by default, so a udev rule
is required:

```bash
sudo tee /etc/udev/rules.d/99-ublox-f9r.rules <<'EOF'
SUBSYSTEM=="usb", ATTRS{idVendor}=="1546", MODE="0666"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger --action=add --subsystem-match=usb --attr-match=idVendor=1546
```

A bare `udevadm trigger` does **not** re-apply the mode to an already-attached device —
it has to be an explicit `--action=add` match, or you replug. Confirm it took:

```bash
ls -l /dev/bus/usb/001/*   # the u-blox node should be crw-rw-rw-
```

### 2. Start the receiver

```bash
source /opt/ros/humble/setup.bash
ros2 launch ublox_dgnss ublox_rover_hpposllh_navsatfix.launch.py device_family:=F9R
```

> [!WARNING]
> **`device_family:=F9R` is not optional.** The ZED-F9P and ZED-F9R share USB product ID
> `0x01a9`, and the driver's autodetection resolves that ID to **F9P**. Left to itself it
> logs `Device family: F9P` and loads `f9p_ubx_config.toml` — the wrong configuration for
> this hardware. Passing `device_family:=F9R` makes it load `f9r_ubx_config.toml`
> (106 parameters, sensor-fusion aware) instead. Check the log line to confirm:
>
> ```
> Device family: F9R - High-precision GNSS with sensor fusion
> Loading default UBX config for F9R: .../config/f9r_ubx_config.toml
> ```

Expect the driver to then report **`Proceeding with partial parameter initialization
(degraded mode)`**, with a list of `Missing response:` keys. This is not fatal and the
receiver works — the keys that go unconfirmed are mostly `CFG_MSGOUT_*` for messages this
launch does not need, plus UART2 settings for a port nothing is wired to. Two consequences
worth knowing:

- The requested 10 Hz rate does not take effect; output stays at the receiver's default
  **1 Hz**. Fine for `gnss_poser`, but do not expect 10 Hz until this is chased down.
- `CFG_USBINPROT_RTCM3X` is among the unconfirmed keys. RTCM3 input on USB is enabled by
  default in F9 firmware, so corrections should still get in — but if RTK never engages,
  verify this first with `/ubx_rxm_rtcm` before suspecting the caster.

### 3. Start the NTRIP client

```bash
source ~/.ichimill.env
ros2 launch ublox_dgnss ntrip_client.launch.py \
  use_https:=false \
  host:=ntrip.ales-corp.co.jp \
  port:=2101 \
  mountpoint:=RTCM32M7S
```

`use_https:=false` is required. The launch file defaults to `true` with port 443 for an
Australian caster; ichimill is plain NTRIP on 2101 and the connection will fail silently
against a TLS handshake.

### 4. Verify RTK is actually working

Fix quality is the thing to check, and it is easy to fool yourself here — a receiver with
no corrections still publishes a perfectly plausible NavSatFix, just with metre-level
error instead of centimetre.

The driver publishes at the **root namespace**, not under `/ublox_dgnss/`:

```bash
# what Autoware will consume — NavSatFix
ros2 topic echo /fix --once
ros2 topic hz   /fix

# carrier solution: gps_fix_ok, diff_soln, carr_soln (0 none, 1 float, 2 FIXED)
ros2 topic echo /ubx_nav_status --once

# corrections arriving AT THE RECEIVER, not merely at the client
ros2 topic echo /ubx_rxm_rtcm --once

# corrections leaving the NTRIP client
ros2 topic hz /ntrip_client/rtcm
```

`carr_soln == 2` (RTK fixed) is the goal. Expect `1` (float) first, converging to `2`
within a minute or two with a clear sky view. If it never leaves `0`, corrections are not
reaching the receiver — check `ubx_rxm_rtcm` before suspecting the antenna.

## Verified state

Brought up 2026-09-05 on the Jetson, receiver on hub port `1-4.1`.

| Step | Result |
|---|---|
| Enumeration | **Pass** — `Bus 001 Device 009: ID 1546:01a9 U-Blox AG u-blox GNSS receiver` |
| udev rule / libusb access | **Pass** — `/dev/bus/usb/001/009` is `crw-rw-rw-`, driver claims it, `cdc_acm` yields with `-16` |
| Driver identification | **Pass, with `device_family:=F9R`** — defaults to F9P otherwise |
| UBX configuration | **Partial** — degraded mode, 59 keys unconfirmed; output runs at 1 Hz rather than the requested 10 Hz |
| `sensor_msgs/NavSatFix` | **Pass** — `/fix` publishing at 1 Hz |
| NTRIP DNS + route | **Pass** — `ntrip.ales-corp.co.jp` → `52.199.90.201`, out via wifi `wlP1p1s0` |
| NTRIP authentication | **Pass** — TCP `ESTAB` to `52.199.90.201:2101`, 179 bytes sent, 14 received (`ICY 200 OK`) |
| RTCM stream | **Withheld** — see below |
| GNSS fix | **None** — `status: -1`, `gps_fix_ok: false`, lat/lon `0.0` |
| RTK fix | **Not tested** — blocked on the above |

### Why the correction stream stops at "connected"

The caster accepted the login and then sent nothing more: byte counters sat frozen at
`sent 179 / received 14` across repeated samples. Fourteen bytes is exactly
`ICY 200 OK\r\n\r\n` — a successful mount-point request, not a rejection. A bad password
closes the socket instead.

`RTCM32M7S` is `nmea-required=1`. It is a VRS mount point: the caster synthesises
corrections for *your* location, so it will not stream until the client uplinks a GGA
sentence saying where you are. `ntrip_client_node` derives that GGA from the receiver's
own position — and the receiver has no fix, so there is no GGA to send, so no corrections
come back.

**This is not a fault.** It is the documented behaviour of the mount point, and it
resolves itself the moment the antenna sees sky. The failure chain is worth remembering
in this order, because it is the reverse of where you would instinctively look:

```
no sky view  →  no GNSS fix  →  no GGA uplink  →  caster withholds RTCM  →  no RTK
```

If RTK is not working, check `/fix` **before** blaming the caster or the credentials.

### What is left to do

1. Put the antenna outside, or somewhere with real sky view. Confirm `/fix` reports
   `status: 0` and a plausible lat/lon.
2. Watch `/ntrip_client/rtcm` start flowing once the GGA uplink begins.
3. Confirm `/ubx_rxm_rtcm` shows corrections reaching the receiver.
4. Watch `carr_soln` go `0 → 1` (float) `→ 2` (fixed). Expect a minute or two.
5. Chase the degraded-mode config if 10 Hz output is wanted.

## Autoware integration

### What works with no code changes

`ublox_nav_sat_fix_hp_node` publishes `sensor_msgs/NavSatFix`, which is exactly what
`autoware_gnss_poser` consumes. Point the sensor kit at that topic and position flows
through to `/sensing/gnss/pose_with_covariance`.

### What does not, and why

**Orientation.** `gnss.launch.xml` sets `use_gnss_ins_orientation: true`, which makes
`gnss_poser` wait for `autoware_sensing_msgs/GnssInsOrientationStamped` on
`/autoware_orientation`. `ublox_dgnss` does not publish it — the message list in
`ublox_ubx_msgs` has no `UBXNavATT`, so the F9R's attitude solution is not exposed at all.
Set `use_gnss_ins_orientation: false` for this receiver.

**IMU.** The F9R's IMU is exposed only as `UBXEsfMeas` / `UBXEsfStatus` — raw u-blox ESF
sensor data, not `sensor_msgs/Imu`. Autoware's `imu_corrector` cannot read it. Three
options, cheapest first:

1. **Use the Ouster's IMU instead.** `imu.launch.xml` already has
   `/sensing/lidar/top/ouster/imu` present as a commented-out input. One line.
2. **Write an ESF→Imu converter.** A small node mapping `UBXEsfMeas` accelerometer and
   gyro items into `sensor_msgs/Imu`. Correct, but it is new code to own.
3. **Leave the IMU to the receiver.** The F9R fuses it internally for dead reckoning, so
   its benefit reaches Autoware through the position anyway. Autoware's EKF still wants
   an `Imu` input of its own, so this is not sufficient on its own.

Option 1 is the sensible starting point: it needs no new code, and the F9R's IMU keeps
doing its real job inside the receiver regardless.

### Launch changes — done

Applied to `pixkit_sensor_kit_launch`; `gnss_receiver` now defaults to `ublox_dgnss`.

| File | Change |
|---|---|
| `launch/gnss.launch.xml` | New `ublox_dgnss` branch launching the driver with `device_family:=F9R` and the NTRIP client against ichimill. The old `ublox` (`ublox_gps`) branch is kept but commented as non-working. |
| `launch/gnss.launch.xml` | `use_gnss_ins_orientation` is now `$(eval "'$(var gnss_receiver)'!='ublox_dgnss'")` — false for this receiver, true for the others, since the F9R exposes no attitude solution. |
| `launch/imu.launch.xml` | `input_topic` moved off `/sensing/gnss/chc/imu` (a receiver this platform does not have) onto `/sensing/lidar/top/ouster/imu`. |
| `package.xml` | `<exec_depend>ublox_dgnss</exec_depend>`. |

#### Two namespace traps found while wiring this

Both cost a debugging cycle and neither is obvious from the launch file.

**The NavSatFix topic must be relative.** `gnss.launch.xml` does
`<push-ros-namespace namespace="gnss"/>`, so the driver's `fix` becomes `/gnss/fix`.
Writing the absolute `/fix` into `navsatfix_topic_name` leaves `gnss_poser` subscribed to
a topic with **zero publishers** — and nothing errors. `ros2 topic info /fix` showing
`Publisher count: 0` is the only symptom. Use the relative `fix`, matching how the `chc`
branch already does it.

**The RTCM topic is absolute and does *not* get namespaced.** `/ntrip_client/rtcm` is
compiled into both `ntrip_client_node` and `ublox_dgnss_node`, so the two connect
regardless of namespace. Convenient here, but it means two u-blox receivers in one system
would cross-feed corrections. If a second is ever added, remap it explicitly.

Verify the whole chain with publisher/subscriber counts rather than by eye:

```bash
for t in /gnss/fix /gnss/pose_with_covariance /ntrip_client/rtcm /gnss/ubx_rxm_rtcm; do
  echo "$t"; ros2 topic info "$t" | grep count
done
```

Expected: `/gnss/fix` 1/1, `/gnss/pose_with_covariance` 1/0 (Autoware subscribes when the
rest of the stack runs), `/ntrip_client/rtcm` 1/1.

## Not applicable here

[GNSS_RTK.md](GNSS_RTK.md) documents RTK for the **CHC CGI-410** over Ethernet at
`192.168.1.110`, using the receiver's own built-in NTRIP client and a NAT service on the
host. That is the Pixkit platform, a different receiver entirely, and none of its network
setup applies to a USB device.
