#!/bin/bash
# =============================================================================
# ISA Platform - Production Service Health Check Script
# =============================================================================
# HA-aware health monitoring for production environment.
# Checks cluster status, replication, leader election, and PDBs.
# =============================================================================

set -e

NAMESPACE="isa-cloud-production"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  ISA Cloud - Production Health Check${NC}"
echo -e "${BLUE}  Namespace: ${NAMESPACE}${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if namespace exists
if ! kubectl get namespace ${NAMESPACE} &>/dev/null; then
    echo -e "${RED}Error: Namespace ${NAMESPACE} not found${NC}"
    exit 1
fi

# Check HA service status
check_ha_service() {
    local name=$1
    local label=$2
    local expected_replicas=$3

    local running=$(kubectl get pods -n "$NAMESPACE" -l "$label" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
    local total=$(kubectl get pods -n "$NAMESPACE" -l "$label" --no-headers 2>/dev/null | wc -l | tr -d ' ')

    if [ "$total" -eq 0 ]; then
        echo -e "${RED}[MISSING]${NC} ${name}: No pods found"
    elif [ "$running" -ge "$expected_replicas" ]; then
        echo -e "${GREEN}[OK]${NC} ${name}: ${running}/${total} Running (expected: ${expected_replicas})"
    elif [ "$running" -gt 0 ]; then
        echo -e "${YELLOW}[DEGRADED]${NC} ${name}: ${running}/${total} Running (expected: ${expected_replicas})"
    else
        echo -e "${RED}[DOWN]${NC} ${name}: ${running}/${total} Running (expected: ${expected_replicas})"
    fi
}

# Check Helm release
check_helm_release() {
    local release=$1
    local status=$(helm status "$release" -n "$NAMESPACE" 2>/dev/null | grep STATUS | awk '{print $2}')

    if [ "$status" == "deployed" ]; then
        echo -e "     ${GREEN}Helm: deployed${NC}"
    elif [ -n "$status" ]; then
        echo -e "     ${YELLOW}Helm: ${status}${NC}"
    else
        echo -e "     ${RED}Helm: not installed${NC}"
    fi
}

# === etcd Cluster ===
echo -e "${MAGENTA}=== etcd Cluster (3 members) ===${NC}"
check_ha_service "etcd" "app=etcd" 3

# Check etcd cluster health
etcd_pod=$(kubectl get pods -n "$NAMESPACE" -l app=etcd -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$etcd_pod" ]; then
    echo -e "     ${CYAN}Cluster Health:${NC}"
    cluster_health=$(kubectl exec -n "$NAMESPACE" "$etcd_pod" -- etcdctl endpoint health --cluster 2>/dev/null || echo "unable to check")
    if echo "$cluster_health" | grep -q "is healthy"; then
        healthy_count=$(echo "$cluster_health" | grep -c "is healthy" || echo "0")
        echo -e "     ${GREEN}${healthy_count} members healthy${NC}"
    else
        echo -e "     ${RED}Cluster unhealthy: ${cluster_health}${NC}"
    fi
fi

# === PostgreSQL HA ===
echo -e "\n${MAGENTA}=== PostgreSQL HA Cluster (3 replicas) ===${NC}"
check_ha_service "PostgreSQL" "app.kubernetes.io/name=postgresql-ha" 3
check_helm_release "postgresql"

# Check primary
pg_primary=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=postgresql-ha,role=primary" --no-headers 2>/dev/null | head -1 | awk '{print $1}')
if [ -n "$pg_primary" ]; then
    echo -e "     ${GREEN}Primary: ${pg_primary}${NC}"
else
    echo -e "     ${YELLOW}Primary: not identified${NC}"
fi

# Check replication lag
pg_pods=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=postgresql-ha" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
if [ -n "$pg_pods" ]; then
    echo -e "     ${CYAN}Replication Status:${NC}"
    for pod in $pg_pods; do
        lag=$(kubectl exec -n "$NAMESPACE" "$pod" -- psql -U postgres -t -c "SELECT CASE WHEN pg_is_in_recovery() THEN pg_last_wal_receive_lsn() - pg_last_wal_replay_lsn() ELSE 0 END;" 2>/dev/null | tr -d ' ' || echo "N/A")
        if [ "$lag" == "0" ] || [ "$lag" == "N/A" ]; then
            echo -e "       ${pod}: ${GREEN}in sync${NC}"
        else
            echo -e "       ${pod}: ${YELLOW}lag: ${lag} bytes${NC}"
        fi
    done
fi

# === Redis Cluster ===
echo -e "\n${MAGENTA}=== Redis Cluster (6 nodes) ===${NC}"
check_ha_service "Redis" "app.kubernetes.io/name=redis-cluster" 6
check_helm_release "redis"

# Check cluster state
redis_pod=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=redis-cluster" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$redis_pod" ]; then
    cluster_state=$(kubectl exec -n "$NAMESPACE" "$redis_pod" -- redis-cli cluster info 2>/dev/null | grep cluster_state | cut -d: -f2 | tr -d '\r' || echo "unknown")
    if [ "$cluster_state" == "ok" ]; then
        echo -e "     ${GREEN}Cluster State: ${cluster_state}${NC}"
    else
        echo -e "     ${RED}Cluster State: ${cluster_state}${NC}"
    fi
fi

# === Neo4j Cluster ===
echo -e "\n${MAGENTA}=== Neo4j Cluster (3 cores) ===${NC}"
check_ha_service "Neo4j" "app=neo4j" 3
check_helm_release "neo4j"

# === MinIO Distributed ===
echo -e "\n${MAGENTA}=== MinIO Distributed (4 nodes) ===${NC}"
check_ha_service "MinIO" "app=minio" 4
check_helm_release "minio"

# === NATS JetStream ===
echo -e "\n${MAGENTA}=== NATS JetStream Cluster (3 nodes) ===${NC}"
check_ha_service "NATS" "app.kubernetes.io/name=nats" 3
check_helm_release "nats"

# === Qdrant Distributed ===
echo -e "\n${MAGENTA}=== Qdrant Distributed (3 nodes) ===${NC}"
check_ha_service "Qdrant" "app.kubernetes.io/name=qdrant" 3
check_helm_release "qdrant"

# === EMQX Cluster ===
echo -e "\n${MAGENTA}=== EMQX MQTT Cluster (3 nodes) ===${NC}"
check_ha_service "EMQX" "app.kubernetes.io/name=emqx" 3
check_helm_release "emqx"

# === Consul Cluster ===
echo -e "\n${MAGENTA}=== Consul Server Cluster (3 servers) ===${NC}"
check_ha_service "Consul" "app=consul,component=server" 3
check_helm_release "consul"

# Check leader
consul_pod=$(kubectl get pods -n "$NAMESPACE" -l "app=consul,component=server" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$consul_pod" ]; then
    leader=$(kubectl exec -n "$NAMESPACE" "$consul_pod" -- consul operator raft list-peers 2>/dev/null | grep leader | awk '{print $1}' || echo "unknown")
    if [ -n "$leader" ] && [ "$leader" != "unknown" ]; then
        echo -e "     ${GREEN}Leader: ${leader}${NC}"
    else
        echo -e "     ${YELLOW}Leader: election in progress${NC}"
    fi
fi

# === APISIX ===
echo -e "\n${MAGENTA}=== APISIX Gateway (2 replicas) ===${NC}"
check_ha_service "APISIX" "app.kubernetes.io/name=apisix" 2
check_helm_release "apisix"

# Check route count
apisix_pod=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=apisix" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$apisix_pod" ]; then
    route_count=$(kubectl exec -n "$NAMESPACE" "$apisix_pod" -- \
        curl -s http://localhost:9180/apisix/admin/routes -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" 2>/dev/null | \
        grep -o '"total":[0-9]*' | cut -d: -f2 || echo "0")
    echo -e "     ${CYAN}Routes: ${route_count:-0}${NC}"
fi

# === ML Platform ===
echo -e "\n${MAGENTA}=== ML Platform ===${NC}"

# Ray Cluster
ray_head=$(kubectl get pods -n "$NAMESPACE" -l "ray.io/node-type=head" --no-headers 2>/dev/null | wc -l | tr -d ' ')
ray_workers=$(kubectl get pods -n "$NAMESPACE" -l "ray.io/node-type=worker" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$ray_head" -gt 0 ]; then
    echo -e "${GREEN}[OK]${NC} Ray Cluster: Head running, ${ray_workers} workers"
else
    echo -e "${YELLOW}[NOT DEPLOYED]${NC} Ray Cluster"
fi

# MLflow
mlflow_pods=$(kubectl get pods -n "$NAMESPACE" -l "app=mlflow" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$mlflow_pods" -gt 0 ]; then
    echo -e "${GREEN}[OK]${NC} MLflow: ${mlflow_pods} replicas"
else
    echo -e "${YELLOW}[NOT DEPLOYED]${NC} MLflow"
fi

# JupyterHub
jupyterhub_pods=$(kubectl get pods -n "$NAMESPACE" -l "app=jupyterhub" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$jupyterhub_pods" -gt 0 ]; then
    echo -e "${GREEN}[OK]${NC} JupyterHub: ${jupyterhub_pods} replicas"
else
    echo -e "${YELLOW}[NOT DEPLOYED]${NC} JupyterHub"
fi

# === Pod Disruption Budgets ===
echo -e "\n${MAGENTA}=== Pod Disruption Budgets ===${NC}"
pdbs=$(kubectl get pdb -n "$NAMESPACE" --no-headers 2>/dev/null)
if [ -n "$pdbs" ]; then
    echo "$pdbs" | while read line; do
        name=$(echo "$line" | awk '{print $1}')
        min_avail=$(echo "$line" | awk '{print $2}')
        current=$(echo "$line" | awk '{print $4}')
        available=$(echo "$line" | awk '{print $5}')
        if [ "$available" -ge "$min_avail" ] 2>/dev/null; then
            echo -e "${GREEN}[OK]${NC} ${name}: ${available} available (min: ${min_avail})"
        else
            echo -e "${YELLOW}[WARN]${NC} ${name}: ${available} available (min: ${min_avail})"
        fi
    done
else
    echo -e "${YELLOW}No PDBs configured${NC}"
fi

# === Horizontal Pod Autoscalers ===
echo -e "\n${MAGENTA}=== Horizontal Pod Autoscalers ===${NC}"
hpas=$(kubectl get hpa -n "$NAMESPACE" --no-headers 2>/dev/null)
if [ -n "$hpas" ]; then
    echo "$hpas" | while read line; do
        name=$(echo "$line" | awk '{print $1}')
        min=$(echo "$line" | awk '{print $3}')
        max=$(echo "$line" | awk '{print $4}')
        current=$(echo "$line" | awk '{print $5}')
        echo -e "${GREEN}[OK]${NC} ${name}: ${current} replicas (${min}-${max})"
    done
else
    echo -e "${YELLOW}No HPAs configured${NC}"
fi

# === Summary ===
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Summary${NC}"
echo -e "${BLUE}========================================${NC}"

echo -e "\n${CYAN}Helm Releases:${NC}"
helm list -n ${NAMESPACE} 2>/dev/null | head -15

echo -e "\n${CYAN}PVC Status:${NC}"
kubectl get pvc -n ${NAMESPACE} 2>/dev/null | head -15

echo -e "\n${CYAN}Recent Warning Events:${NC}"
kubectl get events -n ${NAMESPACE} --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | tail -10 || echo "No warning events"

echo ""
echo -e "${GREEN}Production health check complete.${NC}"
