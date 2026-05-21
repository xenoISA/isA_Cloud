#!/usr/bin/env bash
# =============================================================================
# install-arc.sh — deploy Actions Runner Controller (ARC) on the local kind
#                   cluster, as close to one command as practical, idempotent.
# =============================================================================
# What this does:
#   1. Verifies prerequisites (kubectl, helm, a reachable cluster).
#   2. Applies the arc-systems / arc-runners namespaces.
#   3. Creates/refreshes the GitHub App auth Secret (arc-github-app).
#   4. Installs/upgrades the ARC controller (gha-runner-scale-set-controller).
#   5. Installs/upgrades the runner scale set (gha-runner-scale-set).
#
# Idempotent: re-running reconciles to the same state (helm upgrade --install,
# kubectl apply, secret recreated only when key material is supplied).
#
# Prerequisites (see docs/runbooks/arc-self-hosted-runners.md):
#   - A running kind cluster (context kind-isa-cloud-local).
#   - A GitHub App registered + installed on the `xenoISA` org. You need its
#     App ID, installation ID, and the downloaded private-key .pem file.
#
# Usage — provide the GitHub App credentials via env vars (recommended):
#   ISA_ARC_GITHUB_APP_ID=123456 \
#   ISA_ARC_GITHUB_APP_INSTALLATION_ID=78901234 \
#   ISA_ARC_GITHUB_APP_PRIVATE_KEY_PATH=~/secrets/isa-arc.private-key.pem \
#     ./install-arc.sh
#
# Or, if you have already applied the Secret yourself (from the template),
# run without the env vars and the script will skip Secret creation:
#   ./install-arc.sh --skip-secret
# =============================================================================

set -euo pipefail

# --- paths -------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VALUES_DIR="$ARC_DIR/values"
MANIFESTS_DIR="$ARC_DIR/manifests"

# --- config (override via env) ----------------------------------------------
CLUSTER_CONTEXT="${ISA_ARC_KUBE_CONTEXT:-kind-isa-cloud-local}"
CONTROLLER_NAMESPACE="${ISA_ARC_CONTROLLER_NAMESPACE:-arc-systems}"
RUNNER_NAMESPACE="${ISA_ARC_RUNNER_NAMESPACE:-arc-runners}"
CONTROLLER_RELEASE="${ISA_ARC_CONTROLLER_RELEASE:-arc}"
RUNNER_RELEASE="${ISA_ARC_RUNNER_RELEASE:-isa-kind-runners}"
SECRET_NAME="${ISA_ARC_SECRET_NAME:-arc-github-app}"

CONTROLLER_CHART="oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller"
RUNNER_CHART="oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set"
# Pin the chart version for reproducible installs. Bump deliberately.
# Verified latest at time of writing: 0.14.1 (controller + scale-set share it).
CHART_VERSION="${ISA_ARC_CHART_VERSION:-0.14.1}"

SKIP_SECRET=false
[[ "${1:-}" == "--skip-secret" ]] && SKIP_SECRET=true

# --- colors ------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
say()  { echo -e "${BLUE}==>${NC} $*"; }
ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $*"; }
die()  { echo -e "${RED}✗ $*${NC}" >&2; exit 1; }

# --- 1. prerequisites --------------------------------------------------------
say "Checking prerequisites"
command -v kubectl >/dev/null 2>&1 || die "kubectl not installed (brew install kubectl)"
command -v helm    >/dev/null 2>&1 || die "helm not installed (brew install helm)"

if ! kubectl config get-contexts -o name 2>/dev/null | grep -qx "$CLUSTER_CONTEXT"; then
    die "kube context '$CLUSTER_CONTEXT' not found. Start the kind cluster first
     (.claude/skills/cluster_operations/scripts/setup-local.sh)."
fi
kubectl config use-context "$CLUSTER_CONTEXT" >/dev/null
kubectl cluster-info >/dev/null 2>&1 || die "cluster '$CLUSTER_CONTEXT' not reachable"
ok "kubectl, helm, cluster '$CLUSTER_CONTEXT' all reachable"

