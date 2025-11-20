# APISIX 路由自动同步文档

## 概述

本文档描述了 Consul 服务发现到 APISIX API Gateway 的自动路由同步机制。该系统通过 Kubernetes CronJob 定期从 Consul 获取服务注册信息，并自动在 APISIX 中创建、更新或删除相应的路由配置。

## 架构设计

### 组件关系

```
┌─────────────┐     注册服务      ┌─────────────┐
│   Services  │ ───────────────> │   Consul    │
│ (Microserv) │                  │  (Registry) │
└─────────────┘                  └─────────────┘
                                        │
                                        │ Catalog API
                                        ▼
                                 ┌─────────────┐
                                 │ Sync Script │
                                 │  (CronJob)  │
                                 └─────────────┘
                                        │
                                        │ Admin API
                                        ▼
                                 ┌─────────────┐
                                 │   APISIX    │
                                 │  (Gateway)  │
                                 └─────────────┘
                                        │
                                        ▼
                                   API Routes
```

### 工作流程

1. **服务注册**: 微服务启动时向 Consul 注册，携带元数据（api_path, auth_required, rate_limit 等）
2. **定期同步**: CronJob 每 5 分钟执行一次同步任务
3. **路由创建**: 根据 Consul 服务元数据在 APISIX 中创建路由
4. **路由清理**: 删除 Consul 中已不存在的服务对应的 APISIX 路由
5. **流量路由**: APISIX 根据路由配置将请求转发到后端服务

## 核心功能

### 1. 自动路由发现

- ✅ 使用 Consul Catalog API 获取全局服务列表
- ✅ 支持多实例服务的负载均衡（roundrobin）
- ✅ 自动使用 Kubernetes DNS 名称作为 upstream

### 2. 路由配置

每个路由包含以下特性：

- **URI 匹配**: 同时支持根路径和通配符路径
  \`\`\`json
  "uris": ["/api/v1/auth", "/api/v1/auth/*"]
  \`\`\`

- **负载均衡**: Round-robin 算法分配流量
- **连接池管理**:
  - Pool size: 320
  - Idle timeout: 60s
  - Max requests: 1000

- **超时配置**:
  - Connect: 6s
  - Send: 6s
  - Read: 10s

### 3. 插件支持

默认启用的插件：

- **CORS**: 跨域资源共享
- **Limit Count**: 速率限制（默认 100 req/min）
- **Request ID**: 请求追踪
- **Prometheus**: 监控指标
- **Proxy Rewrite**: 路径重写（特定服务）
- **JWT Auth**: JWT 认证（可选，基于元数据）

### 4. 路由清理

自动删除 Consul 中不再存在的服务路由，防止配置漂移。

## 文件结构

\`\`\`
isA_Cloud/
├── deployments/
│   ├── kubernetes/
│   │   └── base/
│   │       └── infrastructure/
│   │           └── apisix/
│   │               ├── consul-sync-cronjob.yaml    # CronJob 定义（内联脚本）
│   │               └── ...
│   └── scripts/
│       └── apisix/
│           └── sync_routes_from_consul_k8s.sh      # 独立脚本（可手动执行）
└── docs/
    └── apisix_route_consul_sync.md                 # 本文档
\`\`\`


## 配置说明

### CronJob 配置

**文件**: `deployments/kubernetes/base/infrastructure/apisix/consul-sync-cronjob.yaml`

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: consul-apisix-sync
  namespace: isa-cloud-staging
spec:
  schedule: "*/5 * * * *"  # 每 5 分钟执行一次
  concurrencyPolicy: Forbid  # 禁止并发执行
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
```

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `CONSUL_URL` | `http://consul-agent.isa-cloud-staging.svc.cluster.local:8500` | Consul API 地址 |
| `APISIX_ADMIN_URL` | `http://apisix-gateway.isa-cloud-staging.svc.cluster.local:9180` | APISIX Admin API 地址 |
| `APISIX_ADMIN_KEY` | `edd1c9f034335f136f87ad84b625c8f1` | APISIX Admin API 密钥 |

### 服务元数据

服务在注册到 Consul 时应包含以下元数据：

