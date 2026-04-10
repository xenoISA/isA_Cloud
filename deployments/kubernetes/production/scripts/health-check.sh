#!/bin/bash
# =============================================================================
# ISA Platform — Post-Deploy Health Verification
# =============================================================================
# Verifies the full stack is production-ready after deployment.
# Can be run standalone or called by deploy.sh after completion.
#
# Usage:
#   ./health-check.sh               # Full health check
#   ./health-check.sh --quick       # Skip slow checks (Consul, APISIX)
#   ./health-check.sh --component postgres  # Check single component
# =============================================================================

set -e

NAMESPACE="isa-cloud-production"
ERRORS=0
WARNINGS=0
QUICK=false
COMPONENT=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; ((ERRORS++)); }
warn() { echo -e "  ${YELLOW}!${NC} $1"; ((WARNINGS++)); }
header() { echo -e "\n${BLUE}=== $1 ===${NC}"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)     QUICK=true; shift ;;
        --component) COMPONENT="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--quick] [--component <name>]"
            echo "Components: etcd, postgres, redis, neo4j, minio, nats, qdrant, emqx, consul, apisix, vault"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "=============================================="
echo " ISA Platform — Health Check"
echo " Namespace: ${NAMESPACE}"
echo " Mode: ${QUICK:+quick}${COMPONENT:+component=${COMPONENT}}${QUICK:-${COMPONENT:-full}}"
echo "=============================================="

# Helper: check pods for a label selector
check_pods() {
    local name="$1"
    local selector="$2"
    local expected_min="${3:-1}"

    local total=$(kubectl get pods -n ${NAMESPACE} -l "${selector}" --no-headers 2>/dev/null | wc -l | tr -d ' ')
    local ready=$(kubectl get pods -n ${NAMESPACE} -l "${selector}" --no-headers 2>/dev/null | grep -c "Running" || echo 0)

    if [[ "$total" -eq 0 ]]; then
        fail "${name}: no pods found (selector: ${selector})"
        return 1
    elif [[ "$ready" -lt "$expected_min" ]]; then
        fail "${name}: ${ready}/${total} running (need >= ${expected_min})"
        kubectl get pods -n ${NAMESPACE} -l "${selector}" --no-headers 2>/dev/null | grep -v "Running" | while read line; do
            echo -e "    ${YELLOW}${line}${NC}"
        done
        return 1
    else
        pass "${name}: ${ready}/${total} running"
        return 0
    fi
}

