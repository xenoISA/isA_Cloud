#!/bin/bash
# =============================================================================
# Vault Initialization & Secret Seeding Script
# =============================================================================
# Run ONCE after deploying Vault for the first time.
# This script:
#   1. Initializes Vault (generates unseal keys + root token)
#   2. Unseals all Vault pods
#   3. Enables the KV v2 secrets engine
#   4. Enables Kubernetes auth for ESO
#   5. Seeds initial infrastructure secrets (interactive prompts)
#
# Usage:
#   ./vault-init.sh              # Full init + unseal + auth + seed
#   ./vault-init.sh unseal       # Unseal only (after pod restart)
#   ./vault-init.sh seed         # Seed/update secrets only
#   ./vault-init.sh status       # Check Vault status
#
# IMPORTANT: Store the unseal keys and root token securely!
#            The init output is saved to vault-init-keys.json (delete after saving).
# =============================================================================

set -e

NAMESPACE="isa-cloud-production"
VAULT_POD="vault-0"
VAULT_PODS=("vault-0" "vault-1" "vault-2")
KEYS_FILE="vault-init-keys.json"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $1"; }

vault_exec() {
    kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault "$@"
}

# Check if Vault pods are running
check_vault_pods() {
    log_step "Checking Vault pods..."
    for pod in "${VAULT_PODS[@]}"; do
        if ! kubectl get pod -n ${NAMESPACE} ${pod} &>/dev/null; then
            log_error "Vault pod ${pod} not found. Deploy Vault first."
            exit 1
        fi
    done
    log_info "All Vault pods found"
}

# Initialize Vault
init_vault() {
    log_step "Initializing Vault..."

    # Check if already initialized
    local status
    status=$(kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault status -format=json 2>/dev/null || true)
    if echo "$status" | grep -q '"initialized":true'; then
        log_warn "Vault is already initialized. Skipping init."
        return 0
    fi

    # Initialize with 5 key shares, 3 threshold
    kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- \
        vault operator init -key-shares=5 -key-threshold=3 -format=json > "${KEYS_FILE}"

    log_info "Vault initialized. Keys saved to ${KEYS_FILE}"
    log_warn "CRITICAL: Save the unseal keys and root token securely, then delete ${KEYS_FILE}!"
    echo ""
    echo "Root Token: $(jq -r '.root_token' ${KEYS_FILE})"
    echo "Unseal Keys:"
    jq -r '.unseal_keys_b64[]' ${KEYS_FILE} | head -5
    echo ""
}

# Unseal all Vault pods
unseal_vault() {
    log_step "Unsealing Vault pods..."

    if [ ! -f "${KEYS_FILE}" ]; then
        log_error "Keys file not found: ${KEYS_FILE}"
        log_info "Provide unseal keys manually:"
        read -sp "Unseal Key 1: " key1; echo
        read -sp "Unseal Key 2: " key2; echo
        read -sp "Unseal Key 3: " key3; echo
        local keys=("$key1" "$key2" "$key3")
    else
        local keys=()
        while IFS= read -r key; do
            keys+=("$key")
        done < <(jq -r '.unseal_keys_b64[:3][]' "${KEYS_FILE}")
    fi

    for pod in "${VAULT_PODS[@]}"; do
        log_info "Unsealing ${pod}..."
        for key in "${keys[@]}"; do
            kubectl exec -n ${NAMESPACE} ${pod} -- vault operator unseal "${key}" &>/dev/null || true
        done
    done

    # Verify
    for pod in "${VAULT_PODS[@]}"; do
        local sealed
        sealed=$(kubectl exec -n ${NAMESPACE} ${pod} -- vault status -format=json 2>/dev/null | jq -r '.sealed')
        if [ "$sealed" = "false" ]; then
            log_info "${pod}: unsealed"
        else
            log_error "${pod}: still sealed!"
        fi
    done
}

# Configure Vault for ESO
configure_vault() {
    log_step "Configuring Vault..."

    # Login with root token
    local root_token
    if [ -f "${KEYS_FILE}" ]; then
        root_token=$(jq -r '.root_token' "${KEYS_FILE}")
    else
        read -sp "Root Token: " root_token; echo
    fi

    kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault login "${root_token}" &>/dev/null

    # Enable KV v2 secrets engine
    log_info "Enabling KV v2 secrets engine at 'secret/'..."
    vault_exec secrets enable -path=secret kv-v2 2>/dev/null || log_warn "KV v2 already enabled"

    # Enable Kubernetes auth
    log_info "Enabling Kubernetes auth..."
    vault_exec auth enable kubernetes 2>/dev/null || log_warn "Kubernetes auth already enabled"

    # Configure Kubernetes auth to use in-cluster config
    vault_exec write auth/kubernetes/config \
        kubernetes_host="https://kubernetes.default.svc.cluster.local:443"

    # Create policy for ESO to read secrets
    log_info "Creating ESO read policy..."
    kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- /bin/sh -c 'vault policy write external-secrets - <<POLICY
path "secret/data/isa-cloud/*" {
  capabilities = ["read"]
}
path "secret/metadata/isa-cloud/*" {
  capabilities = ["read", "list"]
}
POLICY'

    # Create Kubernetes auth role for ESO
    log_info "Creating Kubernetes auth role for ESO..."
    vault_exec write auth/kubernetes/role/external-secrets \
        bound_service_account_names=external-secrets \
        bound_service_account_namespaces=external-secrets \
        policies=external-secrets \
        ttl=1h

    log_info "Vault configured for ESO"
}

