# Pixkit Autoware — setup state & handover

Last updated: 2026-08-18. Read this first when resuming.

## Where things are

| Path | What |
| --- | --- |
| `/home/ehsan/workspace/pix_autoware/pixkit_autoware` | the workspace (was `autoware`, renamed) |
| `/home/ehsan/workspace/pix_autoware/Pixkit_Autoware_` | upstream Pixkit extensions, kept as backup |
| `/home/ehsan/workspace/pix_autoware/pixkit_setup_backups/` | all rollback artifacts (see below) |
| `~/autoware_data/ml_models` | ONNX models downloaded by the playbook |
| `/opt/acados` | acados, built from source by the playbook |

## Versions

Autoware **1.9.0** (tag, detached HEAD `1071878`) · autoware_core 1.9.0 ·
autoware_universe 0.52.0 · autoware_launch 0.52.0 · Ubuntu 22.04 · ROS 2 Humble ·
CycloneDDS · CUDA 12.8 (`nvcc` 12.8.93) · TensorRT 10.1.0.27 · cuDNN 8.4.1.50.
Pixkit extensions from `tlab-wide/Pixkit_Autoware` @ `b01c6b2`, authored for
Autoware 0.45.1 (see `README.md` for the merge delta).

## DONE — install is COMPLETE (2026-08-18)

**`colcon build`: 492/492 packages, 0 failures, 1h 22min.** `nvidia-smi` works
(610.57.04). The workspace sources cleanly and ROS resolves all 6 Pixkit packages.
Remaining work is RTK receiver config + kernel cleanup + supplying a map.

## DONE

- **Dev env playbook: clean.** `ansible-playbook autoware.dev_env.install_dev_env`
  → `ok=239 changed=39 failed=0`. Run with `-e cuda_install_drivers=false`
  (driver handled separately, below).
- **Pixkit merged**: 497 package.xml in `src/`, 492 buildable, no duplicate names.
- **Network configured** for both sensors (see next section).
- `str2str` (RTKLIB) built → `/usr/local/bin/str2str`.
- **NVIDIA driver `nvidia-open` 610.57.04** installed, DKMS-built for 6.8.0-136.
  `nvidia-smi` verified working after reboot.
- **`rosdep install`**: 204 packages, "All required rosdeps installed successfully".
- **`colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release`**:
  492/492 finished, 0 failed, 1h 22min 29s. `install/` 259 MB, `build/` 4.5 GB.

### Fixes applied to get there (do not undo)

1. Removed stale `/etc/apt/sources.list.d/ros2.list` — it conflicted with
   `ros2.sources` on `Signed-By`, which made apt refuse to read **any** source list
   (`E: The list of sources could not be read.`). This was the original install failure.
2. Disabled `google-chrome.list` and `anydesk-stable.list` — their GPG keys have
   rotated (`NO_PUBKEY`). `apt-get update` only warns, but Ansible's apt module raises
   on any fetch failure (`Failed to update apt cache: unknown reason`).
   **To restore them**, import the current keys, then move the files back from
   `pixkit_setup_backups/`.
3. `COLCON_IGNORE` added to `src/sensor_component/external/rslidar_msg/{ros1,ros2}` —
   upstream ships `rslidar_msg` 3× with the same `<name>`; colcon rejects duplicates.
4. **Upgraded `ros-humble-tensorrt-cmake-module` 0.0.3 → 0.0.5.** 0.0.3 (Nov 2023)
   unconditionally added `nvparsers` to `TENSORRT_LIBRARY`, but NVIDIA removed that
   library in TensorRT 10, so CMake failed with `TENSORRT_NVPARSERS_LIBRARY NOTFOUND`
   in `autoware_tensorrt_common`. 0.0.5 guards it with
   `if(TENSORRT_VERSION_MAJOR VERSION_LESS 9)`. Note `rosdep install` does **not**
   upgrade already-installed packages, so stale ones like this stay stale.
5. **Fixed `CUDA_HOME` in `~/.bashrc`** (was `/usr/local/cuda-11.8`, now
   `/usr/local/cuda` → 12.8). Lines 144-145 derive `PATH`/`LD_LIBRARY_PATH` from it and
   were prepended *after* the playbook's `cuda/bin` entries, so `nvcc` resolved to
   **11.8** and `autoware_tensorrt_plugins` failed on bfloat16 atomics
   (`__ushort_as_bfloat16` undefined). Backup: `~/.bashrc.bak-cuda-*`.
   If an ML project (anomalib/detectron2/fungivision) needs 11.8, set it per-project —
   Autoware needs 12.8 at build **and** run time.
6. **Removed `libc++-dev`, `libc++-14-dev`, `libunwind-14-dev`.** `libgoogle-glog-dev`
   requires `libunwind-dev`, which conflicts with LLVM 14's `libunwind-14-dev`; rosdep's
   plain `apt-get install` cannot do removals so it just failed. `libc++-dev` was
   manually installed — restore with `sudo apt install libc++-dev` if needed, but it is
   mutually exclusive with the `libunwind-dev` Autoware requires.