# --- 2. namespaces -----------------------------------------------------------
say "Applying namespaces (arc-systems, arc-runners)"
kubectl apply -f "$MANIFESTS_DIR/namespaces.yaml"
ok "namespaces applied"

# --- 3. GitHub App auth secret ----------------------------------------------
if [[ "$SKIP_SECRET" == true ]]; then
    say "Skipping Secret creation (--skip-secret)"
    kubectl -n "$RUNNER_NAMESPACE" get secret "$SECRET_NAME" >/dev/null 2>&1 \
        || die "Secret '$SECRET_NAME' not present in '$RUNNER_NAMESPACE'. Apply it
     from manifests/github-app-secret.template.yaml before --skip-secret."
    ok "existing Secret '$SECRET_NAME' found"
else
    : "${ISA_ARC_GITHUB_APP_ID:?set ISA_ARC_GITHUB_APP_ID (or pass --skip-secret)}"
    : "${ISA_ARC_GITHUB_APP_INSTALLATION_ID:?set ISA_ARC_GITHUB_APP_INSTALLATION_ID}"
    : "${ISA_ARC_GITHUB_APP_PRIVATE_KEY_PATH:?set ISA_ARC_GITHUB_APP_PRIVATE_KEY_PATH}"
    KEY_PATH="${ISA_ARC_GITHUB_APP_PRIVATE_KEY_PATH/#\~/$HOME}"
    [[ -f "$KEY_PATH" ]] || die "private key file not found: $KEY_PATH"

    say "Creating/refreshing GitHub App Secret '$SECRET_NAME' in '$RUNNER_NAMESPACE'"
    # apply-from-create makes this idempotent: rewrites the Secret in place.
    kubectl create secret generic "$SECRET_NAME" \
        --namespace "$RUNNER_NAMESPACE" \
        --from-literal=github_app_id="$ISA_ARC_GITHUB_APP_ID" \
        --from-literal=github_app_installation_id="$ISA_ARC_GITHUB_APP_INSTALLATION_ID" \
        --from-file=github_app_private_key="$KEY_PATH" \
        --dry-run=client -o yaml | kubectl apply -f -
    ok "Secret '$SECRET_NAME' applied"
fi

# --- 4. ARC controller -------------------------------------------------------
say "Installing/upgrading ARC controller ($CONTROLLER_RELEASE) in $CONTROLLER_NAMESPACE"
helm upgrade --install "$CONTROLLER_RELEASE" "$CONTROLLER_CHART" \
    --version "$CHART_VERSION" \
    --namespace "$CONTROLLER_NAMESPACE" \
    -f "$VALUES_DIR/controller.yaml" \
    --wait --timeout 5m
ok "controller deployed"

# --- 5. runner scale set -----------------------------------------------------
say "Installing/upgrading runner scale set ($RUNNER_RELEASE) in $RUNNER_NAMESPACE"
helm upgrade --install "$RUNNER_RELEASE" "$RUNNER_CHART" \
    --version "$CHART_VERSION" \
    --namespace "$RUNNER_NAMESPACE" \
    -f "$VALUES_DIR/runner-scale-set.yaml" \
    --wait --timeout 5m
ok "runner scale set deployed"

# --- summary -----------------------------------------------------------------
echo
say "ARC install complete"
echo "  Controller : kubectl -n $CONTROLLER_NAMESPACE get pods"
echo "  Runners    : kubectl -n $RUNNER_NAMESPACE get pods,autoscalingrunnerset"
echo "  Verify org : the runner scale set should appear under"
echo "               https://github.com/organizations/xenoISA/settings/actions/runners"
echo "  Workflows  : jobs target it with  runs-on: self-hosted"
echo
warn "If runners do not register, check the listener logs:"
echo "    kubectl -n $RUNNER_NAMESPACE logs -l app.kubernetes.io/component=runner-scale-set-listener"