```python
# Python 示例
consul_client.register_service(
    name="auth_service",
    address="auth.isa-cloud-staging.svc.cluster.local",
    port=8201,
    meta={
        "api_path": "/api/v1/auth",        # 必需：API 路径前缀
        "base_path": "/api/v1/auth",       # 可选：别名
        "auth_required": "false",          # 可选：是否需要 JWT 认证
        "rate_limit": "100"                # 可选：速率限制（请求/分钟）
    }
)
```

#### 元数据字段说明

- **api_path** / **base_path** (必需): API 路径前缀，将用于创建路由
- **auth_required** (可选): `"true"` 启用 JWT 认证，默认 `"false"`
- **rate_limit** (可选): 每分钟最大请求数，默认 `100`

### 特殊路由处理

某些服务需要路径重写（Proxy Rewrite）：

```bash
# MCP 服务示例
# 服务内部路由: /health, /api, etc.
# 外部访问路径: /api/v1/mcp/health, /api/v1/mcp/api
# APISIX 自动将 /api/v1/mcp/* 重写为 /*
```

当前支持的服务：
- `mcp_service`: `/api/v1/mcp/* -> /*`

可在脚本中添加更多服务：

```bash
# 在 sync_routes_from_consul_k8s.sh 中
if [[ "$service_name" == "your_service" ]]; then
    needs_rewrite=true
fi
```

## 部署和使用

### 初次部署

```bash
# 1. 应用 CronJob 配置
kubectl apply -f deployments/kubernetes/base/infrastructure/apisix/consul-sync-cronjob.yaml

# 2. 验证 CronJob 创建成功
kubectl get cronjob consul-apisix-sync -n isa-cloud-staging

# 3. 手动触发首次同步（可选）
kubectl create job -n isa-cloud-staging consul-apisix-sync-manual \
  --from=cronjob/consul-apisix-sync
```

### 查看同步状态

```bash
# 查看 CronJob 状态
kubectl get cronjob consul-apisix-sync -n isa-cloud-staging

# 查看最近的同步任务
kubectl get jobs -n isa-cloud-staging -l app=consul-apisix-sync --sort-by=.metadata.creationTimestamp

# 查看同步日志
kubectl logs -n isa-cloud-staging -l app=consul-apisix-sync --tail=100

# 查看最新一次同步的详细输出
LATEST_JOB=$(kubectl get jobs -n isa-cloud-staging -l app=consul-apisix-sync \
  --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}')
kubectl logs -n isa-cloud-staging job/$LATEST_JOB
```

### 手动执行同步

```bash
# 方式 1: 从 CronJob 创建 Job
kubectl create job -n isa-cloud-staging consul-apisix-sync-manual-$(date +%s) \
  --from=cronjob/consul-apisix-sync

# 方式 2: 使用独立脚本（需要环境变量）
export CONSUL_URL="http://consul-agent.isa-cloud-staging.svc.cluster.local:8500"
export APISIX_ADMIN_URL="http://apisix-gateway.isa-cloud-staging.svc.cluster.local:9180"
export APISIX_ADMIN_KEY="edd1c9f034335f136f87ad84b625c8f1"
bash deployments/scripts/apisix/sync_routes_from_consul_k8s.sh
```

### 验证路由

```bash
# 查看 APISIX 中的所有路由
kubectl exec -n isa-cloud-staging deploy/apisix -- \
  curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq '.list | length'

# 查看特定服务的路由详情
kubectl exec -n isa-cloud-staging deploy/apisix -- \
  curl -s http://localhost:9180/apisix/admin/routes/auth_service_route \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq
```


## 同步日志解读

### 成功同步示例

```
🔄 Starting Consul → APISIX route synchronization (K8s)...

ℹ Syncing route: auth_service_route (/api/v1/auth + /api/v1/auth/* -> auth_service)
  Added upstream: auth.isa-cloud-staging.svc.cluster.local:8201
✓ Route synced: auth_service_route

ℹ Syncing route: mcp_service_route (/api/v1/mcp + /api/v1/mcp/* -> mcp_service)
  Added proxy-rewrite: /api/v1/mcp/* -> /*
  Added upstream: mcp.isa-cloud-staging.svc.cluster.local:8081
✓ Route synced: mcp_service_route

...

🧹 Cleaning up stale routes...

📊 Synchronization Summary
   Synced:  41
   Skipped: 1
   Failed:  0
   Deleted: 0
✨ Sync complete! Total active routes: 41
```

