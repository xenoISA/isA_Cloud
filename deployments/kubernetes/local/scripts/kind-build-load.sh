#!/bin/bash
set -e

# ============================================
# isA Cloud - kind 镜像构建和加载脚本
# ============================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

CLUSTER_NAME="isa-cloud-local"
PROJECT_ROOT="../../.."

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}isA Cloud - 构建并加载镜像${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查集群是否存在
if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo -e "${RED}错误: 集群 ${CLUSTER_NAME} 不存在${NC}"
    echo "请先运行: ./kind-setup.sh"
    exit 1
fi

# 切换到项目根目录
cd "${PROJECT_ROOT}"

# 定义要构建的服务
declare -A SERVICES=(
    # 基础设施服务 (11个)
    ["consul"]="deployments/dockerfiles/Staging/Dockerfile.consul.staging"
    ["redis"]="deployments/dockerfiles/Staging/Dockerfile.redis.staging"
    ["minio"]="deployments/dockerfiles/Staging/Dockerfile.minio.staging"
    ["nats"]="deployments/dockerfiles/Staging/Dockerfile.nats.staging"
    ["mosquitto"]="deployments/dockerfiles/Staging/Dockerfile.mosquitto.staging"
    ["postgres"]="deployments/dockerfiles/Staging/Dockerfile.postgres.staging"
    ["qdrant"]="deployments/dockerfiles/Staging/Dockerfile.qdrant.staging"
    ["neo4j"]="deployments/dockerfiles/Staging/Dockerfile.neo4j.staging"
    ["loki"]="deployments/dockerfiles/Staging/Dockerfile.loki.staging"
    ["grafana"]="deployments/dockerfiles/Staging/Dockerfile.grafana.staging"

    # gRPC 服务 (9个)
    ["minio-service"]="deployments/dockerfiles/Dockerfile.minio-service"
    ["duckdb-service"]="deployments/dockerfiles/Dockerfile.duckdb-service"
    ["mqtt-service"]="deployments/dockerfiles/Dockerfile.mqtt-service"
    ["loki-service"]="deployments/dockerfiles/Dockerfile.loki-service"
    ["redis-service"]="deployments/dockerfiles/Dockerfile.redis-service"
    ["nats-service"]="deployments/dockerfiles/Dockerfile.nats-service"
    ["postgres-service"]="deployments/dockerfiles/Dockerfile.postgres-service"
    ["qdrant-service"]="deployments/dockerfiles/Dockerfile.qdrant-service"
    ["neo4j-service"]="deployments/dockerfiles/Dockerfile.neo4j-service"

    # 网关层 (2个)
    ["openresty"]="deployments/dockerfiles/Staging/Dockerfile.openresty.staging"
    ["gateway"]="deployments/dockerfiles/Dockerfile.gateway"

    # 业务应用层 (4个)
    ["agent"]="isA_Agent/deployment/staging/Dockerfile.staging"
    ["user"]="isA_user/deployment/staging/Dockerfile.staging"
    ["mcp"]="isA_MCP/deployment/staging/Dockerfile.staging"
    ["model"]="isA_Model/deployment/staging/Dockerfile.staging"
)

# 构建模式选择
echo "选择构建模式:"
echo "  1) 全部服务 (26个服务 - 约30-45分钟)"
echo "  2) 仅基础设施 (10个服务 - 约8-12分钟)"
echo "  3) 仅 gRPC 服务 (9个服务 - 约10-15分钟)"
echo "  4) 仅网关层 (2个服务 - 约3-5分钟)"
echo "  5) 仅业务应用 (4个服务 - 约10-15分钟)"
echo "  6) 自定义选择"
echo ""
read -p "请选择 (1-6): " -r BUILD_MODE

BUILD_LIST=()

case $BUILD_MODE in
    1)
        # 全部服务
        BUILD_LIST=("${!SERVICES[@]}")
        ;;
    2)
        # 基础设施层
        BUILD_LIST=("consul" "redis" "minio" "nats" "mosquitto" "postgres" "qdrant" "neo4j" "loki" "grafana")
        ;;
    3)
        # gRPC 服务层
        BUILD_LIST=("minio-service" "duckdb-service" "mqtt-service" "loki-service" "redis-service" "nats-service" "postgres-service" "qdrant-service" "neo4j-service")
        ;;
    4)
        # 网关层
        BUILD_LIST=("openresty" "gateway")
        ;;
    5)
        # 业务应用层
        BUILD_LIST=("agent" "user" "mcp" "model")
        ;;
    6)
        # 自定义
        echo ""
        echo "可用服务:"
        echo ""
        echo "  基础设施 (10): consul, redis, minio, nats, mosquitto, postgres, qdrant, neo4j, loki, grafana"
        echo "  gRPC (9):      minio-service, duckdb-service, mqtt-service, loki-service, redis-service,"
        echo "                 nats-service, postgres-service, qdrant-service, neo4j-service"
        echo "  网关 (2):      openresty, gateway"
        echo "  业务应用 (4):  agent, user, mcp, model"
        echo ""
        read -p "请输入服务名称 (空格分隔): " -a BUILD_LIST
        ;;
    *)
        echo -e "${RED}无效选择${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${YELLOW}将构建以下服务:${NC}"
