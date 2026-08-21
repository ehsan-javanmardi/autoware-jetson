# CHC CGI-410 — GNSS / INS

Supplies both the GNSS fix Autoware initializes localization from and the IMU that
`autoware_imu_corrector` consumes. It is the `chc` option of the sensor kit's GNSS launch, which is
the default.

## At a glance

| | |
| --- | --- |
| Address | `192.168.1.110`, web UI `:80` (`admin` / `password`) |
| NMEA | TCP `192.168.1.110:9904` |
| Driver | `nmea_navsat_driver` (TCP client variant) |
| Fix topic | `fix` → `/sensing/gnss/...` |
| IMU topic | `/sensing/gnss/chc/imu` → corrected to `imu_data` |
| Frame | `gnss_link` |
| Coordinates | MGRS (`coordinate_system: 1`) |

## Where it is configured

| What | File |
| ---- | ---- |
| Receiver selection | [`gnss.launch.xml`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_launch/launch/gnss.launch.xml) — `gnss_receiver` is `ublox`, `septentrio`, `chc` or `fixposition` |
| TCP endpoint | [`nmea_tcpclient_driver.yaml`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_launch/config/nmea_tcpclient_driver.yaml) |
| IMU source | [`imu.launch.xml`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_launch/launch/imu.launch.xml) |
| Antennas | **two**: rear = GNSS1 position, front = GNSS2 heading, see [VEHICLE.md](../VEHICLE.md#the-two-gnss-antennas) |
| Mounting position | `base_link2gnss` in [`sensors_calibration.yaml`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_description/config/sensors_calibration.yaml) — `x: -0.9, z: 0.3` |

`imu.launch.xml` selects `/sensing/gnss/chc/imu`; two alternatives are commented out in that file,
the Ouster's built-in IMU (`/sensing/lidar/top/ouster/imu`) and the Fixposition
(`/fixposition/corrimu`). Switching IMU source is a one-line change there.

## Changing the address

Edit `nmea_tcpclient_driver.yaml`. That file is the only place the receiver's address appears, and
it is a plain node parameter file, so the change takes effect on the next launch.

## RTK corrections

Corrections come from SoftBank ichimill over NTRIP, at
`ntrip.ales-corp.co.jp:2101`, mount point `RTCM32M7S`. The password is not in this repository; see
`Ntrip_notice_*.xlsx`, account #4.

The receiver has no route to the internet of its own. The sensor LAN deliberately has no gateway,
so **the host is the only way out**, and there are two ways to arrange that. Pick one; they are
alternatives, not steps.

### Option A — the receiver runs the NTRIP client

The receiver dials the caster itself, and the host forwards for it.

**On the receiver:**

| field | value |
| ----- | ----- |
| IP | `192.168.1.110` |
| Netmask | `255.255.255.0` |
| Gateway | `192.168.1.100` ← the host's sensor LAN address |
| DNS | `8.8.8.8` |
| NTRIP server | `ntrip.ales-corp.co.jp` port `2101` |
| Mount point | `RTCM32M7S` |

**On the host**, already in place and needing nothing:

- `net.ipv4.ip_forward = 1`
- `pixkit-sensor-nat.service`, which masquerades `192.168.1.0/24` out of whichever interface holds
  the default route. It is written as `! -o enp3s0`, so it follows the default route wherever it
  goes: cellular today, wifi tomorrow, with no edit.

Traffic path: receiver → host `192.168.1.100` → NAT → whatever provides internet → caster.

Three things go wrong quietly with this option:

- **The gateway is a real dependency.** `192.168.1.102` is the address the host used to have. A
  receiver still pointing there gets a normal single-point fix and never a correction, with no
  error anywhere.
- **DNS must be a public resolver.** Do not use `192.168.1.100`: the host's `systemd-resolved`
  listens on `127.0.0.53` only and does not answer queries from the network. Alternatively skip DNS
  entirely by entering the caster as `52.199.90.201`, which is what the hostname resolved to on
  2026-08-21, at the cost of breaking if that address ever changes.
- **The default route can move under you.** If the internet connection drops, the host may fall
  back to another route that has no internet, and corrections stop silently.

### Option B — `str2str` on the host relays to the receiver

The host pulls the correction stream and re-serves it on the local network. The receiver never
leaves its own subnet, so it needs **no gateway, no DNS and no NAT**.

**On the host** (`str2str` is installed at `/usr/local/bin/str2str`):

```bash
str2str -in "ntrip://<user>:<password>@ntrip.ales-corp.co.jp:2101/RTCM32M7S" \
        -out tcpsvr://:2102
```

**On the receiver:**

| field | value |
| ----- | ----- |
| IP | `192.168.1.110`, netmask `255.255.255.0` |
| Gateway | not needed |
| DNS | not needed |
| Protocol | **TCP client** |
| Server | `192.168.1.100` port `2102` |

This is the more robust of the two while the network is still being sorted out. Every uncertain
part — the receiver's routing, its DNS, the NAT path, the stability of the uplink — moves to the
host, where the correction stream is visible and reconnects are yours to see. The cost is a process
someone has to start, and a password on a command line.

### Using a cellular uplink

Both options work over a USB-tethered modem; nothing needs configuring for it. The host picks the
interface with the lowest metric default route, and the NAT rule follows it.

Verified working on 2026-08-21 with a Kyocera tethered on `enx5666e608234b` (`192.168.42.24/24`,
gateway `192.168.42.129`, metric 100):

```bash
ping 8.8.8.8                                   # 52 ms, cellular latency
resolvectl query ntrip.ales-corp.co.jp         # 52.199.90.201
bash -c 'exec 3<>/dev/tcp/52.199.90.201/2101'  # port open
```

Note that the caster does **not** answer ICMP: pinging `52.199.90.201` fails even when the service
is perfectly reachable. Test the TCP port, not the ping.

> [!WARNING]
> While configuring the receiver over its own WiFi, the host is joined to `192.168.200.0/24` and
> takes DNS servers from the receiver, which has no internet behind it. Name resolution then fails
> on the host for as long as you stay joined, which looks exactly like a broken uplink. Leave that
> network when finished.

## Reaching the receiver's own configuration UI

The wired address is for **data**. Configuration lives behind the receiver's own **WiFi access
point**, and that route works even when its ethernet side is dead, which makes it the fastest way
to tell "unpowered" from "unplugged" from "wrong address":

1. Join the WiFi network `GNSS-<serial>`, password `12345678`.
2. Open `http://192.168.200.1`, log in with `admin` / `password`.
3. **Do not use Firefox.** The vendor documentation states parameters cannot be modified
   successfully from it, and the failure is silent.

From there: the wired IP the receiver currently holds, the NTRIP client settings, and the fix
quality. Vendor documentation:
<https://pixmoving-moveit.github.io/pixkit-documentation-en/install-sensors/GNSS-installation/>,
which also states that `192.168.1.110` is the factory default and should not be modified, and that
the data output defaults to GPCHC and GPGGA at 50 Hz.

## When there is no GNSS data

The failure is almost never RTK. Work down this list; each step distinguishes a different cause,
and the earlier ones are the common ones.

**1. Is the link up at all?**

```bash
ip -br link show enp3s0        # NO-CARRIER means nothing is plugged in or the switch is off
```

`NO-CARRIER` also prevents NetworkManager from applying the profile, so the interface ends up
with no IPv4 address, which in turn stops avahi answering mDNS. One unplugged cable produces
three unrelated-looking symptoms.

**2. Is the receiver on the network?**

```bash
ping 192.168.1.110
nc 192.168.1.110 9904          # the check the vendor documentation gives; NMEA should scroll
```

**3. Is it on the network under a different address?** Sweep the subnet:

```bash
for i in $(seq 1 254); do (ping -c1 -W1 192.168.1.$i >/dev/null 2>&1 && echo "UP: .$i") & done; wait
```

**4. Is it on a *different subnet*?** This is the case a ping sweep cannot find, because a host
only pings within its own subnet. Look at layer 2 instead, where addressing does not matter:

```bash
ip neigh show dev enp3s0 | grep -v INCOMPLETE     # any MAC here is physically on the wire
sudo arp-scan -I enp3s0 --localnet                # if arp-scan is installed
sudo tcpdump -i enp3s0 -nn -c 20                  # needs root; shows who is talking
```

An entry that resolves to a MAC proves a device is present regardless of what subnet it thinks it
is in. To then talk to it, the host needs an address in that subnet.

**5. Does the host need to be on two subnets at once?** Adding a second address is better than
moving the existing one, because moving it takes the lidar off the network:

```bash
sudo nmcli con mod "Wired connection 1" +ipv4.addresses 192.168.200.6/24
sudo nmcli con up "Wired connection 1"
```

### What it looks like from Autoware

| symptom | meaning |
| ------- | ------- |
| `nmea_tcpclient_driver-NN process has died, exit code 255`, preceded by `Installing the transforms3d library by hand required` | a **missing Python dependency**, not a network problem. The driver exits before it ever opens a socket, so it looks identical to an unreachable receiver. `nmea_navsat_driver` imports `transforms3d` but only declared `tf_transformations`; the manifest here now declares `python3-transforms3d` so `rosdep install` covers it |
| `nmea_tcpclient_driver-NN process has died, exit code 255` with no such message | the driver could not open the TCP connection; the receiver is unreachable |
| `/api/localization/initialize: status code 3 'The GNSS pose has not arrived.'` | the **automatic** pose initializer has no GNSS fix. A manual 2D Pose Estimate in RViz still works, it does not need GNSS |
| `status code 1 'The vehicle is not stopped.'` | unrelated to GNSS, see [OUSTER_OS2_32.md](OUSTER_OS2_32.md#running-the-whole-stack-on-a-bench) |

> [!WARNING]
> Changing the host's address to reach the receiver takes every other sensor off the network. The
> lidar lives in `192.168.1.0/24`, so moving `enp3s0` to another subnet makes a running Autoware
> lose its point cloud with no error other than the topic going quiet. Add a second address rather
> than replacing the first.

### Observed 2026-08-21

With the cable in and the link up, a sweep of the whole of `192.168.1.0/24` found only the host and
the lidar; nothing answered at `.110`. Layer 2 showed a third device on the same switch at
`192.168.200.1`, whose MAC `22:a2:a9:ce:9e:a8` has the locally administered bit set, so it is not a
hardware vendor address and may be an access point rather than the receiver itself. Unresolved at
the time of writing: whether that device is the CGI-410 holding a changed address, or something
else on the switch entirely. The WiFi route above is the way to settle it.

## Verifying

```bash
ping 192.168.1.110
nc -vz 192.168.1.110 9904          # NMEA stream is reachable
ros2 topic echo /sensing/gnss/fix --once
ros2 topic hz /sensing/gnss/chc/imu
```

A fix with `status: 0` is a standalone solution; RTK fixed is `status: 2`. Autoware's GNSS pose
initialization is only as good as the fix quality, so a vehicle that will not initialize is worth
checking here first.
