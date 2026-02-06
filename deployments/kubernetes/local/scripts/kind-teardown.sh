#!/bin/bash
set -e

# ============================================
# isA Cloud - kind 集群删除脚本
# ============================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

CLUSTER_NAME="isa-cloud-local"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}isA Cloud - 删除 kind 集群${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查集群是否存在
if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo -e "${YELLOW}集群 ${CLUSTER_NAME} 不存在${NC}"
    exit 0
fi

# 显示集群信息
echo -e "${YELLOW}当前集群信息:${NC}"
kubectl cluster-info --context "kind-${CLUSTER_NAME}" 2>/dev/null || true
echo ""

# 显示运行中的资源
echo -e "${YELLOW}运行中的 Pods:${NC}"
kubectl get pods --all-namespaces --context "kind-${CLUSTER_NAME}" 2>/dev/null || true
echo ""

# 确认删除
echo -e "${RED}警告: 这将删除整个集群及其所有数据!${NC}"
read -p "确认删除集群 ${CLUSTER_NAME}? (yes/no): " -r

if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "已取消"
    exit 0
fi

echo ""
echo -e "${YELLOW}删除集群...${NC}"
kind delete cluster --name "${CLUSTER_NAME}"

echo ""
echo -e "${GREEN}✓ 集群已删除!${NC}"
echo ""

# 清理 Docker 镜像 (可选)
echo -e "${YELLOW}是否同时清理相关 Docker 镜像?${NC}"
echo "这将删除标签为 *:staging 的镜像"
read -p "清理镜像? (yes/no): " -r

if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo ""
    echo -e "${YELLOW}清理镜像...${NC}"
    docker images --format "{{.Repository}}:{{.Tag}}" | grep ":staging$" | xargs -r docker rmi -f || true
    echo -e "${GREEN}✓ 镜像已清理${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}清理完成!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "重新创建集群:"
echo "  ./kind-setup.sh"
echo ""