printf '%s\n' "${BUILD_LIST[@]}"
echo ""
read -p "继续? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "已取消"
    exit 0
fi

# 构建和加载镜像
TOTAL=${#BUILD_LIST[@]}
CURRENT=0
FAILED=()

for service in "${BUILD_LIST[@]}"; do
    CURRENT=$((CURRENT + 1))

    if [ -z "${SERVICES[$service]}" ]; then
        echo -e "${RED}[$CURRENT/$TOTAL] 未知服务: $service${NC}"
        FAILED+=("$service")
        continue
    fi

    DOCKERFILE="${SERVICES[$service]}"
    IMAGE_TAG="${service}:staging"

    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}[$CURRENT/$TOTAL] $service${NC}"
    echo -e "${BLUE}========================================${NC}"

    # 检查 Dockerfile 是否存在
    if [ ! -f "$DOCKERFILE" ]; then
        echo -e "${RED}错误: Dockerfile 不存在: $DOCKERFILE${NC}"
        FAILED+=("$service")
        continue
    fi

    # 构建镜像
    echo -e "${YELLOW}构建镜像: $IMAGE_TAG${NC}"
    if docker build -t "$IMAGE_TAG" -f "$DOCKERFILE" . ; then
        echo -e "${GREEN}✓ 构建成功${NC}"

        # 加载到 kind
        echo -e "${YELLOW}加载到 kind 集群...${NC}"
        if kind load docker-image "$IMAGE_TAG" --name "${CLUSTER_NAME}"; then
            echo -e "${GREEN}✓ 加载成功${NC}"
        else
            echo -e "${RED}✗ 加载失败${NC}"
            FAILED+=("$service")
        fi
    else
        echo -e "${RED}✗ 构建失败${NC}"
        FAILED+=("$service")
    fi
done

# 总结
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}构建总结${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "总计: $TOTAL"
echo "成功: $((TOTAL - ${#FAILED[@]}))"
echo "失败: ${#FAILED[@]}"

if [ ${#FAILED[@]} -gt 0 ]; then
    echo ""
    echo -e "${RED}失败的服务:${NC}"
    printf '%s\n' "${FAILED[@]}"
    exit 1
fi

echo ""
echo -e "${GREEN}所有镜像已成功构建并加载到 kind 集群!${NC}"
echo ""
echo "查看已加载的镜像:"
echo "  docker exec -it ${CLUSTER_NAME}-control-plane crictl images"
echo ""
echo "下一步:"
echo "  ./kind-deploy.sh"
echo ""
