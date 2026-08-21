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
| Mounting position | `base_link2gnss` in [`sensors_calibration.yaml`](../../src/launcher/autoware_launch/sensor_kit/pixkit_sensor_kit_launch/pixkit_sensor_kit_description/config/sensors_calibration.yaml) — `x: -0.9, z: 0.3` |

`imu.launch.xml` selects `/sensing/gnss/chc/imu`; two alternatives are commented out in that file,
the Ouster's built-in IMU (`/sensing/lidar/top/ouster/imu`) and the Fixposition
(`/fixposition/corrimu`). Switching IMU source is a one-line change there.

## Changing the address

Edit `nmea_tcpclient_driver.yaml`. That file is the only place the receiver's address appears, and
it is a plain node parameter file, so the change takes effect on the next launch.

## RTK

Corrections come from SoftBank ichimill over NTRIP. The receiver runs the NTRIP client itself
rather than the host relaying with `str2str`. Full setup, including the caster address, the mount
point and the routing that lets a receiver on a gateway-less LAN reach the internet, is in
[`RTK_ICHIMILL_SETUP.md`](../RTK_ICHIMILL_SETUP.md).

The routing part is easy to miss: the sensor LAN has no gateway, so `pixkit-sensor-nat.service`
masquerades `192.168.1.0/24` out of whichever interface holds the default route. Without it the
receiver cannot reach the caster and silently stays in single-point fix.

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
| `nmea_tcpclient_driver-NN process has died, exit code 255` | the driver could not open the TCP connection; the receiver is unreachable, not misconfigured |
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