### 日志符号说明

- 🔄 同步开始
- ℹ 信息提示
- ✓ 成功
- ✗ 失败
- ⚠ 警告
- 🧹 清理阶段
- 📊 汇总统计
- ✨ 完成

## 故障排查

### 1. 同步任务失败

**症状**: Job 状态为 Failed 或 Error

**排查步骤**:

```bash
# 查看失败的 Job
kubectl get jobs -n isa-cloud-staging -l app=consul-apisix-sync

# 查看失败原因
kubectl describe job <job-name> -n isa-cloud-staging

# 查看 Pod 日志
kubectl logs -n isa-cloud-staging <pod-name>
```

**常见错误**:

#### Error 1: 脚本语法错误
```
/scripts/sync_routes.sh: line 142: syntax error: unexpected "(" (expecting "}")
```
**原因**: 使用 `/bin/sh` 执行了 bash 脚本（数组等语法不兼容）  
**解决**: 已修复，脚本会先安装 bash 再执行

#### Error 2: Bash 未找到
```
/bin/sh: /bin/bash: not found
```
**原因**: Alpine 镜像默认不包含 bash  
**解决**: 已修复，脚本会自动 `apk add bash`

#### Error 3: HTTP 000 错误
```
✗ Failed to sync route: auth_service_route (HTTP 000)
```
**原因**: 无法连接到 APISIX Admin API  
**排查**:
```bash
# 检查 APISIX Pod 状态
kubectl get pods -n isa-cloud-staging -l app=apisix

# 检查 Service Endpoints
kubectl get endpoints apisix-gateway -n isa-cloud-staging

# 测试 Admin API 连通性
kubectl exec -n isa-cloud-staging deploy/apisix -- \
  curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1"
```

### 2. Consul 连接问题

**症状**: 日志显示 "Failed to connect to Consul"

**排查**:

```bash
# 检查 Consul 服务状态
kubectl get pods -n isa-cloud-staging -l app=consul

# 检查 Consul Service
kubectl get svc consul-agent -n isa-cloud-staging

# 测试 Consul API
kubectl run test-consul --rm -it --image=curlimages/curl:latest \
  --restart=Never -- \
  curl -s http://consul-agent.isa-cloud-staging.svc.cluster.local:8500/v1/catalog/services
```

### 3. 路由未生效

**症状**: 路由同步成功但访问返回 404

**排查**:

```bash
# 1. 确认路由存在
kubectl exec -n isa-cloud-staging deploy/apisix -- \
  curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq '.list[].value.uris'

# 2. 检查 upstream 配置
kubectl exec -n isa-cloud-staging deploy/apisix -- \
  curl -s http://localhost:9180/apisix/admin/routes/auth_service_route \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq '.value.upstream'

# 3. 测试后端服务可达性
kubectl run test-backend --rm -it --image=curlimages/curl:latest \
  --restart=Never -- \
  curl -s http://auth.isa-cloud-staging.svc.cluster.local:8201/health
```

### 4. Kubernetes 集群连接问题

**症状**: `Unable to connect to the server: EOF`

**原因**: Docker 重启后 KIND 集群网络问题

**解决**:

```bash
# 重启 KIND control-plane
docker restart isa-cloud-local-control-plane

# 等待 30 秒后验证
sleep 30
kubectl cluster-info

# 如果仍然失败，重新导出 kubeconfig
kind export kubeconfig --name isa-cloud-local
```

### 5. APISIX 使用 hostNetwork 导致端口冲突

**症状**: APISIX Pod 一直 CrashLoopBackOff，新 Pod 无法调度

**原因**: APISIX 配置了 `hostNetwork: true`，占用了 control-plane 节点的端口

**临时解决**:

```bash
# 停止旧 Pod，让新 Pod 调度
kubectl delete pod <old-apisix-pod> -n isa-cloud-staging --grace-period=10

# 重启 control-plane 容器
docker restart isa-cloud-local-control-plane
```

