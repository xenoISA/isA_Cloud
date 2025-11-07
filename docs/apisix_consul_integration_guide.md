# APISIX API 网关 Consul 集成指南

本文档详细说明 isA_Cloud 项目中 APISIX 如何从 Consul 动态获取微服务的服务和路由信息。

---

## 📋 当前架构

### 组件

```
客户端请求
    ↓
APISIX (Port 80, 9080)
    ↓ (Consul 服务发现)
Consul (staging-consul:8500)
    ↓ (健康服务实例)
微服务 (auth_service, etc.)
```

### 已配置组件

1. **APISIX** - Apache APISIX 3.14.1
   - Admin API: http://localhost:9180
   - Gateway: http://localhost:80
   - Dashboard: http://localhost:9010
   - Metrics: http://localhost:9091

2. **etcd** - APISIX 配置存储
   - Port: 2379

3. **Consul** - 服务注册与发现
   - Port: 8500
   - 已在 APISIX 配置中启用

---

## 🚀 当前配置

### APISIX Consul 配置

**文件**: `deployments/configs/staging/apisix/config.yaml`

```yaml
# Consul 服务发现已启用
discovery:
  consul:
    servers:
      - "http://staging-consul:8500"
    fetch_interval: 3                 # 每 3 秒从 Consul 刷新服务
    timeout:
      connect: 2000
      read: 2000
      wait: 60
    keepalive: true
    default_weight: 1
```

✅ **Consul 服务发现已配置并启用**

---

## 🔄 路由同步机制

### 自动同步脚本（推荐）

**脚本**: `deployments/scripts/apisix/sync_routes_from_consul.sh`

#### 工作原理

1. **从 Consul 读取所有服务**
   ```bash
   curl http://localhost:8500/v1/catalog/services
   ```

2. **获取服务 Meta 元数据**
   ```bash
   curl http://localhost:8500/v1/health/service/auth_service?passing=true
   ```

3. **提取路由配置**
   - `meta.api_path` - API 基础路径（如 `/api/v1/auth`）
   - `meta.auth_required` - 是否需要认证
   - `meta.rate_limit` - 速率限制
   - `meta.methods` - 支持的 HTTP 方法

4. **创建/更新 APISIX 路由**
   ```bash
   curl -X PUT http://localhost:9180/apisix/admin/routes/{route_name} \
     -H "X-API-KEY: {admin_key}" \
     -d '{
       "uri": "/api/v1/auth/*",
       "upstream": {
         "service_name": "auth_service",
         "discovery_type": "consul"    # 使用 Consul 发现
       }
     }'
   ```

5. **清理过期路由**
   - 删除不在 Consul 中的服务路由

---

## 📖 使用方法

### 方式 1: 手动同步（一次性）

```bash
cd /Users/xenodennis/Documents/Fun/isA_Cloud

# 运行同步脚本
./deployments/scripts/apisix/sync_routes_from_consul.sh
```

**输出示例**:
```
ℹ 🔄 Starting Consul → APISIX route synchronization...

ℹ Syncing route: auth_service_route (/api/v1/auth/* -> auth_service)
✓ Route synced: auth_service_route

ℹ Syncing route: account_service_route (/api/v1/accounts/* -> account_service)
✓ Route synced: account_service_route

ℹ 📊 Synchronization Summary
   Synced:  2
   Skipped: 8
   Failed:  0
   Deleted: 0

✓ ✨ Sync complete! Total active routes: 2
```

### 方式 2: 定期自动同步（推荐）

使用 `watch` 命令每 10 秒同步一次：

```bash
# 每 10 秒自动同步
watch -n 10 ./deployments/scripts/apisix/sync_routes_from_consul.sh
```

### 方式 3: Cron 定时任务（生产环境）

```bash
# 编辑 crontab
crontab -e

# 添加每分钟同步一次
* * * * * /path/to/isA_Cloud/deployments/scripts/apisix/sync_routes_from_consul.sh >> /var/log/apisix-sync.log 2>&1
```

### 方式 4: Docker Compose Sidecar（最佳实践）

**创建同步服务**: `deployments/compose/Staging/apisix.staging.yml`

