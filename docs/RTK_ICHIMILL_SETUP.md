# RTK (SoftBank ichimill) on Pixkit — receiver built-in NTRIP client

Two ways to feed RTCM corrections to the CHC CGI-410. **Path B is set up on this
machine** and is preferred for road driving.

| | Path A — `str2str` relay (lab doc) | Path B — receiver's built-in NTRIP client |
| --- | --- | --- |
| Who talks to the caster | laptop | receiver |
| GGA sent to caster | **fixed** (`-p 35.90 139.93 50`) | receiver's **live** position |
| Valid range | few km of the fixed point | anywhere |
| Laptop process required while driving | yes | **no** |
| Needs NAT on laptop | no | yes (already configured) |

## Host state (already done)

- `enp3s0` static **192.168.1.100/24**, no gateway, `never-default` (wifi/USB stays default route)
- NAT for the sensor subnet: `pixkit-sensor-nat.service` (enabled, active) — masquerades
  `192.168.1.0/24` out whichever interface has the default route, plus `DOCKER-USER`
  accept rules (Docker sets `FORWARD` policy to DROP, so these are required)
- `str2str` built and installed at `/usr/local/bin/str2str` (for Path A fallback)

## Path B — configure the receiver

Open **http://192.168.1.110** in **Google Chrome** (Firefox cannot save parameters on this
firmware). Log in `admin` / `password`.

### 1. Give the receiver an internet route

In the receiver's network / Ethernet settings:

| Field | Value |
| --- | --- |
| IP address | `192.168.1.110` (unchanged) |
| Netmask | `255.255.255.0` |
| **Gateway** | **`192.168.1.100`** ← this laptop |
| **DNS** | **`8.8.8.8`** (or `1.1.1.1`) |

### 2. Configure the NTRIP client

**IO Configuration → RTK Client → Connect**