**长期解决**: 移除 `hostNetwork: true` 配置（如果不需要）


## 监控和告警

### 关键指标

1. **同步成功率**: 观察 `Synced` vs `Failed` 数量
2. **路由总数**: `Total active routes` 应与 Consul 服务数量一致
3. **同步延迟**: CronJob 的 `LAST SCHEDULE` 时间
4. **Pod 重启次数**: APISIX 和同步 Job 的重启次数

### 监控脚本示例

```bash
#!/bin/bash
# monitor-sync.sh

# 获取最新同步任务
LATEST_JOB=$(kubectl get jobs -n isa-cloud-staging -l app=consul-apisix-sync \
  --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}')

# 获取同步统计
LOGS=$(kubectl logs -n isa-cloud-staging job/$LATEST_JOB --tail=10)

# 提取统计数据
SYNCED=$(echo "$LOGS" | grep "Synced:" | awk '{print $2}')
FAILED=$(echo "$LOGS" | grep "Failed:" | awk '{print $2}')
TOTAL=$(echo "$LOGS" | grep "Total active routes:" | awk '{print $5}')

# 检查健康状态
if [ "$FAILED" -gt 0 ]; then
  echo "⚠️ Warning: $FAILED routes failed to sync"
  exit 1
elif [ "$SYNCED" -eq 0 ] && [ "$TOTAL" -eq 0 ]; then
  echo "❌ Error: No routes synced"
  exit 2
else
  echo "✅ OK: $SYNCED routes synced, $TOTAL total routes"
  exit 0
fi
```

## 性能优化

### 调整同步频率

根据服务变更频率调整 CronJob schedule：

```yaml
# 高频变更环境（开发）
schedule: "*/2 * * * *"  # 每 2 分钟

# 中频变更环境（测试）
schedule: "*/5 * * * *"  # 每 5 分钟（默认）

# 低频变更环境（生产）
schedule: "*/15 * * * *"  # 每 15 分钟
```

### 资源限制调整

根据服务数量调整 Job 资源：

```yaml
resources:
  requests:
    cpu: 50m      # 小规模（< 50 服务）
    memory: 64Mi
  limits:
    cpu: 200m     # 中等规模（50-100 服务）
    memory: 128Mi

# 大规模（> 100 服务）
resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 256Mi
```

## 安全建议

### 1. 保护 Admin API Key

**生产环境**应使用 Kubernetes Secret：

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: apisix-admin-key
  namespace: isa-cloud-staging
type: Opaque
stringData:
  admin-key: <your-secure-random-key>
```

在 CronJob 中引用：

```yaml
env:
  - name: APISIX_ADMIN_KEY
    valueFrom:
      secretKeyRef:
        name: apisix-admin-key
        key: admin-key
```

### 2. 网络隔离

确保 Admin API 只在集群内部访问：

```yaml
# APISIX Service 不要暴露 9180 端口到 LoadBalancer
- port: 9180
  targetPort: 9180
  protocol: TCP
  name: admin
  # 不要设置 nodePort
```

### 3. RBAC 配置

为同步 Job 创建专用的 ServiceAccount：

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: consul-apisix-sync
  namespace: isa-cloud-staging
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: consul-apisix-sync
  namespace: isa-cloud-staging
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: consul-apisix-sync
  namespace: isa-cloud-staging
subjects:
  - kind: ServiceAccount
    name: consul-apisix-sync
roleRef:
  kind: Role
  name: consul-apisix-sync
  apiGroup: rbac.authorization.k8s.io
```

## 最佳实践

### 1. 服务注册规范

- ✅ 使用一致的路径前缀（如 `/api/v1/`, `/grpc/`）
- ✅ 为每个服务设置合理的 `rate_limit`
- ✅ 在服务名中使用下划线 `_` 而非连字符 `-`（便于路由命名）
- ✅ 在元数据中包含版本信息（可选）

### 2. 测试流程

新服务上线前：

1. 在 Consul 中注册服务（带完整元数据）
2. 手动触发同步任务
3. 验证路由创建成功
4. 测试路由可访问性
5. 检查日志和监控指标

### 3. 变更管理

