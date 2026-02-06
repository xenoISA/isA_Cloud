#!/bin/bash
# =============================================================================
# ISA Platform - Staging Service Health Check Script
# =============================================================================
# Monitors all services in the staging namespace.
# Based on local/scripts/check-services.sh patterns.
# =============================================================================

set -e

NAMESPACE="isa-cloud-staging"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  ISA Cloud - Staging Health Check${NC}"
echo -e "${BLUE}  Namespace: ${NAMESPACE}${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if namespace exists
if ! kubectl get namespace ${NAMESPACE} &>/dev/null; then
    echo -e "${RED}Error: Namespace ${NAMESPACE} not found${NC}"
    exit 1
fi

# Check service existence and get info
check_service() {
    local service=$1

    if kubectl get svc "$service" -n "$NAMESPACE" &>/dev/null; then
        local ports=$(kubectl get svc "$service" -n "$NAMESPACE" -o jsonpath='{.spec.ports[*].port}')
        local type=$(kubectl get svc "$service" -n "$NAMESPACE" -o jsonpath='{.spec.type}')
        echo -e "${GREEN}[OK]${NC} ${service} (${type}) - Ports: ${ports}"
    else
        echo -e "${RED}[MISSING]${NC} ${service}"
    fi
}

# Check pod status for an app label
check_pods() {
    local app=$1
    local pods=$(kubectl get pods -n "$NAMESPACE" -l "app=$app" --no-headers 2>/dev/null | wc -l | tr -d ' ')
    local running=$(kubectl get pods -n "$NAMESPACE" -l "app=$app" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')

    if [ "$pods" -eq 0 ]; then
        echo -e "     ${YELLOW}Pods: 0/0${NC}"
    elif [ "$running" -eq "$pods" ]; then
        echo -e "     ${GREEN}Pods: $running/$pods Running${NC}"
    else
        echo -e "     ${RED}Pods: $running/$pods Running${NC}"
    fi
}

# Check Helm release status
check_helm_release() {
    local release=$1
    local status=$(helm status "$release" -n "$NAMESPACE" 2>/dev/null | grep STATUS | awk '{print $2}')

    if [ "$status" == "deployed" ]; then
        echo -e "${GREEN}[OK]${NC} Helm: ${release} - ${status}"
    elif [ -n "$status" ]; then
        echo -e "${YELLOW}[WARN]${NC} Helm: ${release} - ${status}"
    else
        echo -e "${RED}[MISSING]${NC} Helm: ${release}"
    fi
}

# Check etcd health
check_etcd_health() {
    echo -e "\n${CYAN}etcd Health:${NC}"
    local etcd_pod=$(kubectl get pods -n "$NAMESPACE" -l app=etcd -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -n "$etcd_pod" ]; then
        local health=$(kubectl exec -n "$NAMESPACE" "$etcd_pod" -- etcdctl endpoint health 2>/dev/null || echo "unhealthy")
        if echo "$health" | grep -q "healthy"; then
            echo -e "  ${GREEN}[OK]${NC} etcd cluster healthy"
        else
            echo -e "  ${RED}[ERROR]${NC} etcd cluster unhealthy"
        fi
    else
        echo -e "  ${RED}[MISSING]${NC} etcd pod not found"
    fi
}

# Check APISIX routes
check_apisix_routes() {
    echo -e "\n${CYAN}APISIX Status:${NC}"
    local apisix_pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=apisix -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -n "$apisix_pod" ]; then
        # Try to get route count via admin API
        local route_count=$(kubectl exec -n "$NAMESPACE" "$apisix_pod" -- \
            curl -s http://localhost:9180/apisix/admin/routes -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" 2>/dev/null | \
            grep -o '"total":[0-9]*' | cut -d: -f2 || echo "0")
        echo -e "  ${GREEN}[OK]${NC} Routes configured: ${route_count:-0}"
    else
        echo -e "  ${RED}[MISSING]${NC} APISIX pod not found"
    fi
}

# Check Consul services
check_consul_services() {
    echo -e "\n${CYAN}Consul Status:${NC}"
    local consul_pod=$(kubectl get pods -n "$NAMESPACE" -l app=consul -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -n "$consul_pod" ]; then
        local svc_count=$(kubectl exec -n "$NAMESPACE" "$consul_pod" -- \
            curl -s http://localhost:8500/v1/catalog/services 2>/dev/null | grep -o '"' | wc -l || echo "0")
        svc_count=$((svc_count / 4))  # Rough estimate
        echo -e "  ${GREEN}[OK]${NC} Registered services: ~${svc_count}"
    else
        echo -e "  ${RED}[MISSING]${NC} Consul pod not found"
    fi
}

# === Infrastructure Services ===
echo -e "${YELLOW}Infrastructure Services${NC}"
echo -e "${YELLOW}=======================${NC}"

echo -e "\n${CYAN}API Gateway:${NC}"
check_helm_release "apisix"
check_service "apisix-gateway"
check_pods "apisix"
check_service "apisix-dashboard"

echo -e "\n${CYAN}etcd (APISIX backend):${NC}"
check_service "etcd"
check_pods "etcd"

echo -e "\n${CYAN}Databases:${NC}"
check_helm_release "postgresql"
check_service "postgresql"
check_pods "postgresql"

check_helm_release "redis"
check_service "redis-master"
check_pods "redis"

check_helm_release "neo4j"
check_service "neo4j"
check_pods "neo4j"

echo -e "\n${CYAN}Object Storage:${NC}"
check_helm_release "minio"
check_service "minio"
check_pods "minio"

echo -e "\n${CYAN}Messaging:${NC}"
check_helm_release "nats"
check_service "nats"
check_pods "nats"

check_helm_release "emqx"
check_service "emqx"
check_pods "emqx"

echo -e "\n${CYAN}Vector Database:${NC}"
check_helm_release "qdrant"
check_service "qdrant"
check_pods "qdrant"

echo -e "\n${CYAN}Service Discovery:${NC}"
check_helm_release "consul"
check_service "consul-server"
check_pods "consul"

# === Health Checks ===
check_etcd_health
check_apisix_routes
check_consul_services

# === Summary ===
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Summary${NC}"
echo -e "${BLUE}========================================${NC}"

echo -e "\n${CYAN}Pod Status Overview:${NC}"
kubectl get pods -n ${NAMESPACE} --sort-by=.status.phase 2>/dev/null | head -20

echo -e "\n${CYAN}Resource Usage:${NC}"
kubectl top pods -n ${NAMESPACE} 2>/dev/null | head -10 || echo "Metrics server not available"

echo -e "\n${CYAN}Recent Warning Events:${NC}"
kubectl get events -n ${NAMESPACE} --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | tail -5 || echo "No warning events"

echo ""
echo -e "${GREEN}Health check complete.${NC}"
