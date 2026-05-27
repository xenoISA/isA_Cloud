#!/usr/bin/env bash
# =============================================================================
# build-runner-image.sh — build the isA ARC runner image and load it into the
#                         local kind cluster. Idempotent.
#
# Why this exists: jobs running on the stock actions/actions-runner:latest
# image abort when actions/setup-python (and friends) try to download
# toolchains through the kind cluster's slow egress (~150 KB/s, see #306).
# This image pre-bakes Python, Node, pnpm, and uv into the tool cache so
# setup-* actions hit the cache and skip the download path.
#
# What this does:
#   1. Builds runner-image/Dockerfile for the host architecture.
#   2. `kind load`s the resulting image into the local kind cluster.
#   3. Restarts existing ephemeral runners (if any) so future jobs use the
#      new image.
#
# Re-run any time you bump versions in the Dockerfile.
# =============================================================================

set -euo pipefail

# --- paths -------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_DIR="$ARC_DIR/runner-image"

# --- config (override via env) ----------------------------------------------
IMAGE_NAME="${ISA_RUNNER_IMAGE_NAME:-isa-arc-runner}"
IMAGE_TAG="${ISA_RUNNER_IMAGE_TAG:-0.1.0}"
KIND_CLUSTER="${ISA_ARC_KIND_CLUSTER:-isa-cloud-local}"
RUNNER_NAMESPACE="${ISA_ARC_RUNNER_NAMESPACE:-arc-runners}"

IMAGE_REF="${IMAGE_NAME}:${IMAGE_TAG}"

# --- colors ------------------------------------------------------------------
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
say()  { echo -e "${BLUE}==>${NC} $*"; }
ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $*"; }
die()  { echo -e "${RED}✗ $*${NC}" >&2; exit 1; }

# --- prerequisites -----------------------------------------------------------
say "Checking prerequisites"
command -v docker >/dev/null 2>&1 || die "docker not installed"
command -v kind   >/dev/null 2>&1 || die "kind not installed (brew install kind)"
docker info >/dev/null 2>&1 || die "docker daemon not running"
kind get clusters | grep -qx "$KIND_CLUSTER" \
    || die "kind cluster '$KIND_CLUSTER' not found. Start it with the cluster_operations skill."
ok "docker + kind + cluster '$KIND_CLUSTER' reachable"

# --- 1. build ----------------------------------------------------------------
say "Building $IMAGE_REF (host arch only)"
docker build \
    --tag "$IMAGE_REF" \
    --file "$IMAGE_DIR/Dockerfile" \
    "$IMAGE_DIR"
ok "image built: $IMAGE_REF"

# --- 2. load into kind -------------------------------------------------------
say "Loading $IMAGE_REF into kind cluster '$KIND_CLUSTER'"
kind load docker-image "$IMAGE_REF" --name "$KIND_CLUSTER"
ok "image loaded into kind"

# --- 3. roll existing runners ------------------------------------------------
# ARC's ephemeral runners are created from the scale-set template; we cannot
# rolling-restart them like a Deployment. Deleting pending/idle runners forces
# the next job to spawn a fresh pod against the new image.
if kubectl get ns "$RUNNER_NAMESPACE" >/dev/null 2>&1; then
    PODS_TO_DELETE=$(kubectl -n "$RUNNER_NAMESPACE" get pods \
        -l app.kubernetes.io/component=runner \
        --field-selector=status.phase=Pending \
        -o name 2>/dev/null || true)
    if [[ -n "$PODS_TO_DELETE" ]]; then
        say "Rotating pending runners so the new image takes effect"
        echo "$PODS_TO_DELETE" | xargs -r kubectl -n "$RUNNER_NAMESPACE" delete --grace-period=10
        ok "pending runners rotated"
    else
        ok "no pending runners to rotate"
    fi
else
    warn "namespace '$RUNNER_NAMESPACE' not found; skipping runner rotation"
fi

# --- summary -----------------------------------------------------------------
echo
say "Runner image ready"
echo "  Reference  : $IMAGE_REF"
echo "  Cluster    : $KIND_CLUSTER"
echo "  Used by    : deployments/kubernetes/local/arc/values/runner-scale-set.yaml"
echo
echo "  If runner-scale-set.yaml does not already point at this image, apply it:"
echo "    helm upgrade --install isa-kind-runners \\"
echo "      oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set \\"
echo "      --version 0.14.1 --namespace $RUNNER_NAMESPACE \\"
echo "      -f deployments/kubernetes/local/arc/values/runner-scale-set.yaml"
