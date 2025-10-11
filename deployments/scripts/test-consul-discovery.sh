#!/bin/bash
# 测试 Consul 服务发现
# Test Consul Service Discovery

set -e

CONSUL_URL="http://localhost:8500"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "测试 Consul 服务发现"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Consul 是否运行
echo "1. 检查 Consul 连接..."
if curl -sf ${CONSUL_URL}/v1/status/leader > /dev/null; then
    echo -e "${GREEN}✓${NC} Consul 运行正常"
else
    echo -e "${RED}✗${NC} Consul 未运行，请先启动: docker-compose -f deployments/compose/with-consul.yml up -d"
    exit 1
fi
echo ""

# 列出所有注册的服务
echo "2. 查询已注册的服务..."
services=$(curl -s ${CONSUL_URL}/v1/agent/services)
echo "$services" | jq -r 'keys[]' | while read service_id; do
    service_info=$(echo "$services" | jq -r ".\"$service_id\"")
    service_name=$(echo "$service_info" | jq -r '.Service')
    address=$(echo "$service_info" | jq -r '.Address')
    port=$(echo "$service_info" | jq -r '.Port')
    tags=$(echo "$service_info" | jq -r '.Tags | join(", ")')
    
    echo -e "${GREEN}✓${NC} $service_name"
    echo "   ID: $service_id"
    echo "   Address: $address:$port"
    echo "   Tags: $tags"
    echo ""
done

# 测试服务发现
echo "=========================================="
echo "3. 测试服务发现功能"
echo "=========================================="
echo ""

test_service_discovery() {
    local service_name=$1
    local expected_port=$2
    
    echo "测试 $service_name..."
    
    # 查询服务
    response=$(curl -s ${CONSUL_URL}/v1/health/service/${service_name})
    
    # 检查是否找到服务
    count=$(echo "$response" | jq '. | length')
    if [ "$count" -eq 0 ]; then
        echo -e "${RED}✗${NC} 未找到 $service_name 服务"
        return 1
    fi
    
    # 提取服务信息
    address=$(echo "$response" | jq -r '.[0].Service.Address')
    port=$(echo "$response" | jq -r '.[0].Service.Port')
    status=$(echo "$response" | jq -r '.[0].Checks[-1].Status')
    
    echo -e "${GREEN}✓${NC} 发现 $service_name"
    echo "   地址: $address:$port"
    echo "   健康状态: $status"
    
    # 验证端口
    if [ "$port" -eq "$expected_port" ]; then
        echo -e "${GREEN}✓${NC} 端口验证通过: $port"
    else
        echo -e "${RED}✗${NC} 端口不匹配，期望: $expected_port, 实际: $port"
        return 1
    fi
    
    # 验证健康状态
    if [ "$status" == "passing" ]; then
        echo -e "${GREEN}✓${NC} 健康检查通过"
    else
        echo -e "${YELLOW}⚠${NC} 健康检查状态: $status"
    fi
    
    echo ""
    return 0
}

# 测试各个服务
failed_tests=0

test_service_discovery "loki-service" 3100 || ((failed_tests++))
test_service_discovery "mqtt-service" 1883 || ((failed_tests++))
test_service_discovery "minio-service" 9000 || ((failed_tests++))

# 测试通过 DNS 发现服务
echo "=========================================="
echo "4. 测试 DNS 服务发现"
echo "=========================================="
echo ""

test_dns_discovery() {
    local service_name=$1
    echo "DNS 查询: $service_name.service.consul"
    
    # 使用 dig 查询 Consul DNS
    if command -v dig &> /dev/null; then
        dig @localhost -p 8600 ${service_name}.service.consul +short
    else
        echo -e "${YELLOW}⚠${NC} dig 未安装，跳过 DNS 测试"
    fi
    echo ""
}

test_dns_discovery "loki-service"
test_dns_discovery "mqtt-service"
test_dns_discovery "minio-service"

# 测试服务连接
echo "=========================================="
echo "5. 测试服务连接"
echo "=========================================="
echo ""

