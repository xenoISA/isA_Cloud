#!/bin/bash
# =============================================================================
# ISA Platform — Pre-Flight Verification Script
# =============================================================================
# Validates cluster readiness before production deployment.
# Called automatically by deploy.sh (skippable with --skip-preflight).
#
# Usage:
#   ./preflight.sh                    # Run all checks (uses generic profile)
#   ./preflight.sh --provider infotrend  # Check with specific provider profile
#   ./preflight.sh --nodes 3          # Validate for 3-node cluster
#   ./preflight.sh --provider infotrend --nodes 3  # Both
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NAMESPACE="isa-cloud-production"
MIN_K8S_VERSION="1.27"
PROVIDER="generic"
NODE_COUNT=0  # 0 = don't check node count
ERRORS=0
WARNINGS=0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; ((ERRORS++)); }
warn() { echo -e "  ${YELLOW}!${NC} $1"; ((WARNINGS++)); }
header() { echo -e "\n${BLUE}=== $1 ===${NC}"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --provider) PROVIDER="$2"; shift 2 ;;
        --nodes)    NODE_COUNT="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--provider <name>] [--nodes <count>]"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "=============================================="
echo " ISA Platform — Pre-Flight Checks"
echo " Provider: ${PROVIDER}"
echo " Expected nodes: ${NODE_COUNT:-any}"
echo "=============================================="

# --- 1. Tool availability ---
header "Tool Availability"

for tool in kubectl helm curl; do
    if command -v $tool &>/dev/null; then
        pass "$tool found: $(command -v $tool)"
    else
        fail "$tool not found — install before proceeding"
    fi
done

# --- 2. Kubernetes cluster connectivity ---
header "Cluster Connectivity"

if kubectl cluster-info &>/dev/null; then
    CONTEXT=$(kubectl config current-context)
    pass "Connected to cluster (context: ${CONTEXT})"
else
    fail "Cannot connect to Kubernetes cluster"
    echo -e "\n${RED}FATAL: No cluster connection. Remaining checks skipped.${NC}"
    exit 1
fi

# --- 3. Kubernetes version ---
header "Kubernetes Version"

K8S_VERSION=$(kubectl version --short 2>/dev/null | grep "Server" | awk '{print $3}' | tr -d 'v' || \
              kubectl version -o json 2>/dev/null | grep -o '"gitVersion": "[^"]*"' | head -1 | grep -o '[0-9]\+\.[0-9]\+')

if [[ -n "$K8S_VERSION" ]]; then
    MAJOR=$(echo "$K8S_VERSION" | cut -d. -f1)
    MINOR=$(echo "$K8S_VERSION" | cut -d. -f2)
    MIN_MAJOR=$(echo "$MIN_K8S_VERSION" | cut -d. -f1)
    MIN_MINOR=$(echo "$MIN_K8S_VERSION" | cut -d. -f2)

    if [[ "$MAJOR" -gt "$MIN_MAJOR" ]] || { [[ "$MAJOR" -eq "$MIN_MAJOR" ]] && [[ "$MINOR" -ge "$MIN_MINOR" ]]; }; then
        pass "Kubernetes version ${K8S_VERSION} (>= ${MIN_K8S_VERSION})"
    else
        fail "Kubernetes version ${K8S_VERSION} is below minimum ${MIN_K8S_VERSION}"
    fi
else
    warn "Could not determine Kubernetes version"
fi

# --- 4. Node count and capacity ---
header "Node Resources"