# Seed infrastructure secrets
seed_secrets() {
    log_step "Seeding infrastructure secrets in Vault..."
    log_warn "You will be prompted for each secret value."
    echo ""

    # Login
    local root_token
    if [ -f "${KEYS_FILE}" ]; then
        root_token=$(jq -r '.root_token' "${KEYS_FILE}")
    else
        read -sp "Root Token: " root_token; echo
    fi
    kubectl exec -n ${NAMESPACE} ${VAULT_POD} -- vault login "${root_token}" &>/dev/null

    # PostgreSQL
    log_info "PostgreSQL secrets:"
    read -sp "  postgresql-password: " pg_pass; echo
    read -sp "  replication-password: " pg_repl; echo
    read -sp "  pgpool-admin-password: " pg_pool; echo
    vault_exec kv put secret/isa-cloud/production/postgresql \
        password="${pg_pass}" \
        replication-password="${pg_repl}" \
        pgpool-admin-password="${pg_pool}"
    log_info "PostgreSQL secrets stored"

    # Redis
    log_info "Redis secrets:"
    read -sp "  redis-password: " redis_pass; echo
    vault_exec kv put secret/isa-cloud/production/redis \
        password="${redis_pass}"
    log_info "Redis secrets stored"

    # Neo4j
    log_info "Neo4j secrets:"
    read -sp "  neo4j-password: " neo4j_pass; echo
    vault_exec kv put secret/isa-cloud/production/neo4j \
        password="${neo4j_pass}"
    log_info "Neo4j secrets stored"

    # MinIO
    log_info "MinIO secrets:"
    read -p "  root-user [minioadmin]: " minio_user
    minio_user=${minio_user:-minioadmin}
    read -sp "  root-password: " minio_pass; echo
    vault_exec kv put secret/isa-cloud/production/minio \
        root-user="${minio_user}" \
        root-password="${minio_pass}"
    log_info "MinIO secrets stored"

    # EMQX
    log_info "EMQX secrets:"
    read -sp "  dashboard-password: " emqx_pass; echo
    vault_exec kv put secret/isa-cloud/production/emqx \
        dashboard-password="${emqx_pass}"
    log_info "EMQX secrets stored"

    # APISIX
    log_info "APISIX secrets:"
    read -sp "  admin-key: " apisix_key; echo
    vault_exec kv put secret/isa-cloud/production/apisix \
        admin-key="${apisix_key}"
    log_info "APISIX secrets stored"

    echo ""
    log_info "All infrastructure secrets seeded in Vault"
    log_info "ESO will sync them to K8s Secrets within the refresh interval (1h)"
    log_info "To force immediate sync: kubectl annotate externalsecret -n isa-cloud-production --all force-sync=$(date +%s)"
}

# Check Vault status
check_status() {
    log_step "Vault status:"
    echo ""

    for pod in "${VAULT_PODS[@]}"; do
        echo -e "${CYAN}--- ${pod} ---${NC}"
        kubectl exec -n ${NAMESPACE} ${pod} -- vault status 2>/dev/null || echo "  Not reachable"
        echo ""
    done

    # Check ExternalSecrets sync status
    echo -e "${CYAN}--- ExternalSecret sync status ---${NC}"
    kubectl get externalsecret -n isa-cloud-production 2>/dev/null || echo "  No ExternalSecrets found"
}

# Full initialization
full_init() {
    check_vault_pods
    init_vault
    unseal_vault
    configure_vault
    seed_secrets

    echo ""
    log_info "Vault fully initialized and configured!"
    log_warn "REMINDER: Save unseal keys + root token securely, then delete ${KEYS_FILE}"
}

# Main
main() {
    local command="${1:-}"

    case "${command}" in
        unseal)
            check_vault_pods
            unseal_vault
            ;;
        seed)
            check_vault_pods
            seed_secrets
            ;;
        status)
            check_status
            ;;
        configure)
            check_vault_pods
            configure_vault
            ;;
        -h|--help)
            echo "Usage: $0 [unseal|seed|status|configure]"
            echo "  (no args)   Full init + unseal + configure + seed"
            echo "  unseal      Unseal Vault pods (after restart)"
            echo "  seed        Seed/update secrets interactively"
            echo "  status      Check Vault and ExternalSecret status"
            echo "  configure   Re-run Vault auth/policy configuration"
            ;;
        "")
            full_init
            ;;
        *)
            log_error "Unknown command: ${command}"
            echo "Usage: $0 [unseal|seed|status|configure]"
            exit 1
            ;;
    esac
}

main "$@"
