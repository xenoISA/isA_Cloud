#!/bin/bash
# =============================================================================
# Step 4: Initialize Vault and Seed Secrets
# =============================================================================
# Wrapper around the existing vault-init.sh that deploys secrets first
# if Vault is not already running.
#
# Usage:
#   ./04-vault-init.sh                    # Full init (deploy + init + seed)
#   ./04-vault-init.sh --status           # Check Vault status only
#   ./04-vault-init.sh --unseal-only      # Unseal existing Vault (after restart)
#   ./04-vault-init.sh --provider infotrend --nodes 3  # Pass to deploy.sh
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_SCRIPT="${SCRIPT_DIR}/../deploy.sh"
VAULT_INIT_SCRIPT="${SCRIPT_DIR}/../vault-init.sh"
NAMESPACE="isa-cloud-production"
STATUS_ONLY=false
UNSEAL_ONLY=false
DEPLOY_ARGS=""

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
        --status)       STATUS_ONLY=true; shift ;;
        --unseal-only)  UNSEAL_ONLY=true; shift ;;
        --provider|--nodes)
            DEPLOY_ARGS="${DEPLOY_ARGS} $1 $2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--status] [--unseal-only] [--provider <name>] [--nodes <count>]"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

log_info "=============================================="
log_info " Vault Initialization"
log_info "=============================================="

# --- Check kubectl access ---
if ! kubectl cluster-info &>/dev/null; then
    log_error "Cannot connect to K8s cluster"
    exit 1
fi

# --- Check if Vault is deployed ---
check_vault_status() {
    echo ""
    log_info "Checking Vault deployment status..."

    VAULT_PODS=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=vault --no-headers 2>/dev/null | wc -l | tr -d ' ')
    VAULT_RUNNING=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=vault --no-headers 2>/dev/null | grep -c "Running" || echo 0)

    if [[ "$VAULT_PODS" -eq 0 ]]; then
        log_warn "Vault is NOT deployed"
        return 1
    fi

    log_info "Vault pods: ${VAULT_RUNNING}/${VAULT_PODS} running"

    # Check seal status
    for i in 0 1 2; do
        POD="vault-${i}"
        if kubectl get pod ${POD} -n ${NAMESPACE} &>/dev/null; then
            SEALED=$(kubectl exec -n ${NAMESPACE} ${POD} -- vault status -format=json 2>/dev/null | grep '"sealed"' | grep -o 'true\|false' || echo "unknown")
            INIT=$(kubectl exec -n ${NAMESPACE} ${POD} -- vault status -format=json 2>/dev/null | grep '"initialized"' | grep -o 'true\|false' || echo "unknown")
            echo "  ${POD}: initialized=${INIT}, sealed=${SEALED}"
        fi
    done

    # Check ESO
    ESO_RUNNING=$(kubectl get deployment external-secrets -n external-secrets --no-headers 2>/dev/null | grep -c "1/1" || echo 0)
    echo "  External Secrets Operator: $([ "$ESO_RUNNING" -gt 0 ] && echo 'running' || echo 'not deployed')"

    # Check synced secrets
    echo ""
    log_info "External Secrets sync status:"
    kubectl get externalsecret -n ${NAMESPACE} --no-headers 2>/dev/null || echo "  (none)"

    return 0
}

if [[ "$STATUS_ONLY" == true ]]; then
    check_vault_status
    exit 0
fi

# --- Unseal-only mode ---
if [[ "$UNSEAL_ONLY" == true ]]; then
    log_info "Unsealing Vault pods..."
    log_warn "You will need the unseal keys from the initial initialization."
    echo ""

    for i in 0 1 2; do
        POD="vault-${i}"
        if kubectl get pod ${POD} -n ${NAMESPACE} &>/dev/null; then
            SEALED=$(kubectl exec -n ${NAMESPACE} ${POD} -- vault status -format=json 2>/dev/null | grep '"sealed"' | grep -o 'true\|false' || echo "true")
            if [[ "$SEALED" == "true" ]]; then
                log_info "Unsealing ${POD}..."
                echo "  Enter unseal keys (3 required):"
                for k in 1 2 3; do
                    read -sp "  Key ${k}: " KEY
                    echo ""
                    kubectl exec -n ${NAMESPACE} ${POD} -- vault operator unseal "${KEY}" 2>/dev/null || {
                        log_error "Unseal failed for ${POD}"
                        break
                    }
                done
            else
                log_info "${POD}: already unsealed"
            fi
        fi
    done

    check_vault_status
    exit 0
fi

# --- Full initialization ---

# Step 1: Deploy Vault + ESO if not already deployed
VAULT_PODS=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=vault --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [[ "$VAULT_PODS" -eq 0 ]]; then
    log_info "Vault not deployed — deploying secrets infrastructure..."
    if [[ -x "$DEPLOY_SCRIPT" ]]; then
        "${DEPLOY_SCRIPT}" secrets ${DEPLOY_ARGS}
    else
        log_error "deploy.sh not found at ${DEPLOY_SCRIPT}"
        exit 1
    fi
else
    log_info "Vault already deployed (${VAULT_PODS} pods)"
fi

# Step 2: Initialize and seed via existing vault-init.sh
if [[ -x "$VAULT_INIT_SCRIPT" ]]; then
    log_info "Running vault-init.sh..."
    echo ""
    "${VAULT_INIT_SCRIPT}"
else
    log_error "vault-init.sh not found at ${VAULT_INIT_SCRIPT}"
    log_error "Run it manually: cd scripts && ./vault-init.sh"
    exit 1
fi

# Step 3: Verify
echo ""
check_vault_status

echo ""
log_info "=============================================="
log_info " Vault initialization complete"
log_info " SAVE YOUR UNSEAL KEYS AND ROOT TOKEN SECURELY"
log_info "=============================================="
echo ""
log_info "Next: Run Step 5 (Harbor registry setup)"