```yaml
services:
  # ... 其他服务 ...

  # 路由同步 Sidecar
  apisix-route-sync:
    image: alpine:latest
    container_name: apisix-route-sync
    restart: always
    networks:
      - staging-network
    depends_on:
      - apisix
      - staging-consul
    volumes:
      - ../../../deployments/scripts/apisix:/scripts:ro
    environment:
      - CONSUL_URL=http://staging-consul:8500
      - APISIX_ADMIN_URL=http://apisix:9180
      - APISIX_ADMIN_KEY=edd1c9f034335f136f87ad84b625c8f1
    command: |
      sh -c '
        apk add --no-cache curl jq bash
        while true; do
          echo "[$(date)] Running route sync..."
          /scripts/sync_routes_from_consul.sh
          sleep 30
        done
      '
```

---

## 🎯 验证当前配置

### 1. 确认 auth_service 在 Consul 注册

```bash
python3 -c "
from isa_common.consul_client import ConsulRegistry

consul = ConsulRegistry(consul_host='localhost', consul_port=8500)
instances = consul.discover_service('auth_service')

if instances:
    inst = instances[0]
    meta = inst.get('meta', {})
    print(f'✅ auth_service 已注册')
    print(f'   地址: {inst[\"address\"]}:{inst[\"port\"]}')
    print(f'   API路径: {meta.get(\"base_path\")}')
    print(f'   路由数: {meta.get(\"route_count\")}')
else:
    print('❌ auth_service 未注册')
"
```

### 2. 查看 APISIX 当前路由

```bash
curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq '.list'
```

### 3. 运行同步脚本

```bash
./deployments/scripts/apisix/sync_routes_from_consul.sh
```

### 4. 测试路由

```bash
# 测试健康检查（公开）
curl http://localhost/health

# 测试 auth_service 端点（公开）
curl -X POST http://localhost/api/v1/auth/verify-token \
  -H "Content-Type: application/json" \
  -d '{"token": "test-token"}'

# 测试受保护端点（需要 JWT）
curl http://localhost/api/v1/auth/api-keys/org123 \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## 🔧 路由配置详解

### auth_service 路由示例

当运行同步脚本后，APISIX 会创建以下路由：

```json
{
  "name": "auth_service_route",
  "desc": "Auto-synced from Consul service: auth_service",
  "uri": "/api/v1/auth/*",
  "upstream": {
    "service_name": "auth_service",
    "type": "roundrobin",
    "discovery_type": "consul",      // ✅ 使用 Consul 发现
    "timeout": {
      "connect": 6,
      "send": 6,
      "read": 10
    }
  },
  "plugins": {
    "cors": {...},
    "limit-count": {
      "count": 100,
      "time_window": 60
    },
    "request-id": {...},
    "prometheus": {},
    "jwt-auth": {}                   // ✅ 如果 meta.auth_required = "true"
  },
  "labels": {
    "managed_by": "consul-sync",
    "service_name": "auth_service",
    "sync_timestamp": "2025-11-07T..."
  }
}
```

### 关键特性

1. **Consul 服务发现**
   - `discovery_type: "consul"` - APISIX 自动从 Consul 获取健康实例
   - 支持负载均衡（roundrobin）
   - 自动健康检查

2. **自动认证**
   - 从 `meta.auth_required` 自动配置 JWT 认证
   - 公开路由不添加 JWT 插件

3. **速率限制**
   - 从 `meta.rate_limit` 配置每分钟请求限制
   - 默认 100 req/min

4. **CORS 支持**
   - 自动配置跨域访问
   - 支持所有常用 headers

5. **可观测性**
   - `request-id` - 请求追踪
   - `prometheus` - 监控指标

---

## 📊 监控和调试

### 查看 APISIX 日志

```bash
# 实时查看日志
docker logs -f isa-cloud-apisix-staging

# 查看错误日志
docker exec isa-cloud-apisix-staging tail -100 /usr/local/apisix/logs/error.log
```

### 查看 Consul 连接状态

```bash
# 从 APISIX 容器内部测试 Consul 连接
docker exec isa-cloud-apisix-staging \
  curl -s http://staging-consul:8500/v1/catalog/services | jq
```

### 查看 Prometheus 指标

```bash
curl http://localhost:9091/apisix/prometheus/metrics | grep apisix
```

### APISIX Dashboard

访问: http://localhost:9010

- 用户名: `admin`
- 密码: `admin`

可视化管理：
- 路由配置
- 上游服务
- 插件配置
- 实时监控

---

## 🛠️ 高级配置

### 为特定服务自定义配置

修改 `sync_routes_from_consul.sh`，在创建路由时添加自定义逻辑：

```bash
# 在 create_or_update_route 函数中
if [ "$service_name" = "auth_service" ]; then
    # auth_service 特殊配置
    rate_limit=200  # 更高的速率限制
