#!/usr/bin/env bash
#
# Install this workspace on an NVIDIA Jetson AGX Orin running JetPack 6 (L4T R36.x,
# Ubuntu 22.04, ROS 2 Humble). See docs/JETSON_INSTALL.md for the reasoning behind
# every deviation from the generic Autoware instructions in README.md.
#
#   bash install-jetson.sh 2>&1 | tee ~/autoware-jetson-install.log
#
# Resume after a failure without redoing finished work:
#   START_STAGE=7 bash install-jetson.sh
#
# Environment overrides:
#   START_STAGE       first stage to run (default 1; see the stage list below)
#   END_STAGE         last stage to run (default 9). Stages 6 and 7 are the only ones
#                     that need root, so END_STAGE=7 runs the part that must be typed
#                     at a terminal with a sudo password, and START_STAGE=8 the rest.
#   PARALLEL_WORKERS  colcon parallelism (default 4 — the Orin runs out of RAM
#                     long before it runs out of cores)
#   DATA_DIR          where the playbook puts ONNX models (default ~/autoware_data/ml_models)
#
# Stages:
#   1 pre-flight     2 ansible        3 collections    4 dev-env playbook
#   5 spconv (opt)   6 agnocast (opt) 7 rosdep         8 duplicate check   9 colcon build

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_STAGE="${START_STAGE:-1}"
END_STAGE="${END_STAGE:-9}"
PARALLEL_WORKERS="${PARALLEL_WORKERS:-4}"
DATA_DIR="${DATA_DIR:-$HOME/autoware_data/ml_models}"
ROSDISTRO=humble

cd "$REPO"

# ---------------------------------------------------------------- output helpers

c_head=$'\033[1;36m'; c_ok=$'\033[32m'; c_warn=$'\033[33m'; c_err=$'\033[31m'; c_off=$'\033[0m'

stage_no=0
stage() {
    stage_no=$1
    shift
    if [ "$stage_no" -lt "$START_STAGE" ] || [ "$stage_no" -gt "$END_STAGE" ]; then
        printf '%s--- [%d/9] %s — skipped (stages %s-%s selected)%s\n' \
            "$c_warn" "$stage_no" "$1" "$START_STAGE" "$END_STAGE" "$c_off"
        return 1
    fi
    printf '\n%s=== [%d/9] %s ===%s\n' "$c_head" "$stage_no" "$1" "$c_off"
    return 0
}
ok()   { printf '%s  ok: %s%s\n'      "$c_ok"   "$1" "$c_off"; }
warn() { printf '%s  WARNING: %s%s\n' "$c_warn" "$1" "$c_off"; }
die()  { printf '%s  ERROR: %s%s\n'   "$c_err"  "$1" "$c_off" >&2; exit 1; }

# ROS and colcon setup scripts read variables they have not set
# (AMENT_TRACE_SETUP_FILES, COLCON_TRACE, ...), which is fatal under `set -u`.
# Relax it for the duration of the source, then restore it.
source_ros() {
    set +u
    # shellcheck disable=SC1091
    source "/opt/ros/$ROSDISTRO/setup.bash"
    set -u
}

resume_hint() {
    printf '\n%sStage %d failed. Fix the cause, then resume with:%s\n' "$c_err" "$stage_no" "$c_off" >&2
    printf '  START_STAGE=%d bash install-jetson.sh\n' "$stage_no" >&2
}
trap 'resume_hint' ERR

# ------------------------------------------------------- preamble
#
# Stages 2 to 7 install packages and need root; 1, 8 and 9 do not. Only ask for a
# password when the selected range actually contains one of the former — otherwise
# the duplicate check and the build can run unattended, which matters because the
# build is the stage that takes hours.
if [ "$START_STAGE" -le 7 ] && [ "$END_STAGE" -ge 2 ]; then
    # Ask once, up front, rather than letting a playbook stall for a password
    # twenty minutes in. With SUDO_ASKPASS set, -A takes the password from that helper
    # instead of a terminal, which is what makes an unattended run possible; the
    # playbooks and rosdep then run off the cached credential.
    if [ -n "${SUDO_ASKPASS:-}" ]; then sudo_v=(sudo -A -v); else sudo_v=(sudo -v); fi
    "${sudo_v[@]}" || die "stages $START_STAGE-$END_STAGE include package installation, which needs sudo.
   Run this range from a terminal that can prompt for a password, point SUDO_ASKPASS
   at a helper that supplies it, or select a range within stages 8-9 (duplicate check
   and build), which need no root."

    # Several roles dearmor a GPG key as root and then verify it as you. If a root task
    # has taken ownership of ~/.gnupg, the verify step fails with "unsafe ownership on
    # homedir" and aborts the role — this is what stopped the agnocast role on this
    # machine. The directory should be yours either way, so fix it.
    if [ -e "$HOME/.gnupg" ] && [ ! -O "$HOME/.gnupg" ]; then
        warn "$HOME/.gnupg is not owned by $(id -un) — correcting (gpg refuses to run otherwise)"
        sudo chown -R "$(id -u):$(id -g)" "$HOME/.gnupg"
        chmod 700 "$HOME/.gnupg"
        ok "$HOME/.gnupg ownership fixed"
    fi
