# Connecting to the Segway

Every way to reach the chassis, from the serial cable up to driving it from a phone on
cellular. For wiring, the connector pinout and the troubleshooting history, see
[SEGWAY.md](SEGWAY.md).

## Quick reference

| You want to… | Do this |
|---|---|
| Reach the Jetson from anywhere | Tailscale — `100.86.16.37` |
| Reach it on the lab WiFi | `192.168.10.15` (SSID `Buffalo-G-7088`) |
| Reach it over the direct LAN cable | `192.168.1.101` |
| Open the dashboard | `http://<any address above>:8080/` |
| Start the dashboard, read-only | [Running the server](#running-the-server) |
| Start it so you can drive | Same, plus `--allow-control` |
| Stop it | `sudo pkill -f '[s]erver\.py --lib'` |

## The chain

```
Segway RMP 401
   │  8-pin connector, pins 3/4/5 (TX/RX/GND)
   ▼
CP2102 USB-serial converter
   │  USB
   ▼
Jetson AGX Orin  /dev/ttyUSB0 @ 921600
   │
   ├─ dashboard server (python) :8080
   │
   └─ reachable over LAN cable / WiFi / Tailscale
```

---

## 1. Reaching the Jetson

Four routes, in rough order of usefulness.

### Tailscale — works from anywhere

Best option: works on cellular, in a café, behind any NAT. No port forwarding.

| | |
|---|---|
| Machine name | `jetson-tlab` |
| Tailscale IP | `100.86.16.37` |
| MagicDNS name | `jetson-tlab.tail43b8f4.ts.net` |
| Account | `ehsan.jmardi@gmail.com` |

```bash
ssh tlab@100.86.16.37
# dashboard: http://100.86.16.37:8080/
```

### Lab WiFi

```
SSID:  Buffalo-G-7088
IP:    192.168.10.15   (interface wlP1p1s0)
```

Your phone must be on the same SSID. This is the default route to the internet.

### Direct LAN cable

```
Jetson: 192.168.1.101   (interface eno1)
Host:   192.168.1.100
```

A private point-to-point link with no gateway, so it does not affect internet access.
Only reachable from the machine at the other end of the cable — **not** from a phone.

> The kernel has logged `Downshift ... to 10Mbps, check cabling!` and repeated
> `Link is Down` on this interface. If it behaves oddly, suspect the cable.

### On the Jetson itself

```
http://localhost:8080/
```

---

## 2. Tailscale

Installed and **already configured to start on boot** — nothing more to do.

```bash
systemctl is-enabled tailscaled     # enabled
systemctl is-active  tailscaled     # active
```

The node key lives in `/var/lib/tailscale/tailscaled.state`, so the Jetson rejoins the
tailnet automatically after a reboot with no login. Verified by restarting the service:
it came back `Running` and online without re-authenticating.

### Everyday commands

```bash
sudo tailscale status          # all machines on the tailnet
sudo tailscale ip -4           # this machine's tailnet IP
sudo tailscale up              # connect (prints a login URL if logged out)
sudo tailscale down            # disconnect, stay logged in
sudo tailscale logout          # forget the node key; needs re-auth next time
sudo systemctl restart tailscaled
```

### Adding a phone or tablet

1. Install Tailscale from the App Store / Play Store.
2. Sign in as `ehsan.jmardi@gmail.com`.
3. Open `http://100.86.16.37:8080/`.

### Renaming the machine

```bash
sudo tailscale set --hostname=new-name      # no re-auth needed
```

This changes only the Tailscale name. The Jetson's **system** hostname is still
`ubuntu`, deliberately left alone — renaming it touches `/etc/hosts` and can disturb ROS
node discovery.

### Known issue: connmark

Tailscale reports a health warning on this kernel:

```
enabling connmark rules: ... iptables v1.8.7 (legacy):
Couldn't load match `connmark': No such file or directory
```

The L4T kernel ships a trimmed netfilter set and is missing `xt_connmark`. **Normal
connectivity is unaffected** — the node is online and the dashboard is reachable. It
would matter only if you want the Jetson to act as a subnet router or exit node.

---

## 3. Running the server

Files live in [`tools/segway_dashboard/`](../tools/segway_dashboard/).
The SDK it links against is at:

```
/home/tlab/workspace/segway_ros2/segwayrmp/lib/libctrl_arm64-v8a.so
```

### Start — read-only

Safe default. Motion functions are never bound, so it cannot command the chassis.

```bash
cd /home/tlab/workspace/autoware-jetson/tools/segway_dashboard
sudo ./server.py --lib /home/tlab/workspace/segway_ros2/segwayrmp/lib/libctrl_arm64-v8a.so
```

### Start — drivable

```bash
sudo ./server.py --lib /home/tlab/workspace/segway_ros2/segwayrmp/lib/libctrl_arm64-v8a.so \
    --allow-control --max-linear 0.2 --max-angular 0.4
```

Start low. Raise the caps once you have confirmed the direction conventions.

### Start detached (survives closing the terminal)

```bash
sudo setsid nohup ./server.py --lib <path> --allow-control \
    >/dev/null 2>&1 < /dev/null &
```

Discarding stdout matters — the SDK prints `host firmware version is older!` on a loop
and will otherwise grow a large log file.

### Stop

```bash
sudo pkill -f '[s]erver\.py --lib'
```

> The `[s]` is not a typo. A plain `pkill -f 'server.py --lib'` matches **its own**
> command line and kills the shell running it. The bracket stops the pattern matching
> itself.

### Is it running?

```bash
ss -tlnp | grep 8080                    # is the port bound?
pgrep -af '[s]erver\.py --lib'          # the process
curl -s localhost:8080/api/status | python3 -m json.tool
```

### Options

| Flag | Default | Meaning |
|---|---|---|
| `--lib` | *required* | Path to `libctrl_arm64-v8a.so` |
| `--serial` | `ttyUSB0` | Device name under `/dev` |
| `--port` | `8080` | HTTP port |
| `--host` | `0.0.0.0` | Bind address |
| `--allow-control` | *off* | Expose motion endpoints and the Control tab |
| `--max-linear` | `0.5` | Linear cap, m/s |
| `--max-angular` | `0.8` | Angular cap, rad/s |

### Why root

The SDK shells out to `sudo chmod` and `sudo stty` on the serial device during
`init_control_ctrl()`. Being in `dialout` is worth having but is not sufficient.

---

## 4. Driving from a phone

1. Reach the dashboard by any route above.
2. Tap the **Control** tab.
3. **Release the hardware E-stop.** While engaged, the chassis reports mode 3 and shields
   both speed and enable commands; Enable stays greyed out.
4. Press **Enable**, then hold the joystick. Up is forward.

On iOS, *Share → Add to Home Screen* gives a full-screen app without Safari's chrome and
avoids accidental pull-to-refresh while driving.

Releasing the knob, switching tabs, backgrounding the app or losing the network all stop
the chassis. See the [dashboard README](../tools/segway_dashboard/README.md) for the four
safety layers.

---

## 5. Without the web UI

The vendor test tool, useful for confirming the link independently:

```bash
cd /home/tlab/workspace/segway_ros2/segwayrmp/lib
sudo script -qec "printf '/ttyUSB0\n' | ./ctrl_arm64-v8a s -test central" /dev/null
```

`get_chassis_central_version` reading anything but `0xFFFF` means the chassis is
replying. The `script` wrapper is needed because the tool requires a TTY.

The JSON API also works from the command line:

```bash
curl -s localhost:8080/api/status | jq .battery
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| `/dev/ttyUSB0` missing | `lsusb` for the CP2102 (`10c4:ea60`); `sudo dmesg \| grep -i ftdi\|cp210` |
| Dashboard shows "chassis not replying" | Versions read `0xFFFF` — check the 8-pin wiring, TX/RX crossed, white wire for GND |
| Enable button greyed out | Hardware E-stop engaged (mode 3), or chassis in error mode |
| Robot stutters while driving | WiFi dropouts tripping the 400 ms deadman — check signal, or use Tailscale |
| Port 8080 refuses connection | Server not running — see [Is it running?](#is-it-running) |
| `pkill` killed your shell | Use the `[s]erver\.py` bracket form |
| Can't reach `192.168.1.101` from phone | That is the LAN cable, not WiFi. Use `192.168.10.15` or Tailscale |

## Safety

- The red **STOP** button in the UI is a software stop. **Only the hardware E-stop cuts
  motor power.**
- With Tailscale up and `--allow-control`, the chassis is drivable from anywhere you are
  signed in — including out of sight of the robot. Consider binding the server to the
  Tailscale interface (`--host 100.86.16.37`) so it is not exposed to everyone on the
  local WiFi, and starting it with `--allow-control` only when you intend to drive.
- First drive of any session: wheels off the ground, or clear space with the hardware
  E-stop in reach.
