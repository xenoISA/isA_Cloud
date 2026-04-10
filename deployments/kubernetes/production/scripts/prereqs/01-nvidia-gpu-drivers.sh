#!/bin/bash
# =============================================================================
# Step 1: Install NVIDIA GPU Drivers on IEC Nodes
# =============================================================================
# Run this ON EACH NODE that has NVIDIA GPUs (via SSH or node access).
# Alternatively, set GPU_OPERATOR_DRIVER=true in gpu-operator values to
# let the GPU Operator manage drivers (slower but hands-off).
#
# Usage:
#   ssh root@node1 'bash -s' < 01-nvidia-gpu-drivers.sh
#   OR run directly on the node: ./01-nvidia-gpu-drivers.sh
#
# Prerequisites: Ubuntu 22.04+ or RHEL 8+, internet access
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

DRIVER_VERSION="${NVIDIA_DRIVER_VERSION:-550}"

# --- Check if already installed ---
if command -v nvidia-smi &>/dev/null; then
    INSTALLED_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
    log_info "NVIDIA driver already installed: ${INSTALLED_VERSION}"
    nvidia-smi
    echo ""
    log_warn "To reinstall, uninstall first: apt remove --purge 'nvidia-*' or yum remove 'nvidia-*'"
    exit 0
fi

# --- Detect OS ---
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="${ID}"
    OS_VERSION="${VERSION_ID}"
else
    log_error "Cannot detect OS. Supported: ubuntu, rhel, centos, rocky"
    exit 1
fi

log_info "Detected OS: ${OS_ID} ${OS_VERSION}"
log_info "Installing NVIDIA driver branch: ${DRIVER_VERSION}"

case "${OS_ID}" in
    ubuntu|debian)
        # --- Ubuntu/Debian ---
        log_info "Installing via NVIDIA CUDA repository..."

        # Install prerequisites
        apt-get update
        apt-get install -y linux-headers-$(uname -r) build-essential dkms

        # Add NVIDIA repository
        DISTRO="ubuntu$(echo ${OS_VERSION} | tr -d '.')"
        ARCH=$(dpkg --print-architecture)
        apt-get install -y gnupg2
        apt-key adv --fetch-keys "https://developer.download.nvidia.com/compute/cuda/repos/${DISTRO}/${ARCH}/3bf863cc.pub" 2>/dev/null || true
        echo "deb https://developer.download.nvidia.com/compute/cuda/repos/${DISTRO}/${ARCH} /" > /etc/apt/sources.list.d/cuda.list
        apt-get update

        # Install driver
        apt-get install -y "nvidia-driver-${DRIVER_VERSION}"

        # Install container toolkit
        log_info "Installing NVIDIA Container Toolkit..."
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -s -L "https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list" | \
            sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
            tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
        apt-get update
        apt-get install -y nvidia-container-toolkit
        ;;

    rhel|centos|rocky|almalinux)
        # --- RHEL/CentOS/Rocky ---
        log_info "Installing via NVIDIA CUDA repository..."

        # Install prerequisites
        yum install -y kernel-devel-$(uname -r) kernel-headers-$(uname -r) gcc make dkms

        # Add NVIDIA repository
        DISTRO="rhel${OS_VERSION%%.*}"
        ARCH=$(uname -m)
        yum install -y "https://developer.download.nvidia.com/compute/cuda/repos/${DISTRO}/${ARCH}/cuda-repo-${DISTRO}.rpm" || true
        yum clean all

        # Install driver
        yum module install -y "nvidia-driver:${DRIVER_VERSION}-dkms" 2>/dev/null || \
            yum install -y "nvidia-driver-${DRIVER_VERSION}" 2>/dev/null || \
            yum install -y kmod-nvidia

        # Install container toolkit
        log_info "Installing NVIDIA Container Toolkit..."
        curl -s -L https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo | \
            tee /etc/yum.repos.d/nvidia-container-toolkit.repo
        yum install -y nvidia-container-toolkit
        ;;

    *)
        log_error "Unsupported OS: ${OS_ID}. Install NVIDIA drivers manually."
        log_error "See: https://docs.nvidia.com/datacenter/tesla/tesla-installation-notes/"
        exit 1
        ;;
esac

# --- Configure container runtime ---
log_info "Configuring containerd for NVIDIA runtime..."
nvidia-ctk runtime configure --runtime=containerd 2>/dev/null || {
    log_warn "nvidia-ctk not available — configure containerd manually"
    log_warn "Add nvidia runtime to /etc/containerd/config.toml"
}

# --- Verify ---
log_info "Loading NVIDIA kernel modules..."
modprobe nvidia 2>/dev/null || true
modprobe nvidia_uvm 2>/dev/null || true

if command -v nvidia-smi &>/dev/null; then
    echo ""
    log_info "NVIDIA driver installed successfully:"
    nvidia-smi
    echo ""
    log_info "GPU count: $(nvidia-smi --query-gpu=count --format=csv,noheader | head -1)"
    log_info "GPU model: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
    log_info "VRAM: $(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1)"
else
    log_warn "nvidia-smi not available yet — REBOOT REQUIRED"
    log_warn "Run: reboot"
    log_warn "After reboot, verify with: nvidia-smi"
fi

echo ""
log_info "=============================================="
log_info " Next: Reboot if prompted, then run Step 2"
log_info "=============================================="
