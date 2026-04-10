#!/bin/bash
# =============================================================================
# Step 2: Enable KVM for Firecracker Agent Runtime
# =============================================================================
# Run this ON EACH NODE that will host Firecracker microVMs.
# Enables KVM kernel modules and configures /dev/kvm permissions.
#
# Usage:
#   ssh root@node1 'bash -s' < 02-enable-kvm.sh
#   OR run directly on the node: ./02-enable-kvm.sh
#
# Prerequisites: Intel VT-x or AMD-V enabled in BIOS
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# --- Check CPU virtualization support ---
log_info "Checking CPU virtualization support..."

VIRT_SUPPORT=""
if grep -qE '(vmx|svm)' /proc/cpuinfo; then
    if grep -q vmx /proc/cpuinfo; then
        VIRT_SUPPORT="Intel VT-x"
    else
        VIRT_SUPPORT="AMD-V"
    fi
    log_info "CPU virtualization supported: ${VIRT_SUPPORT}"
else
    log_error "CPU does not support hardware virtualization (vmx/svm not found in /proc/cpuinfo)"
    log_error "Enable Intel VT-x or AMD-V in BIOS/UEFI settings"
    exit 1
fi

# --- Load KVM modules ---
log_info "Loading KVM kernel modules..."

modprobe kvm
if grep -q vmx /proc/cpuinfo; then
    modprobe kvm_intel nested=1
    KVM_MODULE="kvm_intel"
else
    modprobe kvm_amd nested=1
    KVM_MODULE="kvm_amd"
fi

# Verify modules loaded
if lsmod | grep -q kvm; then
    log_info "KVM modules loaded:"
    lsmod | grep kvm
else
    log_error "Failed to load KVM modules"
    exit 1
fi

# --- Make modules persistent across reboot ---
log_info "Making KVM modules persistent..."

if [ -d /etc/modules-load.d ]; then
    cat > /etc/modules-load.d/kvm.conf << EOF
kvm
${KVM_MODULE}
EOF
    log_info "Created /etc/modules-load.d/kvm.conf"
fi

# Enable nested virtualization persistently
if [ -d /etc/modprobe.d ]; then
    cat > /etc/modprobe.d/kvm-nested.conf << EOF
options ${KVM_MODULE} nested=1
EOF
    log_info "Enabled nested virtualization in /etc/modprobe.d/kvm-nested.conf"
fi

# --- Configure /dev/kvm permissions ---
log_info "Configuring /dev/kvm permissions..."

if [ -e /dev/kvm ]; then
    # Set permissions
    chmod 666 /dev/kvm
    log_info "/dev/kvm permissions set to 666"

    # Make persistent with udev rule
    cat > /etc/udev/rules.d/99-kvm.rules << 'EOF'
KERNEL=="kvm", GROUP="kvm", MODE="0666"
EOF
    log_info "Created udev rule for persistent /dev/kvm permissions"

    # Create kvm group if not exists
    groupadd -f kvm
    log_info "kvm group ensured"
else
    log_error "/dev/kvm does not exist after loading modules"
    log_error "Check BIOS settings and kernel version"
    exit 1
fi

# --- Install Firecracker dependencies ---
log_info "Installing Firecracker dependencies..."

# Detect package manager
if command -v apt-get &>/dev/null; then
    apt-get update -qq
    apt-get install -y -qq qemu-utils e2fsprogs >/dev/null 2>&1 || true
elif command -v yum &>/dev/null; then
    yum install -y -q qemu-img e2fsprogs >/dev/null 2>&1 || true
fi

# --- Verify nested virtualization ---
log_info "Checking nested virtualization..."

NESTED=$(cat /sys/module/${KVM_MODULE}/parameters/nested 2>/dev/null || echo "N")
if [[ "$NESTED" == "Y" ]] || [[ "$NESTED" == "1" ]]; then
    log_info "Nested virtualization: ENABLED"
else
    log_warn "Nested virtualization: DISABLED"
    log_warn "Some Firecracker features may not work without nested virt"
fi

# --- Label the node for K8s scheduling ---
log_info "Labeling this node for KVM workloads..."
HOSTNAME=$(hostname)
log_info "Node hostname: ${HOSTNAME}"
log_warn "Run this from your kubectl machine:"
echo "  kubectl label node ${HOSTNAME} kvm-enabled=true --overwrite"

# --- Verification summary ---
echo ""
log_info "=============================================="
log_info " KVM Setup Complete"
log_info "=============================================="
echo ""
echo "  CPU Virtualization: ${VIRT_SUPPORT}"
echo "  KVM Module:         ${KVM_MODULE}"
echo "  /dev/kvm:           $(ls -la /dev/kvm 2>/dev/null | awk '{print $1, $3, $4}')"
echo "  Nested Virt:        ${NESTED}"
echo ""
log_info "After running on all nodes, label them from kubectl:"
echo "  kubectl label node node1 kvm-enabled=true"
echo "  kubectl label node node2 kvm-enabled=true"
echo "  kubectl label node node3 kvm-enabled=true"
echo ""
log_info "Next: Run Step 3 (storage classes) from your kubectl machine"
