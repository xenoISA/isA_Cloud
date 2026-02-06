#!/bin/bash
set -e

# ============================================
# isA Cloud - kind 部署脚本
# ============================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

CLUSTER_NAME="isa-cloud-local"
NAMESPACE="isa-cloud-local"
OVERLAY_PATH="../overlays/staging"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}isA Cloud - 部署到 kind${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查集群
if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo -e "${RED}错误: 集群 ${CLUSTER_NAME} 不存在${NC}"
    echo "请先运行: ./kind-setup.sh"
    exit 1
fi

# 设置 kubectl 上下文
kubectl config use-context "kind-${CLUSTER_NAME}"

# 部署选项
echo "部署选项:"
echo "  1) 完整部署 (基础设施 + gRPC 服务 + Gateway)"
echo "  2) 仅基础设施"
echo "  3) 仅 gRPC 服务"
echo "  4) 使用 Kustomize overlay (推荐)"
echo ""
read -p "请选择 (1-4): " -r DEPLOY_MODE

case $DEPLOY_MODE in
    1|2|3)
        # 创建 namespace
        echo -e "${YELLOW}创建 namespace...${NC}"
        kubectl apply -f ../base/namespace/namespace.yaml

        if [ "$DEPLOY_MODE" = "1" ] || [ "$DEPLOY_MODE" = "2" ]; then
            echo ""
            echo -e "${YELLOW}部署基础设施服务...${NC}"
            kubectl apply -k ../base/infrastructure/
        fi

        if [ "$DEPLOY_MODE" = "1" ] || [ "$DEPLOY_MODE" = "3" ]; then
            echo ""
            echo -e "${YELLOW}部署 gRPC 服务...${NC}"
            kubectl apply -k ../base/grpc-services/
        fi

        if [ "$DEPLOY_MODE" = "1" ]; then
            echo ""
            echo -e "${YELLOW}部署 Gateway...${NC}"
            kubectl apply -k ../base/gateway/
        fi
        ;;
    4)
        if [ ! -d "$OVERLAY_PATH" ]; then
            echo -e "${RED}错误: Overlay 路径不存在: ${OVERLAY_PATH}${NC}"
            exit 1
        fi

        echo ""
        echo -e "${YELLOW}预览部署资源...${NC}"
        kubectl kustomize "$OVERLAY_PATH" | grep -E '^kind:|^  name:' | paste - - | sed 's/kind: //' | sed 's/  name: / - /'
        echo ""

        read -p "继续部署? (yes/no): " -r
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            echo "已取消"
            exit 0
        fi

        echo ""
        echo -e "${YELLOW}使用 Kustomize 部署...${NC}"
        kubectl apply -k "$OVERLAY_PATH"
        ;;
    *)
        echo -e "${RED}无效选择${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}✓ 部署完成!${NC}"
echo ""

# 等待 Pod 就绪
echo -e "${YELLOW}等待 Pod 就绪...${NC}"
kubectl wait --for=condition=ready pod --all -n "$NAMESPACE" --timeout=5m || true

echo ""
echo -e "${YELLOW}Pod 状态:${NC}"
kubectl get pods -n "$NAMESPACE"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}部署总结${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "访问服务 (已通过 kind 端口映射):"
echo "  Consul UI:        http://localhost:8500"
echo "  MinIO Console:    http://localhost:9001"
echo "  Grafana:          http://localhost:3000"
echo "  Gateway:          http://localhost:8080"
echo ""
echo "或使用端口转发:"
echo "  kubectl port-forward -n $NAMESPACE svc/consul 8500:8500"
echo ""
echo "查看日志:"
echo "  kubectl logs -n $NAMESPACE -l app=consul --tail=100 -f"
echo ""
echo "查看所有资源:"
echo "  kubectl get all -n $NAMESPACE"
echo ""
echo "进入 Pod:"
echo "  kubectl exec -it -n $NAMESPACE <pod-name> -- /bin/sh"
echo ""
