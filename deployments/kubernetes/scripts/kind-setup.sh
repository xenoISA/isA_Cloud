#!/bin/bash
set -e

# ============================================
# isA Cloud - kind 集群设置脚本
# ============================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

CLUSTER_NAME="isa-cloud-local"
CONFIG_FILE="../kind-config.yaml"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}isA Cloud - kind 集群设置${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查 kind 是否安装
if ! command -v kind &> /dev/null; then
    echo -e "${RED}错误: kind 未安装${NC}"
    echo ""
    echo "安装方法:"
    echo "  macOS:   brew install kind"
    echo "  Linux:   curl -Lo ./kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64"
    echo "  Windows: choco install kind"
    exit 1
fi

# 检查 Docker 是否运行
if ! docker info &> /dev/null; then
    echo -e "${RED}错误: Docker 未运行${NC}"
    echo "请先启动 Docker Desktop"
    exit 1
fi

# 检查是否已存在集群
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo -e "${YELLOW}集群 ${CLUSTER_NAME} 已存在${NC}"
    read -p "是否删除并重建? (yes/no): " -r
    if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo -e "${YELLOW}删除现有集群...${NC}"
        kind delete cluster --name "${CLUSTER_NAME}"
    else
        echo -e "${GREEN}使用现有集群${NC}"
        exit 0
    fi
fi

# 创建集群
echo -e "${YELLOW}创建 kind 集群...${NC}"
echo "集群名称: ${CLUSTER_NAME}"
echo "配置文件: ${CONFIG_FILE}"
echo ""

if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}错误: 配置文件不存在: ${CONFIG_FILE}${NC}"
    exit 1
fi

kind create cluster --config "${CONFIG_FILE}"

echo ""
echo -e "${GREEN}✓ 集群创建成功!${NC}"
echo ""

# 设置 kubectl 上下文
kubectl cluster-info --context "kind-${CLUSTER_NAME}"

echo ""
echo -e "${YELLOW}验证节点状态...${NC}"
kubectl get nodes

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}设置完成!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "下一步:"
echo "  1. 构建并加载镜像:"
echo "     ./kind-build-load.sh"
echo ""
echo "  2. 部署服务:"
echo "     ./kind-deploy.sh"
echo ""
echo "  3. 查看集群信息:"
echo "     kubectl cluster-info --context kind-${CLUSTER_NAME}"
echo "     kubectl get nodes"
echo ""
echo "  4. 删除集群:"
echo "     ./kind-teardown.sh"
echo ""
