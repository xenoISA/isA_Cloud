#!/bin/bash
# =============================================================================
# Step 5: Configure Harbor Registry Credentials
# =============================================================================
# Sets up K8s image pull secrets so pods can pull from Harbor.
# Run this FROM YOUR KUBECTL MACHINE.
#
# Usage:
#   ./05-harbor-registry.sh                                    # Interactive
#   ./05-harbor-registry.sh --host harbor.isa.io --user admin  # CLI args
#   HARBOR_PASSWORD=xxx ./05-harbor-registry.sh --host harbor.isa.io --user admin  # Non-interactive
# =============================================================================

set -e

NAMESPACE="isa-cloud-production"
HARBOR_HOST="${HARBOR_HOST:-}"
HARBOR_USER="${HARBOR_USER:-}"
HARBOR_PASSWORD="${HARBOR_PASSWORD:-}"
SECRET_NAME="harbor-registry"

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
        --host)     HARBOR_HOST="$2"; shift 2 ;;
        --user)     HARBOR_USER="$2"; shift 2 ;;
        --password) HARBOR_PASSWORD="$2"; shift 2 ;;
        --secret)   SECRET_NAME="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--host <harbor-url>] [--user <username>] [--password <password>]"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

log_info "=============================================="
log_info " Harbor Registry Setup"
log_info "=============================================="

# --- Check kubectl access ---
if ! kubectl cluster-info &>/dev/null; then
    log_error "Cannot connect to K8s cluster"
    exit 1
fi

# --- Collect credentials interactively if not provided ---
if [[ -z "$HARBOR_HOST" ]]; then
    read -p "Harbor registry host (e.g., harbor.isa.io): " HARBOR_HOST
fi

if [[ -z "$HARBOR_USER" ]]; then
    read -p "Harbor username: " HARBOR_USER
fi

if [[ -z "$HARBOR_PASSWORD" ]]; then
    read -sp "Harbor password: " HARBOR_PASSWORD
    echo ""
fi

if [[ -z "$HARBOR_HOST" ]] || [[ -z "$HARBOR_USER" ]] || [[ -z "$HARBOR_PASSWORD" ]]; then
    log_error "All fields required: host, user, password"
    exit 1
fi

# --- Test connectivity ---
log_info "Testing connectivity to ${HARBOR_HOST}..."
if curl -sf -o /dev/null "https://${HARBOR_HOST}/api/v2.0/health" 2>/dev/null; then
    log_info "Harbor is reachable and healthy"
elif curl -sf -o /dev/null "http://${HARBOR_HOST}/api/v2.0/health" 2>/dev/null; then
    log_warn "Harbor reachable over HTTP (not HTTPS) — consider enabling TLS"
else
    log_warn "Cannot reach Harbor health endpoint — may still work for pulls"
fi

# --- Create namespace if needed ---
kubectl get namespace ${NAMESPACE} &>/dev/null || kubectl create namespace ${NAMESPACE}

# --- Create image pull secret ---
log_info "Creating image pull secret '${SECRET_NAME}' in ${NAMESPACE}..."

kubectl create secret docker-registry ${SECRET_NAME} \
    --namespace ${NAMESPACE} \
    --docker-server="${HARBOR_HOST}" \
    --docker-username="${HARBOR_USER}" \
    --docker-password="${HARBOR_PASSWORD}" \
    --dry-run=client -o yaml | kubectl apply -f -

log_info "Secret '${SECRET_NAME}' created/updated"

# --- Patch default service account to use this secret ---
log_info "Patching default ServiceAccount to use image pull secret..."

kubectl patch serviceaccount default -n ${NAMESPACE} \
    -p "{\"imagePullSecrets\": [{\"name\": \"${SECRET_NAME}\"}]}" 2>/dev/null || {
    log_warn "Could not auto-patch default SA — add imagePullSecrets manually to deployments"
}

# --- Also create in gpu-operator namespace if it exists ---
if kubectl get namespace gpu-operator &>/dev/null; then
    log_info "Creating pull secret in gpu-operator namespace..."
    kubectl create secret docker-registry ${SECRET_NAME} \
        --namespace gpu-operator \
        --docker-server="${HARBOR_HOST}" \
        --docker-username="${HARBOR_USER}" \
        --docker-password="${HARBOR_PASSWORD}" \
        --dry-run=client -o yaml | kubectl apply -f -
fi

# --- Also create in external-secrets namespace ---
if kubectl get namespace external-secrets &>/dev/null; then
    log_info "Creating pull secret in external-secrets namespace..."
    kubectl create secret docker-registry ${SECRET_NAME} \
        --namespace external-secrets \
        --docker-server="${HARBOR_HOST}" \
        --docker-username="${HARBOR_USER}" \
        --docker-password="${HARBOR_PASSWORD}" \
        --dry-run=client -o yaml | kubectl apply -f -
fi

# --- Verify ---
echo ""
log_info "Verifying image pull secret..."
kubectl get secret ${SECRET_NAME} -n ${NAMESPACE} -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d | python3 -c "
import json, sys
config = json.load(sys.stdin)
for server, creds in config.get('auths', {}).items():
    print(f'  Registry: {server}')
    print(f'  Username: {creds.get(\"username\", \"N/A\")}')
    print(f'  Auth:     ****configured****')
" 2>/dev/null || log_warn "Could not verify secret contents"

# --- Test pull (optional) ---
echo ""
log_info "To test image pull, run:"
echo "  kubectl run harbor-test --image=${HARBOR_HOST}/isa/isa-data:latest --restart=Never -n ${NAMESPACE}"
echo "  kubectl get pod harbor-test -n ${NAMESPACE}"
echo "  kubectl delete pod harbor-test -n ${NAMESPACE}"

echo ""
log_info "=============================================="
log_info " Harbor registry setup complete"
log_info "=============================================="
echo ""
log_info "All prerequisites done! Deploy with:"
echo "  cd ../  &&  ./deploy.sh all --provider infotrend --nodes 3"