ACTUAL_NODES=$(kubectl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
READY_NODES=$(kubectl get nodes --no-headers 2>/dev/null | grep -c " Ready" || echo 0)

if [[ "$ACTUAL_NODES" -gt 0 ]]; then
    pass "Nodes found: ${ACTUAL_NODES} total, ${READY_NODES} Ready"
else
    fail "No nodes found in cluster"
fi

if [[ "$NODE_COUNT" -gt 0 ]] && [[ "$READY_NODES" -lt "$NODE_COUNT" ]]; then
    fail "Expected ${NODE_COUNT} Ready nodes, found ${READY_NODES}"
elif [[ "$NODE_COUNT" -gt 0 ]]; then
    pass "Node count matches expected: ${NODE_COUNT}"
fi

# Show node capacity summary
echo ""
echo "  Node capacity:"
kubectl get nodes -o custom-columns="NAME:.metadata.name,CPU:.status.capacity.cpu,MEMORY:.status.capacity.memory,DISK:.status.capacity.ephemeral-storage" --no-headers 2>/dev/null | while read line; do
    echo "    $line"
done

# --- 5. Namespace ---
header "Namespace"

if kubectl get namespace ${NAMESPACE} &>/dev/null; then
    pass "Namespace '${NAMESPACE}' exists"
else
    warn "Namespace '${NAMESPACE}' does not exist (deploy.sh will create it)"
fi

# --- 6. Storage classes ---
header "Storage Classes"

# Load provider profile
PROFILE_FILE="${SCRIPT_DIR}/../profiles/${PROVIDER}.yaml"
if [[ -f "$PROFILE_FILE" ]]; then
    pass "Provider profile found: ${PROVIDER}"

    # Parse expected storage classes from profile
    for LOGICAL in block fast nfs object; do
        SC=$(grep "^  ${LOGICAL}:" "$PROFILE_FILE" | sed 's/^.*: *//' | tr -d '"' | tr -d "'")
        if [[ -z "$SC" ]]; then
            pass "Storage '${LOGICAL}': uses default StorageClass"
        elif kubectl get storageclass "$SC" &>/dev/null; then
            pass "Storage '${LOGICAL}': StorageClass '${SC}' exists"
        else
            fail "Storage '${LOGICAL}': StorageClass '${SC}' NOT FOUND"
            echo -e "    ${YELLOW}Hint: Apply storage classes first:${NC}"
            echo "    kubectl apply -f manifests/storage-classes/${PROVIDER}-storage-classes.yaml"
        fi
    done
else
    warn "Provider profile not found: ${PROFILE_FILE}"
    warn "Checking for any available StorageClasses..."
    SC_COUNT=$(kubectl get storageclass --no-headers 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$SC_COUNT" -gt 0 ]]; then
        pass "Found ${SC_COUNT} StorageClass(es) in cluster"
        kubectl get storageclass --no-headers 2>/dev/null | while read line; do
            echo "    $line"
        done
    else
        fail "No StorageClasses found in cluster"
    fi
fi

# --- 7. Helm repos ---
header "Helm Repositories"

REQUIRED_REPOS=("bitnami" "hashicorp" "external-secrets" "apisix" "nats" "qdrant" "emqx" "minio" "neo4j")
for repo in "${REQUIRED_REPOS[@]}"; do
    if helm repo list 2>/dev/null | grep -q "^${repo}"; then
        pass "Helm repo '${repo}' configured"
    else
        warn "Helm repo '${repo}' not configured (deploy.sh will add it)"
    fi
done

# --- 8. Secrets (Vault + ESO) ---
header "Secrets Management"

# Check if Vault is deployed
if kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=vault --no-headers 2>/dev/null | grep -q "Running"; then
    pass "Vault pods running"

    # Check if Vault is unsealed
    VAULT_STATUS=$(kubectl exec -n ${NAMESPACE} vault-0 -- vault status -format=json 2>/dev/null | grep '"sealed"' | tr -d ' ,' || echo "")
    if echo "$VAULT_STATUS" | grep -q "false"; then
        pass "Vault is unsealed"
    elif [[ -n "$VAULT_STATUS" ]]; then
        fail "Vault is sealed — run vault-init.sh to unseal"
    else
        warn "Could not check Vault seal status"
    fi
else
    warn "Vault not deployed yet (deploy secrets first: ./deploy.sh secrets)"
fi

# Check ESO
if kubectl get deployment -n external-secrets external-secrets --no-headers 2>/dev/null | grep -q ""; then
    pass "External Secrets Operator deployed"
else
    warn "External Secrets Operator not deployed (deploy secrets first)"
fi

# Check required secrets
REQUIRED_SECRETS=("postgresql-secret" "redis-secret" "neo4j-secret" "minio-secret")
for secret in "${REQUIRED_SECRETS[@]}"; do
    if kubectl get secret ${secret} -n ${NAMESPACE} &>/dev/null; then
        pass "Secret '${secret}' exists"
    else
        warn "Secret '${secret}' not found (will be created by ESO after Vault seed)"
    fi
done

# --- 9. Network connectivity ---
header "Network"

# DNS resolution
if kubectl run preflight-dns-test --image=busybox:1.36 --restart=Never --rm -i --timeout=30s -- nslookup kubernetes.default.svc.cluster.local &>/dev/null 2>&1; then
    pass "Cluster DNS resolution working"
else
    warn "Could not verify cluster DNS (test pod may need permissions)"
fi

# Check if registry is reachable (via node)
for registry in "registry.k8s.io" "docker.io" "quay.io" "gcr.io"; do
    if kubectl run "preflight-net-${registry//./}" --image=busybox:1.36 --restart=Never --rm -i --timeout=15s -- wget -q -O /dev/null "https://${registry}" &>/dev/null 2>&1; then
        pass "Registry reachable: ${registry}"
    else
        warn "Registry unreachable: ${registry} (may need proxy config)"
    fi
done 2>/dev/null

# Cleanup any leftover test pods
kubectl delete pod -n default -l run=preflight-dns-test --ignore-not-found &>/dev/null 2>&1 || true

# --- 10. Summary ---
echo ""
echo "=============================================="
if [[ "$ERRORS" -eq 0 ]]; then
    echo -e " ${GREEN}PRE-FLIGHT PASSED${NC} (${WARNINGS} warnings)"
    echo "=============================================="
    exit 0
else
    echo -e " ${RED}PRE-FLIGHT FAILED${NC} (${ERRORS} errors, ${WARNINGS} warnings)"
    echo "=============================================="
    echo ""
    echo "Fix the errors above before running deploy.sh"
    exit 1
fi