fi

# ------------------------------------------------------- 1. pre-flight
#
# These checks are not decoration. Stage 4 deliberately skips the 'cuda' and 'tensorrt'
# Ansible roles because JetPack already provides both. If JetPack's CUDA/TensorRT were
# in fact missing, the build would fail hundreds of packages in, with an error that
# points at source code rather than at the real cause. Better to stop here.

if stage 1 "Pre-flight"; then
    [ "$(uname -m)" = "aarch64" ] ||
        die "expected aarch64, got $(uname -m). This script is for the Jetson; on x86 follow README.md."

    ubuntu_version="$(lsb_release -rs)"
    [ "$ubuntu_version" = "22.04" ] ||
        die "expected Ubuntu 22.04 (ROS 2 Humble), got $ubuntu_version."

    if [ -r /etc/nv_tegra_release ]; then
        ok "L4T: $(head -1 /etc/nv_tegra_release)"
    else
        warn "/etc/nv_tegra_release missing — is this really a Jetson? Continuing."
    fi

    # JetPack installs CUDA at /usr/local/cuda but does not put it on PATH.
    export PATH="/usr/local/cuda/bin:$PATH"
    command -v nvcc >/dev/null ||
        die "nvcc not found, even with /usr/local/cuda/bin on PATH.
   JetPack's CUDA toolkit is a prerequisite: sudo apt install cuda-toolkit-12-6
   Do NOT install CUDA from NVIDIA's generic Ubuntu repo — see docs/JETSON_INSTALL.md."
    ok "CUDA: $(nvcc --version | tail -1)"

    dpkg -s libnvinfer-dev >/dev/null 2>&1 ||
        die "TensorRT dev package (libnvinfer-dev) not installed.
   On JetPack: sudo apt install tensorrt"
    ok "TensorRT: $(dpkg-query -W -f='${Version}' libnvinfer-dev)"

    if [ -d "/opt/ros/$ROSDISTRO" ]; then
        ok "ROS 2 $ROSDISTRO already present"
    else
        printf '  ROS 2 %s not installed yet — stage 4 will install it\n' "$ROSDISTRO"
    fi

    # build/ alone reaches ~4.5 GB, and the ONNX artifacts add several more.
    avail_gb=$(df -BG --output=avail "$REPO" | tail -1 | tr -dc '0-9')
    if [ "$avail_gb" -lt 40 ]; then
        warn "only ${avail_gb} GB free on this filesystem; the install wants ~40 GB"
    else
        ok "${avail_gb} GB free"
    fi
fi

# ------------------------------------------------------- 2. ansible

if stage 2 "Install Ansible"; then
    bash ansible/scripts/install-ansible.sh
fi
export PATH="${PIPX_BIN_DIR:-$HOME/.local/bin}:/usr/local/cuda/bin:$PATH"

# ------------------------------------------------------- 3. galaxy collections

if stage 3 "Install Ansible collections"; then
    ansible-galaxy collection install -f -r ansible-galaxy-requirements.yaml
fi

# ------------------------------------------------------- 4. dev-env playbook
#
# Four roles are skipped here and handled separately (or dropped):
#
#   cuda      On anything other than x86_64 the role assumes SBSA — it adds NVIDIA's
#             server-ARM apt repo and installs 'nvidia-open', a discrete-GPU driver.
#             A Jetson's GPU driver is part of L4T. Running this role would lay a
#             second, wrong driver stack over JetPack's.
#   tensorrt  Same story: it would pull SBSA TensorRT over JetPack's arm64 build.
#   spconv    Stage 5 — the prebuilt .deb targets a different CUDA minor version, and
#             a failure there should not abort the whole playbook.
#   agnocast  Stage 6 — wants a DKMS module against linux-headers-$(uname -r), which
#             does not exist in the Ubuntu archive for a -tegra kernel.