test_service_connection() {
    local service_name=$1
    local health_endpoint=$2
    
    echo "测试 $service_name 连接..."
    
    # 从 Consul 获取服务地址
    response=$(curl -s ${CONSUL_URL}/v1/health/service/${service_name})
    address=$(echo "$response" | jq -r '.[0].Service.Address')
    port=$(echo "$response" | jq -r '.[0].Service.Port')
    
    # 构建完整地址
    if [ "$address" == "loki" ] || [ "$address" == "mosquitto" ] || [ "$address" == "minio" ]; then
        # Docker 内部地址，使用 localhost
        full_url="http://localhost:${port}${health_endpoint}"
    else
        full_url="http://${address}:${port}${health_endpoint}"
    fi
    
    # 测试连接
    if curl -sf "$full_url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $service_name 连接成功: $full_url"
    else
        echo -e "${RED}✗${NC} $service_name 连接失败: $full_url"
        ((failed_tests++))
    fi
    echo ""
}

test_service_connection "loki-service" "/ready"
test_service_connection "minio-service" "/minio/health/live"

# MQTT 需要特殊测试
echo "测试 mqtt-service 连接..."
response=$(curl -s ${CONSUL_URL}/v1/health/service/mqtt-service)
address=$(echo "$response" | jq -r '.[0].Service.Address')
port=$(echo "$response" | jq -r '.[0].Service.Port')
if nc -z localhost $port 2>/dev/null; then
    echo -e "${GREEN}✓${NC} mqtt-service 连接成功: localhost:$port"
else
    echo -e "${RED}✗${NC} mqtt-service 连接失败"
    ((failed_tests++))
fi
echo ""

# 生成 Go 客户端测试代码
echo "=========================================="
echo "6. 生成 SDK 客户端测试代码"
echo "=========================================="
echo ""

cat > /tmp/consul_discovery_test.go << 'EOF'
package main

import (
	"fmt"
	"log"

	"github.com/hashicorp/consul/api"
)

func main() {
	// 创建 Consul 客户端
	config := api.DefaultConfig()
	config.Address = "localhost:8500"
	
	client, err := api.NewClient(config)
	if err != nil {
		log.Fatal(err)
	}

	// 测试服务发现
	services := []string{"loki-service", "mqtt-service", "minio-service"}
	
	fmt.Println("=== Consul 服务发现测试 ===\n")
	
	for _, serviceName := range services {
		// 查询健康的服务实例
		healthServices, _, err := client.Health().Service(serviceName, "", true, nil)
		if err != nil {
			log.Printf("❌ 查询 %s 失败: %v\n", serviceName, err)
			continue
		}
		
		if len(healthServices) == 0 {
			log.Printf("❌ 未找到 %s 服务\n", serviceName)
			continue
		}
		
		// 打印服务信息
		for _, service := range healthServices {
			fmt.Printf("✅ 发现服务: %s\n", serviceName)
			fmt.Printf("   ID: %s\n", service.Service.ID)
			fmt.Printf("   地址: %s:%d\n", service.Service.Address, service.Service.Port)
			fmt.Printf("   标签: %v\n", service.Service.Tags)
			fmt.Println()
		}
	}
}
EOF

echo "Go 测试代码已生成: /tmp/consul_discovery_test.go"
echo ""
echo "运行命令:"
echo "  cd /tmp && go mod init test && go get github.com/hashicorp/consul/api && go run consul_discovery_test.go"
echo ""

# 总结
echo "=========================================="
echo "测试结果总结"
echo "=========================================="
echo ""

if [ $failed_tests -eq 0 ]; then
    echo -e "${GREEN}✓ 所有测试通过！${NC}"
    echo ""
    echo "Consul UI: http://localhost:8500/ui"
    echo "Loki: http://localhost:3100"
    echo "MinIO Console: http://localhost:9001 (minioadmin/minioadmin)"
    echo "MQTT: tcp://localhost:1883"
else
    echo -e "${RED}✗ 有 $failed_tests 个测试失败${NC}"
    exit 1
fi

echo ""
echo "=========================================="

