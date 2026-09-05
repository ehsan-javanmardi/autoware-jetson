# Installing on the Jetson AGX Orin

This repository is the workspace for running Autoware **on an NVIDIA Jetson AGX Orin**,
driving a **Segway RMP Plus 401** mobile base. The tree was forked from a Pixkit workspace
built for an x86 desktop with a discrete RTX GPU, and that origin shows up most sharply
during install: Autoware's own tooling assumes the x86 case throughout.

This page is the record of what actually differs. Every deviation below was found by
running it, not by reading the code.

Run [`install-jetson.sh`](../install-jetson.sh) from the repository root:

```bash
cd ~/workspace/autoware-jetson
bash install-jetson.sh 2>&1 | tee ~/autoware-jetson-install.log
```

It runs nine stages and prints a resume command if any of them fails, so a failure
part-way through costs you only the failed stage:

```bash
START_STAGE=7 bash install-jetson.sh
```

Budget about three hours, nearly all of it in stage 9. The reference run on this Orin
built 510 packages in 2 h 55 min at 6 workers, with no failures.

## Why not just run the standard playbook

Because on a Jetson, two of its roles will install the wrong thing over JetPack.

**JetPack already provides the entire NVIDIA stack** — GPU driver, CUDA, cuDNN and
TensorRT — built for Tegra and versioned together with L4T. On this machine:

| | |
| --- | --- |
| Host | Jetson AGX Orin Developer Kit |
| L4T | R36.x (JetPack 6), kernel `5.15.185-tegra` |
| OS | Ubuntu 22.04 LTS, `aarch64` |
| ROS | ROS 2 Humble |
| CUDA | 12.6 (`nvcc` 12.6.68), at `/usr/local/cuda` |
| TensorRT | 10.3.0.30-1+cuda12.5 |

Autoware's Ansible roles do not know about Tegra. They branch on `x86_64` versus
"everything else", and treat everything else as **SBSA** — Server Base System
Architecture, meaning ARM servers like Grace, which use discrete NVIDIA GPUs and the
generic ARM CUDA repository:

- [`ansible/roles/cuda/tasks/main.yaml`](../ansible/roles/cuda/tasks/main.yaml) — the
  architecture is chosen by `if [ "$(uname -m)" = "x86_64" ] … else echo "sbsa"`, and
  the role then installs **`nvidia-open`**, a driver for discrete GPUs. A Jetson's GPU
  driver ships inside L4T. Installing `nvidia-open` here layers a second, wrong driver
  stack over JetPack's.
- [`ansible/roles/tensorrt/README.md`](../ansible/roles/tensorrt/README.md) — pins
  TensorRT `10.3.0.26-1+cuda12.5` for "aarch64 (SBSA)". JetPack has already installed
  `10.3.0.30-1+cuda12.5`, the Tegra build of nearly the same version.

So `install-jetson.sh` skips both roles (`--skip-tags cuda,tensorrt`) and instead
*verifies* in stage 1 that JetPack's CUDA and TensorRT are actually present, failing
early and loudly if they are not.

> [!WARNING]
> Do not "fix" a missing-CUDA error by running the `cuda` role or by following NVIDIA's
> generic Ubuntu CUDA instructions. On a Jetson, CUDA comes from the L4T apt repository
> (`sudo apt install cuda-toolkit-12-6`) or from a JetPack SDK Manager flash.

Two further roles are moved out of the main run into optional stages, so that a failure
in either does not abort an otherwise good install:

| Role | Stage | Why it is separate |
| --- | --- | --- |
| `spconv` | 5 | Installs a prebuilt `.deb`. The role does know about Jetson — [`spconv_is_jetson`](../ansible/roles/spconv/defaults/main.yaml) selects a `-jetson` build instead of `-sbsa` — but the release is tagged `cu128`, built against CUDA 12.8, while JetPack ships 12.6. **It works**: `spconv 2.3.8` and `cumm 0.5.3` install and the sparse-convolution detectors build against them. It is a separate stage only so that a future mismatch fails on its own rather than taking the playbook with it. |
| `agnocast` | 6 | **Does not complete on this machine, and is not installed.** Two independent reasons, in the order they bite. It adds a Launchpad PPA, dearmoring the GPG key as root and verifying it as you, so a root-owned `~/.gnupg` fails the verify step with `unsafe ownership on homedir`; the script's preamble fixes that. Past it, the DKMS module needs `linux-headers-5.15.185-tegra`, which does not exist in the Ubuntu archive — Jetson kernel headers come from L4T sources. Agnocast is an opt-in zero-copy transport, off by default, and nothing in `src/` needs it to build or run. |

Everything else in the playbook — ROS 2 Humble, CycloneDDS, colcon and build tooling,
acados, geographiclib, and the ONNX model artifacts — is architecture independent and
runs unchanged.

## Stages