| Field | Value |
| --- | --- |
| Protocol | **NTRIP** (not TCP — TCP is for Path A) |
| Server / host | `ntrip.ales-corp.co.jp` |
| Port | `2101` |
| Mount point | `RTCM32M7S` |
| User / ID | `67vsdpoz`  (ichimill account **#4**) |
| Password | see `Ntrip_notice_0714164534.xlsx`, row 4 |

Save. Accounts #1–#3 are in use on other vehicles; #4 is reserved for Pixkit.

If DNS gives trouble, use the caster's IP **`52.199.90.201`** instead of the hostname
(verified 2026-08-18; an AWS address, so it may change — prefer the hostname).

Fallback mount point `RTCM32M5S` (MSM5) if the firmware rejects MSM7.

## Verify

From the laptop, confirm the receiver actually used the NAT path — counters were zero
before setup, so any non-zero value proves it:

```bash
sudo iptables -t nat -L POSTROUTING -v -n | grep 192.168.1.0/24   # pkts > 0
sudo conntrack -L 2>/dev/null | grep 2101                          # ESTABLISHED to caster
```

Then check the fix quality. The 6th GGA field is definitive: `1` = single,
`5` = RTK float, **`4` = RTK fixed**.

```bash
nc 192.168.1.110 9904 | awk -F, '/GGA/{print "quality="$7"  nSat="$8"  HDOP="$9}'
```

Autoware side (after `colcon build`, with the stack running):

```bash
ros2 topic echo /sensing/gnss/fix    # position_covariance ~0.02 when RTK fixed
ros2 topic hz   /sensing/gnss/fix    # ~10 Hz
```

Note `status.status == 2` (GBAS_FIX) covers **both** RTK float and fixed — use the GGA
quality field to distinguish them.

Requires open sky; RTK will not lock indoors. The receiver also needs its ~30 min
outdoor INS calibration before fused GPCHC attitude is trustworthy.

## Verified device API (CGI-410, HC_PRODUCT_MODEL__P5, board UB482)

Read directly from the receiver on 2026-08-18. The web UI is an EasyUI SPA over
`*.cmd` HTTP endpoints; `urlStringId` is only a cache-buster (no real API auth).

### Current (mis)configuration found

| Endpoint | Value | Note |
| --- | --- | --- |
| `eth_ip_get` | gateway `192.168.1.1`, dns `192.168.1.1` | **wrong** — no such router on this subnet |
| `netlink_server_type_get` | `NETLINK_SERVER_TYPE__TCP` | needs `CORS_CASTER` for NTRIP |
| `netlink_ip_addr_get` | `201.255.122.215:9902` | stale/dummy |
| `netlink_account_get` | name `""`, pwd `""` | empty |
| `netlink_data_source_get` | `""` | no mount point |
| `netlink_status_get` | `LINK_CONNECTING`, `err_num 113` | 113 = EHOSTUNREACH |
| `netlink_auto_open_get` | `true` | good — reconnects on boot |

`err_num 113` is the smoking gun: it cannot route off-subnet.

### Server-type enum

`NETLINK_SERVER_TYPE__` + `TCP` | `UDP` | **`CORS_CASTER`** (= NTRIP client) |
`NTRIP_SERVER` | `NTRIP2_SERVER` | `APIS_ROVER` | `APIS_BASE` | `ONE_STEP_FIX`

### Apply via HTTP (all GET; `link_idx=IO_ID__NETLINK_ROVER` is the RTK client)

```bash
R=192.168.1.110
L=IO_ID__NETLINK_ROVER
U="urlStringId=admin$(date +%s)000"

# 1. gateway + DNS (IP/mask unchanged, so the receiver does not move)
curl -sG "http://$R/eth_ip_set.cmd" --data-urlencode "$U" \
  -d ip=192.168.1.110 -d gateway=192.168.1.100 -d mask=255.255.255.0 \
  -d dns=8.8.8.8 -d udhcpc=0

# 2. NTRIP (CORS caster) mode
curl -sG "http://$R/netlink_server_type_set.cmd" --data-urlencode "$U" \
  -d link_idx=$L -d server_type=NETLINK_SERVER_TYPE__CORS_CASTER \
  -d udp_type=NETLINK_UDP_TYPE_NONE

# 3. caster address (IP avoids any DNS dependency)
curl -sG "http://$R/netlink_ip_addr_set.cmd" --data-urlencode "$U" \
  -d link_idx=$L -d ip=52.199.90.201 -d port=2101

# 4. ichimill account #4
curl -sG "http://$R/netlink_account_set.cmd" --data-urlencode "$U" \
  -d link_idx=$L -d name=67vsdpoz --data-urlencode "pwd=<pass4>"

# 5. PROOF the NAT path works - asks the caster for its source table
curl -sG "http://$R/netlink_data_source_list_get.cmd" --data-urlencode "$U" -d link_idx=$L
#    a mount-point list back => receiver reached the internet through this laptop

# 6. mount point
curl -sG "http://$R/netlink_data_source_set.cmd" --data-urlencode "$U" \
  -d link_idx=$L -d data_source=RTCM32M7S

# 7. auto-reconnect + connect now
curl -sG "http://$R/netlink_auto_open_set.cmd" --data-urlencode "$U" -d link_idx=$L -d auto_open=true
curl -sG "http://$R/netlink_open_set.cmd"      --data-urlencode "$U" -d link_idx=$L

# 8. status: expect NETLINK_STATUS__LINK_CONNECTED
curl -sG "http://$R/netlink_status_get.cmd" --data-urlencode "$U" -d link_idx=$L
```

Step 5 is the one that matters most: it is a round trip from the receiver to the
caster, so a mount-point list proves both the gateway and the laptop NAT are working.

### Equivalent clicks in Chrome

- **Network Settings** page (`WebForm/NetworkSet/NetworkSet.html`) - static IP, set
  Gateway `192.168.1.100`, DNS `8.8.8.8`, leave IP/mask alone.
- **IO Settings** page (`WebForm/IOSet/IOSet.html`) - the `NetClientRover` row, edit it
  (opens `EditWindows/CorsSet.html`): mode CORS/NTRIP caster, server + port, account,
  then refresh the mount-point list and pick `RTCM32M7S`, save, connect.

### Rollback

Original values are backed up as JSON in
`../pixkit_setup_backups/cgi410_config/*.json`. To revert the network change:

```bash
curl -sG "http://192.168.1.110/eth_ip_set.cmd" --data-urlencode "urlStringId=admin$(date +%s)000" \
  -d ip=192.168.1.110 -d gateway=192.168.1.1 -d mask=255.255.255.0 -d dns=192.168.1.1 -d udhcpc=0
```

## Path A — `str2str` fallback

Use if Path B misbehaves. Two corrections vs. the lab guide:

- **`-n 5000` is required.** Every ichimill mount point advertises `nmea-required=1`, and
  `str2str`'s NMEA request cycle defaults to `0` (never send). Without `-n` the caster
  drops the connection with a bare `timeout`.
- Build path on RTKLIB's default branch is `RTKLIB/app/str2str/gcc`, not
  `RTKLIB/app/consapp/str2str/gcc`.

```bash
str2str -in "ntrip://67vsdpoz:<pass>@ntrip.ales-corp.co.jp:2101/RTCM32M7S" \
        -p 35.90 139.93 50 -n 5000 -out "tcpsvr://:2102"
```

Expect a steady ~15 kbps. Then in the receiver: **IO Configuration → RTK Client →
Connect**, Protocol **TCP**, Server **192.168.1.100**, Port **2102**.

## Notes

- Field labels vary by firmware; see the CGI-410 manual if a name does not match.
- The Ouster lidar (`192.168.1.126`) is unaffected by any of this — its traffic is
  same-subnet and never routed.
- Avoid host addresses `.102`, `.110`, `.125`, `.126`, `.200` on the vehicle LAN.
