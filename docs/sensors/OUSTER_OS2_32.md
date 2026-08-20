# Ouster OS-2-32 — 32 beam long range lidar

The second Ouster available for this vehicle. It uses the same driver, the same point type and the
same top mount as the [OS-1-128](OUSTER_OS1_128.md); what differs is the address, the beam count
and the field of view. Select it with `lidar_profile:=os2_32`.

## Hardware identity

| | |
| --- | --- |
| Model | `OS-2-32-U3` |
| Serial number | `992317000316` |
| Part number | `860-105020-07` |
| MAC address | `bc:0f:a7:00:7f:94` |
| Hostname | `os-992317000316` (mDNS `os-992317000316.local`) |
| IPv4 link-local | `169.254.60.43/16` |
| IPv6 link-local | `fe80::be0f:a7ff:fe00:7f94/64` |

## At a glance

| | |
| --- | --- |
| Model | Ouster OS-2, 32 beams |
| Address | `192.168.1.120/24` static — **the unit ships from our bench at `192.168.1.100`, see [Changing the sensor's address](#changing-the-sensors-address)** |
| Host address | `192.168.1.100/24` on the sensor LAN, static, **no gateway** |
| UDP ports | lidar `38672`, imu `48215` (shared with the OS-1 profile) |
| Point type | `xyzircaedt` — `autoware::point_types::PointXYZIRCAEDT` |
| Topic | `/sensing/lidar/top/ouster/points` |
| Frames | `os_sensor_top` → `os_lidar_top`, `os_imu_top` |
| Concat config | `config/lidar_profiles/os2_32.param.yaml` |

Only one Ouster runs at a time, so the OS-2-32 reuses the topic and frames of the top mount rather
than introducing its own. Nothing downstream has to change when the units are swapped.

## Running it

```bash
ros2 launch autoware_launch autoware.launch.xml \
    vehicle_model:=pixkit sensor_model:=velodyne_pixkit_sensor_kit \
    map_path:=$PWD/autoware_map \
    lidar_profile:=os2_32
```

Or through the script, which passes extra arguments through:

```bash
./autoware_velodyne_kashiwa.sh autoware_map lidar_profile:=os2_32
```

A different address for one run:

```bash
... lidar_profile:=os2_32 os2_32_ip:=192.168.1.105
```

## Changing the sensor's address

The sensor holds a **static IPv4 override**, which is why its console reports
`IPv4 (Static) 192.168.1.100/24` rather than a DHCP lease. That address has to become
`192.168.1.120`, because `192.168.1.100` is the host's address on the sensor LAN. Leaving both on
`.100` means two devices answering for one address the moment the cable is plugged in, and the
symptom is not an error but a lidar that behaves erratically or disappears.

**From the web console.** Open `http://<current address>/`, find the network configuration page,
and set the static IPv4 override to `192.168.1.120/24`. The sensor applies it and immediately stops
answering on the old address.

**From the HTTP API**, which the console uses underneath:

```bash
# set a static address
curl -X PUT http://192.168.1.100/api/v1/system/network/ipv4/override \
     -H 'Content-Type: application/json' --data '"192.168.1.120/24"'

# or hand it back to DHCP / link-local
curl -X DELETE http://192.168.1.100/api/v1/system/network/ipv4/override
```

**From a Windows workstation**, in PowerShell. The body is a JSON *string*, so the double quotes
have to survive into the request — wrap it in single quotes:

```powershell
# what it currently thinks its network is
Invoke-RestMethod -Uri "http://192.168.1.100/api/v1/system/network" | ConvertTo-Json -Depth 5

# set the static override
Invoke-RestMethod -Uri "http://192.168.1.100/api/v1/system/network/ipv4/override" `
    -Method Put -ContentType "application/json" -Body '"192.168.1.120/24"'

# confirm on the new address
Test-NetConnection 192.168.1.120 -Port 80
Invoke-RestMethod -Uri "http://192.168.1.120/api/v1/system/network" | ConvertTo-Json -Depth 5
```

Note that `curl` in PowerShell is an alias for `Invoke-WebRequest`, which does not take curl's
flags: a pasted `curl -X PUT ...` fails with a confusing parameter error. Use `curl.exe` if you
want the literal curl syntax, or the cmdlets above.

Verify on the new address, not the old one:

```bash
ping 192.168.1.120
curl -s http://192.168.1.120/api/v1/system/network | python3 -m json.tool
```

The endpoint above is the one used by firmware 2.4 and 3.x. If it returns 404, the firmware is
older than that and the console is the only route; check `/api/v1/sensor/metadata/sensor_info` for
the version.

## Why `os-992317000316.local` may not resolve while the IP works

The `.local` name is mDNS, which is a fundamentally different mechanism from the address and fails
independently of it. Three things break it, in rough order of likelihood:

1. **The interface has no IPv4 address.** avahi will not answer IPv4 mDNS on an interface that has
   none, so a host whose sensor NIC is unconfigured — or unplugged, which prevents
   NetworkManager from applying the profile at all — resolves nothing even though everything is
   otherwise correct. Check with `ip -4 addr show enp3s0`.
2. **The name resolves to the link-local address.** A sensor with a static override often still
   advertises `169.254.60.43` over mDNS. The name looks fine, and the connection then fails because
   the client has no route into `169.254.0.0/16` on that link. `avahi-resolve-host-name -4
   os-992317000316.local` shows which address is actually being handed back.
3. **The client is not on the same link.** mDNS is link-local multicast with TTL 1 and does not
   cross a router, so a client reaching the sensor through any routed path can ping the address
   forever and never resolve the name.

This host is otherwise set up for it: `avahi-daemon` is active and `/etc/nsswitch.conf` has
`mdns4_minimal [NOTFOUND=return]` on the `hosts:` line. Nothing in this workspace depends on the
`.local` name — every launch file and config uses the address.

## What has to be checked when swapping units

1. **The extrinsic.** `base_link2os_lidar_top` in
   [`sensors_calibration.yaml`](../../src/launcher/autoware_launch/sensor_kit/velodyne_pixkit_sensor_kit_launch/velodyne_pixkit_sensor_kit_description/config/sensors_calibration.yaml)
   describes one physical mount. The OS-2 is a different size from the OS-1, so unless it sits in
   exactly the same place with the same orientation, that entry has to be re-measured before this
   profile localizes correctly. Wrong extrinsics do not raise an error, they produce scan matching
   that drifts or never converges.
2. **The address.** `.120` keeps the lidars together in `.12x` and leaves `.100` to the host,
   which is where the rest of the setup expects it. Set it through the sensor's web UI, or pass
   `os2_32_ip:=<address>` for a one-off run.
3. **`host_ip`.** The sensor sends its UDP stream to whatever `host_ip` names. On a machine whose
   sensor LAN address is not `192.168.1.100`, pass `host_ip:=<that address>` or the driver will
   connect, configure the sensor and receive nothing.

## Differences from the OS-1-128 that matter downstream

| | OS-1-128 | OS-2-32 |
| --- | --- | --- |
| Beams (`channel` values) | 128 | 32 |
| Vertical field of view | wide | narrow, longer range |
| Points per scan at `1024x10` | 131,072 | 32,768 |

The narrower vertical field of view is the part worth thinking about: ground segmentation and
scan matching both rely on seeing enough of the ground plane near the vehicle. The ground
segmentation parameters in
[`ground_segmentation.param.yaml`](../../src/launcher/autoware_launch/autoware_launch/config/perception/obstacle_segmentation/ground_segmentation/ground_segmentation.param.yaml)
were tuned for a 128 beam sensor, and a four times sparser cloud may need
`grid_size_m` and `gnd_grid_buffer_size` revisited.

## Verifying

```bash
ping 192.168.1.120
ros2 topic hz /sensing/lidar/top/ouster/points                    # ~10 Hz
ros2 topic echo --field fields /sensing/lidar/top/ouster/points --once   # 10 fields
ros2 topic echo --field height /sensing/lidar/top/ouster/points --once   # 1 (unorganized)
ros2 run tf2_ros tf2_echo base_link os_lidar_top
```
