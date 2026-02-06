#!/bin/bash

# Check Services Status Script
# 检查所有服务的健康状态

set -e

NAMESPACE="isa-cloud-local"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}  服务健康检查${NC}"
echo -e "${GREEN}  Namespace: $NAMESPACE${NC}"
echo -e "${GREEN}================================${NC}\n"

# 检查服务是否存在
check_service() {
    local service=$1
    local category=$2

    if kubectl get svc "$service" -n "$NAMESPACE" &>/dev/null; then
        # 获取端口信息
        local ports=$(kubectl get svc "$service" -n "$NAMESPACE" -o jsonpath='{.spec.ports[*].port}')
        local type=$(kubectl get svc "$service" -n "$NAMESPACE" -o jsonpath='{.spec.type}')
        echo -e "${GREEN}✓${NC} ${service} (${type}) - Ports: ${ports}"
    else
        echo -e "${RED}✗${NC} ${service} - 不存在"
    fi
}

# 检查 Pod 状态
check_pods() {
    local app=$1
    local pods=$(kubectl get pods -n "$NAMESPACE" -l "app=$app" --no-headers 2>/dev/null | wc -l | tr -d ' ')
    local running=$(kubectl get pods -n "$NAMESPACE" -l "app=$app" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')

    if [ "$pods" -eq 0 ]; then
        echo -e "  ${YELLOW}Pods: 0/0${NC}"
    elif [ "$running" -eq "$pods" ]; then
        echo -e "  ${GREEN}Pods: $running/$pods Running${NC}"
    else
        echo -e "  ${RED}Pods: $running/$pods Running${NC}"
    fi
}

echo -e "${YELLOW}API Gateway & 管理${NC}"
check_service "apisix-gateway"
check_pods "apisix"
check_service "apisix-dashboard"
check_pods "apisix-dashboard"
check_service "etcd"
check_pods "etcd"

echo -e "\n${YELLOW}核心应用服务${NC}"
check_service "agent"
check_pods "agent"
check_service "model"
check_pods "model"
check_service "mcp"
check_pods "mcp"

echo -e "\n${YELLOW}用户微服务${NC}"
for svc in auth account session authorization audit notification payment wallet storage order task organization invitation vault product billing calendar weather album device ota media memory telemetry event location compliance; do
    check_service "$svc"
    check_pods "$svc"
done

echo -e "\n${YELLOW}基础设施服务${NC}"
check_service "consul"
check_pods "consul"
check_service "consul-ui"
check_service "consul-agent"
check_pods "consul-agent"
check_service "postgres"
check_pods "postgres"
check_service "redis"
check_pods "redis"
check_service "neo4j"
check_pods "neo4j"
check_service "nats"
check_pods "nats"
check_service "mosquitto"
check_pods "mosquitto"
check_service "minio"
check_pods "minio"
check_service "qdrant"
check_pods "qdrant"
check_service "loki"
check_pods "loki"
check_service "grafana"
check_pods "grafana"

echo -e "\n${YELLOW}gRPC 服务${NC}"
for svc in postgres-grpc redis-grpc neo4j-grpc nats-grpc mqtt-grpc minio-grpc qdrant-grpc duckdb-grpc loki-grpc; do
    check_service "$svc"
    check_pods "$svc"
done

echo -e "\n${GREEN}================================${NC}"
echo -e "${GREEN}检查完成${NC}"
echo -e "${GREEN}================================${NC}\n"

# 显示所有 Pod 状态概览
echo -e "${BLUE}Pod 状态概览:${NC}"
kubectl get pods -n "$NAMESPACE" --sort-by=.status.phase

echo -e "\n${BLUE}服务概览:${NC}"
kubectl get svc -n "$NAMESPACE" | head -20