7. Re-cloned `src/core/autoware_core` — the first `vcs import` was interrupted and left
   null-SHA refs, which made every later import fail with a misleading
   "did not send all necessary objects".

## Network / IP map

| Device | Address | Notes |
| --- | --- | --- |
| **This PC** on sensor LAN | **192.168.1.20/24** on `enp3s0` | static, **no gateway**, `never-default`. Was `.100` until the OS-2-32 took that address. |
| **Ouster OS-1-128 lidar** | **192.168.1.126** | `os-122345000355.local`, web UI :80, data :7501 |
| **Ouster OS-2-32 lidar** | **192.168.1.100** | web UI :80, data :7501 |
| **CHC CGI-410 GNSS/INS** | **192.168.1.110** | web UI :80 (`admin`/`password`), NMEA TCP **:9904** |
| ichimill NTRIP caster | `ntrip.ales-corp.co.jp:2101` (`52.199.90.201`) | mount point `RTCM32M7S` |
| Internet | wifi `wlp4s0` / USB eth `enx1625e5f9a0e6` | keeps the default route |

Avoid assigning `.102`, `.110`, `.125`, `.126`, `.200` on the vehicle LAN.

Two config changes make this work, both persistent:

- `/etc/NetworkManager/conf.d/10-globally-managed-devices.conf` — overrides the Ubuntu
  default `unmanaged-devices=*,except:type:wifi,...` which left **every wired NIC
  unmanaged**. Without this, `enp3s0` gets no IPv4 at all and `.local` names do not
  resolve (avahi will not do IPv4 mDNS on an interface with no IPv4 address).
- `pixkit-sensor-nat.service` (enabled+active) — masquerades `192.168.1.0/24` out the
  default-route interface so the GNSS receiver can reach the NTRIP caster. Needed
  because Docker sets `FORWARD` policy to `DROP`; rules go in `DOCKER-USER`.

Side effect: making NM manage all ethernet also brought up `enx1625e5f9a0e6` (USB), which
got DHCP `192.168.200.22`. At one point it took the default route at metric 101 ahead of
wifi (600). Internet worked either way. **Open question:** whether to set that profile
`never-default` so wifi stays primary.

## TODO — in this order

### ~~1. NVIDIA driver~~ — DONE

`nvidia-open` 610.57.04 installed, DKMS module built for 6.8.0-136, `nvidia-smi` verified.
Historical detail follows for reference.

<details><summary>original notes</summary>

#### NVIDIA driver (user chose "Option B": `nvidia-open`)

Current GPU is **broken**: RTX 3080 Mobile, `nvidia-driver-535` installed but
`linux-modules-nvidia-535-6.8.0-**59**-generic` while running kernel **6.8.0-136** — no
module loads, `nvidia-smi` fails, no DKMS. A reboot alone will not fix it.

Verified to resolve cleanly (18 packages removed, no errors), and prerequisites are all
present (`linux-headers-6.8.0-136-generic`, `dkms` 2.8.7, Secure Boot **disabled**):

```bash
sudo apt install nvidia-open nvidia-driver-535- libnvidia-fbc1-535- \
     libnvidia-fbc1-535:i386- nvidia-kernel-common-535-
```

Pulls `nvidia-open` / `nvidia-dkms-open` / `nvidia-kernel-source-open` 610.57.04.
`nvidia-dkms-open` rebuilds on kernel upgrades, which is what prevents a repeat.

**Before rebooting, confirm the module built:**

```bash
dkms status            # expect nvidia .. 610.57.04 .. 6.8.0-136-generic: installed
```

If that fails, do **not** expect a working GPU after reboot (harmless — the display is
on the Intel iGPU). After reboot: `nvidia-smi` should work.

Note: 8 TensorRT packages are `apt-mark hold` (set by the playbook). They do **not**
block the driver install; apt's "may be caused by held packages" hint there is a red
herring — the real conflict was the 535 stack.

</details>

### ~~2. Dependencies + build~~ — DONE

`rosdep install` (204 pkgs) and `colcon build` (492/492, 0 failed) both complete.
To rebuild after changes: `colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release`
(ccache is warm now, so incremental builds are much faster).

<details><summary>original notes</summary>

#### Dependencies + build

```bash
cd /home/ehsan/workspace/pix_autoware/pixkit_autoware
source /opt/ros/humble/setup.bash
rosdep update
rosdep install -y --from-paths src --ignore-src --rosdistro "$ROS_DISTRO"
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
```

`rosdep install` has **not** been run yet — it is the authoritative dependency check.
A static pre-flight resolved all 98 Pixkit dependencies, and the 6 ROS 1 keys
(`roscpp`, `rospy`, `nodelet`, …) appear only in `COLCON_IGNORE`d packages.

Nothing is compile-verified yet. If the 0.45.1→1.9.0 drift bites, expect it in
`pix_hooke_driver` (vehicle interface) or the Pixkit launch configs.