if stage 4 "Dev environment (skipping cuda, tensorrt, spconv, agnocast)"; then
    ansible-playbook autoware.dev_env.install_dev_env \
        --skip-tags cuda,tensorrt,spconv,agnocast \
        -e "rosdistro=$ROSDISTRO" \
        -e "data_dir=$DATA_DIR" \
        -e install_devel=y
fi

# ------------------------------------------------------- 5. spconv (optional)
#
# Needed by the sparse-convolution lidar detectors (autoware_tensorrt_plugins,
# autoware_lidar_transfusion). The Jetson .deb is built against CUDA 12.8; JetPack 6.1
# ships 12.6. It may work anyway — CUDA is forward compatible across minor versions —
# but if it does not, the damage is confined to those packages.

if stage 5 "spconv (optional)"; then
    if ansible-playbook autoware.dev_env.install_dev_env \
        --tags spconv -e spconv_is_jetson=true; then
        ok "spconv installed"
    else
        warn "spconv failed. Perception packages that need sparse convolution
  (autoware_tensorrt_plugins, autoware_lidar_transfusion, autoware_lidar_centerpoint)
  may fail in stage 9. Exclude them with --packages-skip if you do not need them."
    fi
fi

# ------------------------------------------------------- 6. agnocast (optional)
#
# Zero-copy IPC transport. Opt-in at runtime, so nothing needs it in order to build.

if stage 6 "agnocast (optional)"; then
    if ansible-playbook autoware.dev_env.install_dev_env --tags agnocast; then
        ok "agnocast installed"
    else
        warn "agnocast failed. It is opt-in, off by default, and no package in src/
  needs it in order to build, so the rest of the install is unaffected. The two causes
  seen on this machine, in the order they occur:
    * 'unsafe ownership on homedir ~/.gnupg' during 'Verify GPG key fingerprint' —
      the role dearmors the key as root and verifies it as you. The preamble of this
      script fixes the ownership, so simply re-running the stage clears it.
    * no linux-headers-\$(uname -r) for a -tegra kernel, so the DKMS module cannot
      build. The role itself tolerates this; nothing to fix short of L4T kernel
      sources, and it costs you nothing here."
    fi
fi

# ------------------------------------------------------- 7. rosdep

if stage 7 "Resolve dependencies (rosdep)"; then
    source_ros
    rosdep update
    rosdep install -y --from-paths src --ignore-src --rosdistro "$ROSDISTRO"
fi

# ------------------------------------------------------- 8. duplicate check
#
# README.md step 4: a package present both in src/ and as a ros-humble-* deb builds
# against the wrong headers, and the resulting compile error points at correct code.

if stage 8 "Check for packages installed twice"; then
    source_ros
    dupes=$(comm -12 \
        <(colcon list --base-paths src --names-only | sort) \
        <(dpkg-query -W -f='${Package}\n' "ros-$ROSDISTRO-*" |
            sed "s/^ros-$ROSDISTRO-//; s/-/_/g" | sort))
    if [ -z "$dupes" ]; then
        ok "no duplicates"
    else
        printf '%s\n' "$dupes"
        warn "the packages above exist in src/ AND as Debian packages.
  Remove the Debian copies before building — see README.md step 4:
    sudo apt-get remove -y <ros-$ROSDISTRO-name-with-hyphens>
  Then resume with: START_STAGE=8 bash install-jetson.sh"
        exit 1
    fi
fi

# ------------------------------------------------------- 9. build

if stage 9 "Build"; then
    source_ros
    # --continue-on-error: colcon otherwise stops scheduling at the first failure, so a
    # 511-package build surfaces one problem per multi-hour run. Packages that depend on
    # a failed one are still skipped; only independent ones carry on.
    colcon build --symlink-install \
        --continue-on-error \
        --cmake-args -DCMAKE_BUILD_TYPE=Release \
        --parallel-workers "$PARALLEL_WORKERS"
fi

trap - ERR
printf '\n%s=== Done ===%s\n' "$c_head" "$c_off"
printf 'Source the workspace with:\n  source %s/install/setup.bash\n' "$REPO"
