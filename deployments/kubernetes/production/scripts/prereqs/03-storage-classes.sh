#!/bin/bash
# =============================================================================
# Step 3: Apply Storage Classes for IEC
# =============================================================================
# Run this FROM YOUR KUBECTL MACHINE (not on individual nodes).
# Creates StorageClasses for the selected provider profile.
#
# Usage:
#   ./03-storage-classes.sh                        # Infotrend (default)
#   ./03-storage-classes.sh --provider generic      # Generic (default SC)
#   ./03-storage-classes.sh --provider infotrend --nfs-server 10.0.1.50 --nfs-share /exports/isa
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/../../manifests/storage-classes"
PROVIDER="infotrend"
NFS_SERVER=""
NFS_SHARE=""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --provider)    PROVIDER="$2"; shift 2 ;;
        --nfs-server)  NFS_SERVER="$2"; shift 2 ;;
        --nfs-share)   NFS_SHARE="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--provider <name>] [--nfs-server <ip>] [--nfs-share <path>]"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

log_info "=============================================="
log_info " Storage Class Setup — Provider: ${PROVIDER}"
log_info "=============================================="

# --- Check kubectl access ---
if ! kubectl cluster-info &>/dev/null; then
    log_error "Cannot connect to K8s cluster. Configure kubectl first."
    exit 1
fi

# --- Show existing storage classes ---
log_info "Current StorageClasses:"
kubectl get storageclass --no-headers 2>/dev/null || echo "  (none)"
echo ""

case "${PROVIDER}" in
    infotrend)
        SC_FILE="${MANIFESTS_DIR}/infotrend-storage-classes.yaml"
        if [[ ! -f "$SC_FILE" ]]; then
            log_error "StorageClass manifest not found: ${SC_FILE}"
            exit 1
        fi

        # Substitute NFS variables if provided
        if [[ -n "$NFS_SERVER" ]] && [[ -n "$NFS_SHARE" ]]; then
            log_info "Substituting NFS config: server=${NFS_SERVER}, share=${NFS_SHARE}"
            TEMP_FILE=$(mktemp)
            sed -e "s|\${NFS_SERVER}|${NFS_SERVER}|g" \
                -e "s|\${NFS_SHARE}|${NFS_SHARE}|g" \
                "$SC_FILE" > "$TEMP_FILE"
            SC_FILE="$TEMP_FILE"
        else
            log_warn "NFS_SERVER and NFS_SHARE not provided"
            log_warn "The infotrend-nfs StorageClass will have placeholder values"
            log_warn "Re-run with: --nfs-server <ip> --nfs-share <path>"
        fi

        log_info "Applying Infotrend StorageClasses..."
        kubectl apply -f "$SC_FILE"

        # Cleanup temp file
        [[ -n "${TEMP_FILE:-}" ]] && rm -f "$TEMP_FILE"

        # Verify CSI driver is available
        log_info "Checking for Infotrend CSI driver..."
        if kubectl get csidrivers 2>/dev/null | grep -q "csi.infotrend"; then
            log_info "Infotrend CSI driver found"
        else
            log_warn "Infotrend CSI driver NOT found in cluster"
            log_warn "Install the Infotrend CSI driver before PVCs can be provisioned"
            log_warn "Refer to Infotrend documentation for CSI driver installation"
        fi

        # Check NFS CSI driver
        if kubectl get csidrivers 2>/dev/null | grep -q "nfs.csi.k8s.io"; then
            log_info "NFS CSI driver found"
        else
            log_warn "NFS CSI driver not found — installing..."
            helm repo add csi-driver-nfs https://raw.githubusercontent.com/kubernetes-csi/csi-driver-nfs/master/charts 2>/dev/null || true
            helm install csi-driver-nfs csi-driver-nfs/csi-driver-nfs \
                --namespace kube-system \
                --set driver.name=nfs.csi.k8s.io 2>/dev/null && \
                log_info "NFS CSI driver installed" || \
                log_warn "NFS CSI driver install failed — install manually if NFS storage needed"
        fi
        ;;

    generic)
        log_info "Generic provider — using cluster default StorageClass"
        DEFAULT_SC=$(kubectl get storageclass -o jsonpath='{.items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")].metadata.name}' 2>/dev/null)
        if [[ -n "$DEFAULT_SC" ]]; then
            log_info "Default StorageClass: ${DEFAULT_SC}"
        else
            log_warn "No default StorageClass found"
            log_warn "Set one with: kubectl patch storageclass <name> -p '{\"metadata\":{\"annotations\":{\"storageclass.kubernetes.io/is-default-class\":\"true\"}}}'"
        fi
        ;;

    aws)
        log_info "AWS provider — creating EBS and EFS StorageClasses..."

        kubectl apply -f - <<'AWSEOF'
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  fsType: ext4
reclaimPolicy: Retain
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer
---
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: io2
provisioner: ebs.csi.aws.com
parameters:
  type: io2
  iops: "5000"
  fsType: ext4
reclaimPolicy: Retain
allowVolumeExpansion: true
volumeBindingMode: WaitForFirstConsumer
AWSEOF

        log_info "AWS StorageClasses created (gp3, io2)"
        log_warn "Ensure the EBS CSI driver is installed: kubectl get csidrivers ebs.csi.aws.com"
        ;;

    *)
        log_error "Unknown provider: ${PROVIDER}"
        log_error "Available: infotrend, generic, aws"
        exit 1
        ;;
esac

# --- Final verification ---
echo ""
log_info "StorageClasses after setup:"
kubectl get storageclass
echo ""
log_info "Next: Run Step 4 (Vault initialization)"