- 📝 记录每次重要的路由配置变更
- 🧪 在非生产环境先验证
- 📊 同步后检查统计数据
- 🔍 保留足够的 Job 历史（`successfulJobsHistoryLimit: 3`）

### 4. 灾难恢复

定期备份 APISIX 路由配置：

```bash
# 导出所有路由
kubectl exec -n isa-cloud-staging deploy/apisix -- \
  curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" \
  > apisix-routes-backup-$(date +%Y%m%d).json
```


## 未来改进

### 计划中的功能

- [ ] 支持金丝雀发布（基于权重的路由）
- [ ] 支持蓝绿部署（基于版本的路由切换）
- [ ] 支持更细粒度的认证配置（Key Auth, OAuth2）
- [ ] 支持自定义插件配置（从 Consul 元数据读取）
- [ ] 集成 Prometheus 告警
- [ ] Web UI 展示同步状态
- [ ] 支持多环境配置（dev, staging, prod）

### 扩展方向

- 支持其他服务发现（Eureka, Nacos）
- 支持其他 API Gateway（Kong, Traefik）
- 支持 GitOps 工作流（ArgoCD 集成）

## 参考资料

- [APISIX 官方文档](https://apisix.apache.org/docs/)
- [Consul 服务发现](https://www.consul.io/docs/discovery)
- [Kubernetes CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
- [KIND 本地集群](https://kind.sigs.k8s.io/)

## 附录

### A. 完整的路由配置示例

```json
{
  "name": "auth_service_route",
  "desc": "Auto-synced from Consul service: auth_service",
  "uris": ["/api/v1/auth", "/api/v1/auth/*"],
  "upstream": {
    "type": "roundrobin",
    "nodes": {
      "auth.isa-cloud-staging.svc.cluster.local:8201": 1
    },
    "timeout": {
      "connect": 6,
      "send": 6,
      "read": 10
    },
    "keepalive_pool": {
      "size": 320,
      "idle_timeout": 60,
      "requests": 1000
    },
    "pass_host": "pass"
  },
  "plugins": {
    "cors": {
      "allow_origins": "*",
      "allow_methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD",
      "allow_headers": "DNT,X-CustomHeader,Keep-Alive,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Authorization,X-API-Key,X-Request-ID",
      "expose_headers": "X-Request-ID,X-RateLimit-Limit,X-RateLimit-Remaining,X-RateLimit-Reset",
      "max_age": 86400,
      "allow_credentials": true
    },
    "limit-count": {
      "count": 100,
      "time_window": 60,
      "rejected_code": 429,
      "rejected_msg": "Rate limit exceeded",
      "policy": "local"
    },
    "request-id": {
      "algorithm": "uuid",
      "include_in_response": true
    },
    "prometheus": {}
  },
  "enable_websocket": true,
  "status": 1,
  "labels": {
    "managed_by": "consul-sync-k8s",
    "service_name": "auth_service",
    "sync_timestamp": "2025-11-16T15:50:00Z"
  }
}
```

### B. 环境变量参考

| 变量名 | 用途 | 默认值 |
|--------|------|--------|
| `CONSUL_URL` | Consul HTTP API 地址 | `http://consul-agent.isa-cloud-staging.svc.cluster.local:8500` |
| `APISIX_ADMIN_URL` | APISIX Admin API 地址 | `http://apisix-gateway.isa-cloud-staging.svc.cluster.local:9180` |
| `APISIX_ADMIN_KEY` | APISIX Admin API 密钥 | `edd1c9f034335f136f87ad84b625c8f1` |

### C. Consul 元数据字段完整列表

| 字段 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `api_path` | string | 是 | - | API 路径前缀 |
| `base_path` | string | 否 | - | `api_path` 的别名 |
| `auth_required` | string | 否 | `"false"` | 是否需要 JWT 认证 |
| `rate_limit` | string | 否 | `"100"` | 每分钟请求限制 |
| `version` | string | 否 | - | 服务版本（预留） |
| `weight` | string | 否 | `"1"` | 负载均衡权重（预留） |

---

**文档版本**: v1.0  
**最后更新**: 2025-11-17  
**维护者**: isA Cloud Platform Team