fi
```

### 添加更多 Meta 字段支持

在服务注册时添加更多元数据：

```python
# microservices/auth_service/routes_registry.py
route_meta = {
    'base_path': '/api/v1/auth',
    'auth_required': 'true',
    'rate_limit': '150',              # ✅ 速率限制
    'timeout_connect': '10',          # ✅ 连接超时
    'timeout_read': '30',             # ✅ 读取超时
    'cors_origins': 'https://app.isa.com',  # ✅ CORS 域名
}
```

更新同步脚本以使用这些字段。

### 多环境配置

```bash
# 开发环境
export CONSUL_URL=http://localhost:8500
export APISIX_ADMIN_URL=http://localhost:9180

# 生产环境
export CONSUL_URL=http://consul.prod.isa.com:8500
export APISIX_ADMIN_URL=http://apisix.prod.isa.com:9180

./sync_routes_from_consul.sh
```

---

## ✅ 验证清单

- [ ] Consul 服务发现已在 APISIX 配置中启用
  ```bash
  docker exec isa-cloud-apisix-staging \
    cat /usr/local/apisix/conf/config.yaml | grep -A 10 "discovery:"
  ```

- [ ] auth_service 已在 Consul 注册
  ```bash
  curl http://localhost:8500/v1/health/service/auth_service?passing=true | jq
  ```

- [ ] 同步脚本运行成功
  ```bash
  ./deployments/scripts/apisix/sync_routes_from_consul.sh
  # 输出: "✓ Route synced: auth_service_route"
  ```

- [ ] 路由已在 APISIX 创建
  ```bash
  curl -s http://localhost:9180/apisix/admin/routes \
    -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | \
    jq '.list[] | select(.value.name == "auth_service_route")'
  ```

- [ ] 可以通过网关访问服务
  ```bash
  curl http://localhost/api/v1/auth/info
  # 应返回 200 OK
  ```

---

## 🚨 故障排查

### 问题 1: 同步脚本报错 "Failed to connect to Consul"

**检查**:
```bash
# 确认 Consul 运行
curl http://localhost:8500/v1/status/leader

# 检查 Docker 网络
docker network inspect staging_staging-network | grep -A 5 staging-consul
```

### 问题 2: APISIX 无法发现 Consul 服务

**检查 APISIX 配置**:
```bash
docker exec isa-cloud-apisix-staging \
  cat /usr/local/apisix/conf/config.yaml | grep -A 10 consul
```

**检查从 APISIX 到 Consul 的连接**:
```bash
docker exec isa-cloud-apisix-staging \
  curl -s http://staging-consul:8500/v1/catalog/services
```

### 问题 3: 路由同步后无法访问

**检查路由配置**:
```bash
curl http://localhost:9180/apisix/admin/routes/auth_service_route \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq
```

**检查 upstream 状态**:
```bash
# 查看 APISIX 日志
docker logs isa-cloud-apisix-staging | grep auth_service
```

### 问题 4: JWT 认证失败

**检查路由插件配置**:
```bash
curl http://localhost:9180/apisix/admin/routes/auth_service_route \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | \
  jq '.value.plugins'
```

**测试不带认证的公开端点**:
```bash
curl http://localhost/health
# 应该返回 200 OK（不需要 JWT）
```

---

## 📚 相关文档

- [APISIX Consul 服务发现文档](https://apisix.apache.org/docs/apisix/discovery/consul/)
- [isA_Cloud Consul 集成指南](./how_to_consul.md)
- [服务迁移指南](../isA_user/docs/service_migration.md)
- [APISIX Admin API 文档](https://apisix.apache.org/docs/apisix/admin-api/)

---

## 🎯 下一步

1. **为其他微服务添加 Consul 注册**
   - 参考 auth_service 的实现
   - 添加完整的路由元数据

2. **配置自动同步**
   - 添加 apisix-route-sync sidecar 到 docker-compose
   - 或配置 cron 定时任务

3. **添加更多路由策略**
   - 基于请求头路由
   - A/B 测试路由
   - 灰度发布

4. **监控和告警**
   - 集成 Prometheus + Grafana
   - 配置路由失败告警
   - 监控服务健康状态

---

*Last Updated: 2025-11-07*
*Author: isA Platform Team*