Do **not** rename the workspace after building — colcon bakes absolute paths into
`build/` and `install/`.

</details>

### 2.5. Post-reboot cleanup: purge obsolete kernels

This machine has 10+ installed kernels. DKMS rebuilds the NVIDIA module for **every**
one of them, which is why the 610.57.04 install took so long (it built for 5.15.0-56,
5.15.0-60, 5.19.0-46, 6.2.0-39, 6.5.0-44, 6.8.0-59 and 6.8.0-136). Clearing the old ones
makes every future driver/kernel update dramatically faster and frees a lot of `/boot`.

Do this **after** the reboot has confirmed the new driver works (`nvidia-smi` OK), never
before — the currently-booted kernel must stay installed.

```bash
uname -r                          # note the running kernel; it must survive
apt list --installed 'linux-image-*' 'linux-headers-*' 'linux-modules-*' | wc -l
sudo apt autoremove --purge       # REVIEW the list before confirming
```

Check the proposed removal list actually keeps `linux-image-$(uname -r)` and the newest
kernel. If autoremove is too timid (it only removes what it considers orphaned), remove
specific old series explicitly, e.g.:

```bash
sudo apt purge 'linux-image-5.15.0-*' 'linux-headers-5.15.0-*' 'linux-modules-5.15.0-*'
```

Afterwards `dkms status` should list the NVIDIA module for only the remaining kernels.

### 3. RTK

See `RTK_ICHIMILL_SETUP.md`. Host side is done; the receiver still needs its gateway
set to `192.168.1.20` plus the NTRIP client pointed at ichimill account **#4**.
Writes to the receiver were blocked by the permission classifier, so this is either a
manual step in Chrome or needs a Bash permission rule.

### 4. Run

```bash
./autoware_velodyne_kashiwa.sh /path/to/map
```

No map is present on this machine yet (`~/autoware_map` does not exist).

### 5. Deferred: make the single Ouster visible in RViz

Parked 2026-08-18 at the user's request. Everything below is diagnosed, not yet fixed.

**Why RViz shows no points.** The Ouster streams fine (10 Hz on
`/sensing/lidar/top/ouster/points`, TF `base_link -> os_lidar_top` resolves), but
`PointCloudConcatenateDataSynchronizerComponent` refuses to load with a single input:

```
[pointcloud_container] Component constructor threw an exception:
  Only one topic given. Need at least two topics to continue.
```

so `/sensing/lidar/concatenated/pointcloud` has 0 publishers, and that is the topic the
Autoware RViz config displays. Options, cheapest first:

1. Relay: `ros2 run topic_tools relay /sensing/lidar/top/ouster/points /sensing/lidar/concatenated/pointcloud`
2. Replace the concat component with a passthrough / crop-box chain in
   `velodyne_pixkit_sensor_kit_launch/launch/pointcloud_preprocessor.launch.py`
3. Connect the other two Ousters the Pixkit design expects (`os_rl_config.yaml`,
   `os_rr_config.yaml`)

**Initial pose.** `/tf` is empty - no `map -> base_link`, because localization has no
initial pose. Either set `2D Pose Estimate` in RViz, or finish the RTK setup for
GNSS-based auto-init. To eyeball the sensor without localization, set RViz Fixed Frame to
`base_link` and add a PointCloud2 display on the raw Ouster topic.

**Also still open:** `nmea_tcpclient_driver` dies with exit 255 (GNSS NMEA client to
`192.168.1.110:9904`; receiver is reachable, cause not yet found), and `usb_cam_node_exe`
dies because it references the nonexistent package `pixkit_sensor_kit_launch` (left alone
deliberately - no camera connected).

See `VEHICLE_CAN_AND_RUNTIME.md` for the full runtime picture.

## Rollback artifacts — `pixkit_setup_backups/`

| File | Restores |
| --- | --- |
| `pixkit_merge_backup_*.tar.gz` + `pixkit_merge_overwritten_files.txt` | the 106 files Pixkit overwrote → `tar xzf … -C pixkit_autoware` |
| `cgi410_config/*.json` | the GNSS receiver's original settings |
| `ros2.list.backup` | the stale apt source (do not restore — it caused the failure) |
| `google-chrome.list.disabled`, `anydesk-stable.list.disabled` | the two disabled repos |
| `pixkit-sensor-nat.service` | copy of the installed unit |

## Gotchas worth remembering

- Repos manifest lives at `repositories/autoware.repos` at this tag, **not**
  `./autoware.repos` as the upstream docs say.
- `str2str` needs **`-n 5000`**; ichimill mount points are `nmea-required=1` and the
  NMEA request cycle defaults to 0 (never send) → bare `timeout`. RTKLIB build path on
  the default branch is `app/str2str/gcc`, not `app/consapp/str2str/gcc`.
- The `ros2`/`dev_tools` roles use `failed_when: false` on apt tasks, so a failure
  prints as `ok` and then emits a bogus "package is apt-mark hold, skipping" warning
  while installing nothing. Verify with `dpkg -l`, not the playbook output.