| Stage | What it does |
| --- | --- |
| 1 | Pre-flight: architecture, Ubuntu version, L4T, CUDA, TensorRT, disk space, sudo |
| 2 | Installs Ansible via pipx ([`ansible/scripts/install-ansible.sh`](../ansible/scripts/install-ansible.sh)) |
| 3 | Installs the Galaxy collections |
| 4 | The dev-env playbook, minus the four roles above |
| 5 | spconv (optional, non-fatal) |
| 6 | agnocast (optional, non-fatal) |
| 7 | `rosdep install` across `src/` |
| 8 | The [duplicate-package check](../README.md#check-for-duplicate-packages-first) |
| 9 | `colcon build --continue-on-error`, at `--parallel-workers 6` |

Stage 9 passes `--continue-on-error` deliberately. colcon's default is to stop scheduling
at the first failure, which on a 511-package tree means one problem discovered per
multi-hour run — the first attempt here died at 97 packages after 38 minutes. With the flag,
only the failed package's dependents are skipped and everything independent carries on, so
one pass surfaces every problem.

There is **no `vcs import` step**: `src/` is committed to this repository, at the
revisions recorded in
[`repositories/imported-revisions.repos`](../repositories/imported-revisions.repos).

## Build parallelism

The default is `--parallel-workers 6`. The first run used 4, on the theory that an Orin
shares one memory pool between CPU and GPU and would OOM before it ran out of cores. That
turned out to be too cautious for this board: 4 workers left 23 GB of 29 GB free, and 6
completed the tree without pressure. Memory is still the failure mode to watch for — a job
killed with no compile error is an OOM, not a bug — so lower it if that happens:

```bash
PARALLEL_WORKERS=2 START_STAGE=9 bash install-jetson.sh
```

A failed build resumes cleanly — colcon skips packages that already finished.

## The Segway base

The target chassis is a **Segway RMP Plus 401** (`14 P01R POLUS`), connected to the Orin
over USB serial through a CP2102 converter. Nothing in the install above touches it, and
**no Segway ROS 2 driver is in `src/` yet** — the vehicle interface currently committed
is `pix_hooke_driver`, for the Pixkit chassis this tree was forked from.

Bring-up is in progress and is documented separately in [SEGWAY_HARDWARE.md](SEGWAY_HARDWARE.md): the
serial link is up and the host side is proven, but the chassis does not answer, most
likely a TX/RX or converter-type issue. Read that file before wiring or powering the
base — it is a powered mobile base, and the safety notes there are not optional.

## Fixes already committed to the tree

A clean run of `install-jetson.sh` now succeeds, but only because four source-level
problems are already fixed in this repository. They are listed in full under
[What is in this workspace](../README.md#what-is-in-this-workspace); the reason to repeat
them here is that each one *stops the build*, and reverting any of them to match upstream
will bring the failure straight back.

| Fix | What breaks without it |
| --- | --- |
| `cuda_blackboard` guarded for CUDA 12.6 | `cudaStreamGetDevice()` arrived in CUDA 12.8. JetPack ships 12.6, and a Jetson's toolkit is versioned with L4T rather than chosen, so the call has to go. Without the guard `cuda_blackboard` will not compile, and it takes the whole CUDA perception stack with it — bevfusion, transfusion, centerpoint, frnet, ptv3, ground segmentation, CUDA pointcloud preprocessor. |
| `casadi` pinned to 3.7.2 | 3.8.0's aarch64 wheel wants `GLIBCXX_3.4.32` (GCC 13); jammy provides at most 3.4.30. Every acados code-generation step then fails at `import casadi`, with an error naming libstdc++ rather than casadi. **Not Jetson-specific** — the same boundary applies on x86 Ubuntu 22.04. |
| `COLCON_IGNORE` on `yabloc_image_processing` | Needs OpenCV contrib's `ximgproc`. JetPack's OpenCV 4.8.0 has no contrib modules, and Ubuntu's `libopencv-contrib-dev` cannot be installed beside it — apt cannot resolve it without displacing JetPack's CUDA-enabled build. |
| `yabloc_image_processing` exec_depend dropped from `tier4_localization_launch` | The quiet one. colcon skips any package whose declared dependency is unavailable, so the ignore above cascades: `tier4_localization_launch`, then `tier4_simulator_launch`, then **`autoware_launch`** — the top-level launch package. The build reports success while the thing you actually launch is missing. |

Verified result on this Orin: **510 packages finished, 0 failed.** The 14 packages that
report `stderr output` are compiler warnings from the CUDA and TensorRT code, not errors.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Stage 1: `nvcc not found` | JetPack's CUDA toolkit is missing or `/usr/local/cuda` is a dangling symlink. `sudo apt install cuda-toolkit-12-6`. Do not use NVIDIA's generic Ubuntu repo. |
| Stage 4 fails in the `ros2` role with an apt error | Usually a stale or conflicting entry in `/etc/apt/sources.list.d/`. Ansible's apt module raises on *any* fetch failure, including one that plain `apt-get update` only warns about, so check `sudo apt-get update` output for `NO_PUBKEY` or `Signed-By` conflicts and disable the offending file. |
| Stage 5 or 6 prints a WARNING | Expected on a Jetson; both are optional and the script continues past them. See the table above. |
| `gpg: WARNING: unsafe ownership on homedir '~/.gnupg'` | A root Ansible task took ownership of your GPG home, so gpg refuses to run as you. The script's preamble corrects it (`chown -R` back to your uid, `chmod 700`); re-run the stage that failed. |
| `AMENT_TRACE_SETUP_FILES: unbound variable` when a stage sources ROS | A shell running under `set -u` sourcing `/opt/ros/humble/setup.bash`, which reads variables it has not set. `install-jetson.sh` handles this in `source_ros()`; if you hit it in your own script, `set +u` before the source. |
| Stage 8 lists packages | A `ros-humble-*` Debian package is shadowing a package in `src/`. Remove the Debian copy — the [duplicate-package check](../README.md#check-for-duplicate-packages-first) explains why this is worth doing rather than ignoring. |
| Stage 9: a job is killed with no compile error | Out of memory. Re-run with a lower `PARALLEL_WORKERS`. |
| Stage 9: `no matching function`, with the header under `/opt/ros/humble/include` and the `.cpp` under `src/` | The stage 8 problem, reached the hard way. |