# Helper: check Helm release
check_helm() {
    local name="$1"
    if helm status "${name}" -n ${NAMESPACE} &>/dev/null; then
        local status=$(helm status "${name}" -n ${NAMESPACE} -o json 2>/dev/null | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        if [[ "$status" == "deployed" ]]; then
            pass "${name}: Helm release deployed"
        else
            warn "${name}: Helm release status = ${status}"
        fi
    else
        fail "${name}: Helm release not found"
    fi
}

# Helper: check PVC bound
check_pvcs() {
    local selector="$1"
    local pending=$(kubectl get pvc -n ${NAMESPACE} -l "${selector}" --no-headers 2>/dev/null | grep -c "Pending" || echo 0)
    local bound=$(kubectl get pvc -n ${NAMESPACE} -l "${selector}" --no-headers 2>/dev/null | grep -c "Bound" || echo 0)
    local total=$((pending + bound))

    if [[ "$total" -eq 0 ]]; then
        return 0  # No PVCs for this component
    elif [[ "$pending" -gt 0 ]]; then
        fail "PVCs: ${pending} pending (${bound} bound)"
        kubectl get pvc -n ${NAMESPACE} -l "${selector}" --no-headers 2>/dev/null | grep "Pending" | while read line; do
            echo -e "    ${YELLOW}${line}${NC}"
        done
    else
        pass "PVCs: ${bound} bound"
    fi
}

should_check() {
    [[ -z "$COMPONENT" ]] || [[ "$COMPONENT" == "$1" ]]
}

# --- Infrastructure Components ---

if should_check "etcd"; then
    header "etcd"
    check_pods "etcd" "app=etcd" 2
    # Check cluster health
    ETCD_POD=$(kubectl get pods -n ${NAMESPACE} -l app=etcd -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [[ -n "$ETCD_POD" ]]; then
        if kubectl exec -n ${NAMESPACE} ${ETCD_POD} -- etcdctl endpoint health --cluster 2>/dev/null | grep -q "is healthy"; then
            pass "etcd cluster healthy"
        else
            warn "etcd cluster health check inconclusive"
        fi
    fi
fi

if should_check "vault"; then
    header "Vault"
    check_pods "Vault" "app.kubernetes.io/name=vault" 1
    check_helm "vault"
fi

if should_check "postgres"; then
    header "PostgreSQL HA"
    check_pods "PostgreSQL" "app.kubernetes.io/name=postgresql-ha" 2
    check_helm "postgresql"
    # Check replication
    PG_POD=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=postgresql-ha,app.kubernetes.io/component=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [[ -n "$PG_POD" ]]; then
        REPLICAS=$(kubectl exec -n ${NAMESPACE} ${PG_POD} -- psql -U postgres -tAc "SELECT count(*) FROM pg_stat_replication;" 2>/dev/null || echo "?")
        if [[ "$REPLICAS" =~ ^[0-9]+$ ]] && [[ "$REPLICAS" -gt 0 ]]; then
            pass "PostgreSQL replication active (${REPLICAS} standbys)"
        else
            warn "PostgreSQL replication status unknown"
        fi
    fi
fi

if should_check "redis"; then
    header "Redis Cluster"
    check_pods "Redis" "app.kubernetes.io/name=redis-cluster" 3
    check_helm "redis"
    # Check cluster slots
    REDIS_POD=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=redis-cluster -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [[ -n "$REDIS_POD" ]]; then
        SLOTS=$(kubectl exec -n ${NAMESPACE} ${REDIS_POD} -- redis-cli cluster info 2>/dev/null | grep "cluster_slots_ok" | tr -d '[:space:]' | cut -d: -f2 || echo "?")
        if [[ "$SLOTS" == "16384" ]]; then
            pass "Redis cluster: all 16384 slots covered"
        elif [[ "$SLOTS" =~ ^[0-9]+$ ]]; then
            fail "Redis cluster: only ${SLOTS}/16384 slots covered"
        else
            warn "Redis cluster slot status unknown"
        fi
    fi
fi

if should_check "neo4j"; then
    header "Neo4j"
    check_pods "Neo4j" "app=neo4j" 2
    check_helm "neo4j"
fi

if should_check "minio"; then
    header "MinIO"
    check_pods "MinIO" "app=minio" 2
    check_helm "minio"
fi

if should_check "nats"; then
    header "NATS JetStream"
    check_pods "NATS" "app.kubernetes.io/name=nats" 2
    check_helm "nats"
    # Check JetStream status
    NATS_POD=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=nats -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [[ -n "$NATS_POD" ]]; then
        if kubectl exec -n ${NAMESPACE} ${NATS_POD} -- nats server check jetstream 2>/dev/null | grep -q "OK"; then
            pass "NATS JetStream operational"
        else
            warn "NATS JetStream status unknown"
        fi
    fi
fi

if should_check "qdrant"; then
    header "Qdrant"
    check_pods "Qdrant" "app.kubernetes.io/name=qdrant" 2
    check_helm "qdrant"
fi

if should_check "emqx"; then
    header "EMQX"
    check_pods "EMQX" "app.kubernetes.io/name=emqx" 2
    check_helm "emqx"
fi

if should_check "consul"; then
    header "Consul"
    check_pods "Consul server" "app=consul,component=server" 2
    check_helm "consul"

    if [[ "$QUICK" != true ]]; then
        # Check service count in Consul
        CONSUL_POD=$(kubectl get pods -n ${NAMESPACE} -l app=consul,component=server -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
        if [[ -n "$CONSUL_POD" ]]; then
            SVC_COUNT=$(kubectl exec -n ${NAMESPACE} ${CONSUL_POD} -- consul catalog services 2>/dev/null | wc -l | tr -d ' ' || echo "?")
            if [[ "$SVC_COUNT" =~ ^[0-9]+$ ]] && [[ "$SVC_COUNT" -gt 1 ]]; then
                pass "Consul: ${SVC_COUNT} services registered"
            else
                warn "Consul: service count = ${SVC_COUNT}"
            fi
        fi
    fi
fi

if should_check "apisix"; then
    header "APISIX"
    check_pods "APISIX" "app.kubernetes.io/name=apisix" 1
    check_helm "apisix"

    if [[ "$QUICK" != true ]]; then
        # Check route count via admin API
        APISIX_POD=$(kubectl get pods -n ${NAMESPACE} -l app.kubernetes.io/name=apisix -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
        if [[ -n "$APISIX_POD" ]]; then
            ROUTE_COUNT=$(kubectl exec -n ${NAMESPACE} ${APISIX_POD} -- curl -s http://127.0.0.1:9180/apisix/admin/routes 2>/dev/null | grep -o '"total_size":[0-9]*' | cut -d: -f2 || echo "?")
            if [[ "$ROUTE_COUNT" =~ ^[0-9]+$ ]]; then
                pass "APISIX: ${ROUTE_COUNT} routes configured"
            else
                warn "APISIX: could not query route count"
            fi
        fi
    fi
fi

# --- Cross-cutting checks ---

if [[ -z "$COMPONENT" ]]; then
    header "PVC Status (all)"
    PENDING_PVCS=$(kubectl get pvc -n ${NAMESPACE} --no-headers 2>/dev/null | grep -c "Pending" || echo 0)
    BOUND_PVCS=$(kubectl get pvc -n ${NAMESPACE} --no-headers 2>/dev/null | grep -c "Bound" || echo 0)
    TOTAL_PVCS=$((PENDING_PVCS + BOUND_PVCS))

    if [[ "$PENDING_PVCS" -gt 0 ]]; then
        fail "PVCs: ${PENDING_PVCS}/${TOTAL_PVCS} pending"
        kubectl get pvc -n ${NAMESPACE} --no-headers 2>/dev/null | grep "Pending"
    elif [[ "$TOTAL_PVCS" -gt 0 ]]; then
        pass "PVCs: all ${TOTAL_PVCS} bound"
    else
        warn "No PVCs found"
    fi

    header "Pod Disruption Budgets"
    PDB_COUNT=$(kubectl get pdb -n ${NAMESPACE} --no-headers 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$PDB_COUNT" -gt 0 ]]; then
        DISRUPTED=$(kubectl get pdb -n ${NAMESPACE} --no-headers 2>/dev/null | awk '{if ($4 == 0) print $0}' || true)
        if [[ -n "$DISRUPTED" ]]; then
            warn "Some PDBs have 0 disruptions allowed:"
            echo "$DISRUPTED" | while read line; do echo "    $line"; done
        else
            pass "All ${PDB_COUNT} PDBs satisfied"
        fi
    else
        warn "No PDBs configured"
    fi

    header "Backup CronJobs"
    CRON_COUNT=$(kubectl get cronjob -n ${NAMESPACE} --no-headers 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$CRON_COUNT" -gt 0 ]]; then
        pass "Backup CronJobs: ${CRON_COUNT} configured"
        kubectl get cronjob -n ${NAMESPACE} --no-headers 2>/dev/null | while read line; do
            echo "    $line"
        done
    else
        warn "No backup CronJobs configured"
    fi

    header "Recent Warning Events"
    WARNINGS_EVENTS=$(kubectl get events -n ${NAMESPACE} --field-selector type=Warning --sort-by='.lastTimestamp' --no-headers 2>/dev/null | tail -5)
    if [[ -n "$WARNINGS_EVENTS" ]]; then
        warn "Recent warning events:"
        echo "$WARNINGS_EVENTS" | while read line; do
            echo "    $line"
        done
    else
        pass "No recent warning events"
    fi
fi

# --- Summary ---
echo ""
echo "=============================================="
if [[ "$ERRORS" -eq 0 ]]; then
    echo -e " ${GREEN}HEALTH CHECK PASSED${NC} (${WARNINGS} warnings)"
    echo "=============================================="
    exit 0
else
    echo -e " ${RED}HEALTH CHECK FAILED${NC} (${ERRORS} errors, ${WARNINGS} warnings)"
    echo "=============================================="
    exit 1
fi
