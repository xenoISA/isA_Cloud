#!/bin/bash
# 启动 Staging 环境（支持 Consul 服务发现）
# Start Staging Environment with Consul Service Discovery

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "启动 isA Cloud Staging 服务"
echo "=========================================="
echo ""

cd "$DEPLOYMENTS_DIR"

# 检查参数
USE_CONSUL=${1:-false}

if [ "$USE_CONSUL" = "true" ] || [ "$USE_CONSUL" = "--consul" ]; then
    export CONSUL_ENABLED=true
    export CONSUL_HOST=consul
    export CONSUL_PORT=8500
    echo "模式: 启用 Consul 服务发现"
else
    export CONSUL_ENABLED=false
    echo "模式: 直接连接（不使用 Consul）"
fi

echo ""

# 停止现有服务
echo "1. 清理现有服务..."
docker-compose -f compose/base.yml \
    -f compose/infrastructure.yml \
    -f compose/sdk-services.yml \
    down 2>/dev/null || true
echo "✓ 清理完成"
echo ""

# 构建镜像
echo "2. 构建服务镜像..."
docker-compose -f compose/base.yml -f compose/sdk-services.yml build
echo "✓ 镜像构建完成"
echo ""

# 启动服务
echo "3. 启动服务..."

if [ "$CONSUL_ENABLED" = "true" ]; then
    # 先启动 Consul
    echo "   - 启动 Consul..."
    docker-compose -f compose/base.yml -f compose/infrastructure.yml up -d consul
    
    # 等待 Consul 就绪
    echo "   - 等待 Consul 就绪..."
    sleep 5
    
    # 启动 SDK 服务
    echo "   - 启动 SDK 服务（注册到 Consul）..."
    docker-compose -f compose/base.yml -f compose/sdk-services.yml up -d
else
    # 直接启动服务
    docker-compose -f compose/base.yml -f compose/sdk-services.yml up -d
fi

echo "✓ 服务启动完成"
echo ""

# 等待服务就绪
echo "4. 等待服务就绪..."
sleep 10

# 检查服务状态
echo ""
echo "5. 检查服务状态..."
docker-compose -f compose/base.yml -f compose/sdk-services.yml ps

echo ""
echo "=========================================="
echo "✓ Staging 环境启动成功！"
echo "=========================================="
echo ""

if [ "$CONSUL_ENABLED" = "true" ]; then
    echo "Consul 已启用:"
    echo "  Consul UI:  http://localhost:8500/ui"
    echo "  查看服务:   curl http://localhost:8500/v1/agent/services | jq"
    echo ""
fi

echo "服务访问:"
echo "  Loki API:      http://localhost:3100"
echo "  Loki Ready:    http://localhost:3100/ready"
echo "  MinIO API:     http://localhost:9000"
echo "  MinIO Console: http://localhost:9001 (minioadmin/minioadmin)"
echo "  MQTT Broker:   tcp://localhost:1883"
echo "  MQTT WS:       ws://localhost:9001"
echo ""

if [ "$CONSUL_ENABLED" = "true" ]; then
    echo "测试服务发现:"
    echo "  ./scripts/test-consul-discovery.sh"
    echo ""
fi

echo "查看日志:"
echo "  docker-compose -f compose/base.yml -f compose/sdk-services.yml logs -f"
echo ""

echo "停止服务:"
echo "  docker-compose -f compose/base.yml -f compose/sdk-services.yml down"
echo ""

