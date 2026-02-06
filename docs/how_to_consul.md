# Consul 服务发现与注册中心完整指南

## 目录

- [概述](#概述)
- [架构设计](#架构设计)
- [部署组件](#部署组件)
- [服务注册](#服务注册)
- [配置详解](#配置详解)
- [运维管理](#运维管理)
- [故障排查](#故障排查)
- [最佳实践](#最佳实践)

## 概述

Consul 是 HashiCorp 开发的分布式服务网格解决方案，在 isA Cloud 平台中作为核心的服务发现和配置中心。

### 当前部署概况

**集群信息**:
- **Datacenter**: staging
- **Consul 版本**: 1.21.5
- **部署模式**: Server + Client Agent 混合模式
- **注册服务数**: 42 个服务
- **健康检查**: TCP/HTTP 自动健康检查

### Helm 部署的 Service 名称（现行）

- **Server**: `consul-server`（Headless Service，无 ClusterIP）
- **UI/API**: `consul-ui`（ClusterIP/NodePort，`port 80` → `targetPort 8500`）
- **DNS**: `consul-dns`

本地环境使用 NodePort 暴露 `consul-ui`，通过 `localhost:8500` 访问 Consul HTTP API。

**组件分布**:
```
┌─────────────────────────────────────────────────────┐
│              Consul 架构 (Kubernetes)                │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────┐                                   │
│  │ Consul Server│  (StatefulSet)                    │
│  │  consul-0    │  - Leader 节点                     │
│  │              │  - 数据持久化 (1Gi PVC)            │
│  │ 10.244.2.7   │  - 端口: 8500, 8600, 8300-8302     │
│  └──────────────┘                                   │
│         │                                            │
│         │ Gossip Protocol (8301)                     │
│         ▼                                            │
│  ┌──────────────┐                                   │
│  │ Consul Agent │  (Deployment)                     │
│  │ Shared Agent │  - Client 模式                     │
│  │              │  - 无持久化 (emptyDir)             │
│  │ 10.244.2.16  │  - 共享服务注册点                  │
│  └──────────────┘                                   │
│         │                                            │
│         │ Service Registration                       │
│         ▼                                            │
│  ┌──────────────────────────────────┐               │
│  │   42 Registered Services         │               │
│  │   - 33 业务服务                   │               │
│  │   - 9 gRPC 基础设施服务          │               │
│  └──────────────────────────────────┘               │
└─────────────────────────────────────────────────────┘
```


## 架构设计

### Consul Server vs Client 的区别

| 特性 | Consul Server | Consul Agent (Client) |
|------|--------------|----------------------|
| **角色** | 数据中心的核心节点，存储数据 | 轻量级代理，转发请求 |
| **数据存储** | 持久化存储集群状态 (Raft) | 不存储持久化数据 |
| **选举** | 参与 Leader 选举 | 不参与选举 |
| **资源需求** | 较高 (256Mi-512Mi) | 较低 (128Mi-512Mi) |
| **部署方式** | StatefulSet (需要稳定网络标识) | Deployment (无状态) |
| **数量建议** | 3-5 个（奇数，生产环境） | 可任意扩展 |
| **服务注册** | 可以注册服务 | 主要用于服务注册 |

### 当前部署架构说明

#### 1. Consul Server (consul-0)

**部署类型**: StatefulSet  
**副本数**: 1 (开发/测试环境)  
**持久化**: 1Gi PVC

**职责**:
- ✅ 集群 Leader (单节点自动成为 Leader)
- ✅ 存储所有服务注册数据
- ✅ 提供 Raft 一致性保证
- ✅ 处理服务查询和健康检查
- ✅ 提供 Web UI (http://consul-ui:8500)

**配置特点**:
```json
{
  "server": true,                 // Server 模式
  "bootstrap_expect": 1,          // 期望 1 个 Server（测试环境）
  "ui_config": { "enabled": true },  // 启用 UI
  "datacenter": "staging"
}
```

**端口说明**:
- `8500`: HTTP API / UI
- `8600`: DNS (TCP/UDP)
- `8300`: Server RPC (Raft)
- `8301`: Serf LAN (Gossip)
- `8302`: Serf WAN (跨数据中心)

#### 2. Consul Agent (consul-agent)

**部署类型**: Deployment  
**副本数**: 1  
**持久化**: emptyDir (无持久化)

**职责**:
- ✅ 作为共享的服务注册点
- ✅ 预注册 9 个 gRPC 基础设施服务
- ✅ 转发请求到 Consul Server
- ✅ 本地健康检查缓存

**配置特点**:
```json
{
  "server": false,                              // Client 模式
  "retry_join": ["consul-0.consul..."],        // 自动加入 Server
  "enable_script_checks": true,                // 允许脚本检查
  "enable_local_script_checks": true           // 本地脚本检查
}
```

**预注册的 gRPC 服务** (grpc-services.json):
1. postgres_grpc_service (50061)
2. redis_grpc_service (50055)
3. neo4j_grpc_service (50063)
4. nats_grpc_service (50056)
5. duckdb_grpc_service (50052)
6. mqtt_grpc_service (50053)
7. loki_grpc_service (50054)
8. minio_grpc_service (50051)
9. qdrant_grpc_service (50062)

### 服务发现流程

```
┌────────────┐
│ 微服务启动  │
└─────┬──────┘
      │
      │ 1. 调用 Consul HTTP API
      ▼
┌────────────────┐
│  Consul Agent  │  共享注册点
│ (consul-agent) │  
└─────┬──────────┘
      │
      │ 2. Gossip Protocol (8301)
      ▼
┌────────────────┐
│ Consul Server  │  数据存储
│   (consul-0)   │  
└─────┬──────────┘
      │
      │ 3. Raft Consensus
      ▼
┌────────────────┐
│  Catalog API   │  服务目录
└────────────────┘
      │
      │ 4. 健康检查
      ▼
┌────────────────┐
│  APISIX Sync   │  路由同步
└────────────────┘
```


## 部署组件

### 文件结构

```
deployments/kubernetes/base/infrastructure/consul/
├── statefulset.yaml          # Consul Server
├── service.yaml              # Headless Service + UI Service
├── configmap.yaml            # Server 配置
├── agent-deployment.yaml     # Consul Agent
├── agent-service.yaml        # Agent Service
└── agent-configmap.yaml      # Agent 配置 + gRPC 服务预注册
```

### Kubernetes 资源清单

#### 1. Consul Server (StatefulSet)

**文件**: `statefulset.yaml`

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: consul
  namespace: isa-cloud-staging
spec:
  serviceName: consul
  replicas: 1
  template:
    spec:
      containers:
      - name: consul
        image: hashicorp/consul:latest
        args:
        - "agent"
        - "-config-file=/consul/config-from-cm/consul.json"
        
        ports:
        - containerPort: 8500  # HTTP/API
        - containerPort: 8600  # DNS
        - containerPort: 8300  # Server RPC
        - containerPort: 8301  # Serf LAN
        
        volumeMounts:
        - name: data           # 持久化数据
          mountPath: /consul/data
        - name: config         # 配置文件
          mountPath: /consul/config-from-cm
        
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 256m
            memory: 512Mi
  
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 1Gi
```

**关键配置**:
- `serviceName: consul`: 为 StatefulSet 提供稳定的网络标识
- `volumeClaimTemplates`: 每个 Pod 自动创建独立 PVC
- `livenessProbe`: `/v1/status/leader` 检查 Leader 状态
- `readinessProbe`: `/v1/status/peers` 检查集群成员

#### 2. Consul Services

**文件**: `service.yaml`

```yaml
# Headless Service (StatefulSet DNS)
apiVersion: v1
kind: Service
metadata:
  name: consul
spec:
  clusterIP: None                    # Headless
  publishNotReadyAddresses: true     # Pod 未就绪时也发布 DNS
  ports:
  - name: http
    port: 8500
  selector:
    app: consul

---
# ClusterIP Service (UI Access)
apiVersion: v1
kind: Service
metadata:
  name: consul-ui
spec:
  type: ClusterIP
  ports:
  - name: http
    port: 8500
  selector:
    app: consul
```

**DNS 解析**:
- `consul-0.consul.isa-cloud-staging.svc.cluster.local` → Server Pod
- `consul-ui.isa-cloud-staging.svc.cluster.local:8500` → UI

#### 3. Consul Agent (Deployment)

**文件**: `agent-deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: consul-agent
  namespace: isa-cloud-staging
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: consul-agent
        image: hashicorp/consul:latest
        command:
        - "consul"
        - "agent"
        - "-config-file=/consul/config/agent-config.json"
        - "-config-file=/consul/config/grpc-services.json"  # 预注册 gRPC 服务
        - "-client=0.0.0.0"
        - "-bind=0.0.0.0"
        
        ports:
        - containerPort: 8500  # HTTP/API
        - containerPort: 8502  # gRPC
        - containerPort: 8600  # DNS
        
        volumeMounts:
        - name: config
          mountPath: /consul/config
        - name: data
          mountPath: /consul/data
      
      volumes:
      - name: config
        configMap:
          name: consul-agent-config
      - name: data
        emptyDir: {}  # 无持久化需求
```

**关键特性**:
- 使用两个配置文件：基础配置 + 服务预注册
- `emptyDir` 存储：无需持久化
- `livenessProbe/readinessProbe`: 使用 `consul members` 检查连接

#### 4. Agent Service

**文件**: `agent-service.yaml`

```yaml
apiVersion: v1
kind: Service
metadata:
  name: consul-agent
  namespace: isa-cloud-staging
spec:
  type: ClusterIP
  ports:
  - name: http
    port: 8500
    targetPort: 8500
  - name: grpc
    port: 8502
    targetPort: 8502
  selector:
    app: consul-agent
```

**用途**:
- 为微服务提供统一的 Consul API 入口
- DNS: `consul-agent.isa-cloud-staging.svc.cluster.local:8500`


## 服务注册

### 注册方式对比

| 方式 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **ConfigMap 静态注册** | 配置简单，容器化友好 | 无法动态更新 | 基础设施服务（gRPC） |
| **Python SDK 动态注册** | 灵活，支持健康检查 | 需要代码集成 | 业务微服务 |
| **Kubernetes Sidecar** | 自动化，无侵入 | 资源开销大 | 大规模部署 |
| **HTTP API 注册** | 通用，语言无关 | 需手动管理 | 第三方服务集成 |

### 方式 1: ConfigMap 静态注册（当前使用）

**适用于**: gRPC 基础设施服务

**文件**: `agent-configmap.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: consul-agent-config
data:
  grpc-services.json: |
    {
      "services": [
        {
          "id": "postgres_grpc_service",
          "name": "postgres_grpc_service",
          "port": 50061,
          "address": "postgres-grpc.isa-cloud-staging.svc.cluster.local",
          "tags": ["v1", "grpc", "infrastructure", "database"],
          "meta": {
            "version": "1.0.0",
            "protocol": "grpc",
            "base_path": "/grpc/postgres"
          },
          "checks": [
            {
              "id": "postgres-grpc-tcp",
              "name": "PostgreSQL gRPC TCP Check",
              "tcp": "postgres-grpc.isa-cloud-staging.svc.cluster.local:50061",
              "interval": "10s",
              "timeout": "3s"
            }
          ]
        }
      ]
    }
```

**字段说明**:
- `id`: 服务唯一标识（建议与 name 相同）
- `name`: 服务名称（用于发现）
- `port`: 服务端口
- `address`: Kubernetes Service DNS 名称
- `tags`: 标签（用于过滤）
- `meta`: 元数据（key-value，用于路由同步等）
  - `base_path` / `api_path`: API 路径前缀（APISIX 使用）
  - `auth_required`: 是否需要认证
  - `rate_limit`: 速率限制
- `checks`: 健康检查配置

**健康检查类型**:
```json
// TCP 检查
{
  "tcp": "host:port",
  "interval": "10s",
  "timeout": "3s"
}

// HTTP 检查
{
  "http": "http://host:port/health",
  "interval": "10s",
  "timeout": "3s",
  "method": "GET"
}

// gRPC 检查
{
  "grpc": "host:port/service",
  "grpc_use_tls": false,
  "interval": "10s"
}
```

### 方式 2: Python SDK 动态注册（业务服务）

**安装依赖**:
```bash
pip install python-consul
```

**示例代码**:
```python
import consul
import os

# 创建 Consul 客户端
consul_client = consul.Consul(
    host=os.getenv('CONSUL_HOST', 'consul-agent.isa-cloud-staging.svc.cluster.local'),
    port=int(os.getenv('CONSUL_PORT', '8500'))
)

# 服务配置
service_name = "auth_service"
service_id = f"{service_name}-{os.getenv('HOSTNAME', 'default')}"
service_address = f"auth.isa-cloud-staging.svc.cluster.local"
service_port = 8201

# 注册服务
consul_client.agent.service.register(
    name=service_name,
    service_id=service_id,
    address=service_address,
    port=service_port,
    tags=["v1", "http", "authentication"],
    meta={
        "api_path": "/api/v1/auth",
        "auth_required": "false",
        "rate_limit": "100",
        "version": "1.0.0"
    },
    check=consul.Check.http(
        url=f"http://{service_address}:{service_port}/health",
        interval="10s",
        timeout="3s",
        deregister="30s"  # 失败 30 秒后自动注销
    )
)

print(f"Service {service_name} registered successfully")

# 优雅退出时注销
import atexit
def deregister_service():
    consul_client.agent.service.deregister(service_id)
    print(f"Service {service_name} deregistered")

atexit.register(deregister_service)
```

**集成到应用**:
```python
# app.py
from fastapi import FastAPI
from consul_client import register_service

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    register_service()

@app.on_event("shutdown")
async def shutdown_event():
    deregister_service()

@app.get("/health")
async def health():
    return {"status": "healthy"}
```

### 方式 3: HTTP API 直接注册

**注册服务**:
```bash
curl -X PUT http://consul-agent.isa-cloud-staging.svc.cluster.local:8500/v1/agent/service/register \
  -H "Content-Type: application/json" \
  -d '{
    "ID": "web_service",
    "Name": "web_service",
    "Port": 8083,
    "Address": "web.isa-cloud-staging.svc.cluster.local",
    "Tags": ["v1", "http", "frontend"],
    "Meta": {
      "api_path": "/api/v1/web",
      "rate_limit": "200"
    },
    "Check": {
      "HTTP": "http://web.isa-cloud-staging.svc.cluster.local:8083/health",
      "Interval": "10s",
      "Timeout": "3s"
    }
  }'
```

**注销服务**:
```bash
curl -X PUT http://consul-agent.isa-cloud-staging.svc.cluster.local:8500/v1/agent/service/deregister/web_service
```


## 配置详解

### Consul Server 配置

**文件**: `configmap.yaml`

```json
{
  "datacenter": "staging",              // 数据中心名称
  "data_dir": "/consul/data",           // 数据目录（持久化）
  "client_addr": "0.0.0.0",             // 客户端监听地址（所有接口）
  "bind_addr": "0.0.0.0",               // 集群通信地址
  
  "ui_config": {
    "enabled": true                     // 启用 Web UI
  },
  
  "server": true,                       // Server 模式
  "bootstrap_expect": 1,                // 期望 Server 数量（测试环境）
  
  "dns_config": {
    "enable_truncate": true,            // DNS 响应过大时截断
    "only_passing": true,               // DNS 只返回健康的服务
    "allow_stale": true,                // 允许从 follower 读取
    "max_stale": "87600h"               // 最大过期时间（10年）
  },
  
  "log_level": "INFO",                  // 日志级别: DEBUG, INFO, WARN, ERROR
  "disable_anonymous_signature": true,  // 禁用匿名签名
  "disable_update_check": true          // 禁用更新检查
}
```

### Consul Agent 配置

**文件**: `agent-configmap.yaml`

```json
{
  "datacenter": "staging",
  "node_name": "k8s-shared-agent",      // 节点名称
  "data_dir": "/consul/data",
  "client_addr": "0.0.0.0",
  "bind_addr": "0.0.0.0",
  
  "retry_join": [
    "consul-0.consul.isa-cloud-staging.svc.cluster.local"  // 自动加入 Server
  ],
  
  "enable_script_checks": true,         // 允许脚本健康检查
  "enable_local_script_checks": true,   // 本地脚本检查
  
  "log_level": "INFO",
  
  "performance": {
    "raft_multiplier": 1                // Raft 性能调优（1=最快，5=最慢）
  },
  
  "telemetry": {
    "prometheus_retention_time": "60s", // Prometheus 指标保留时间
    "disable_hostname": false           // 在指标中包含主机名
  },
  
  "ports": {
    "http": 8500,                       // HTTP API
    "grpc": 8502,                       // gRPC API
    "dns": 8600,                        // DNS
    "serf_lan": 8301,                   // LAN Gossip
    "serf_wan": 8302                    // WAN Gossip
  }
}
```

### 端口详解

| 端口 | 协议 | 用途 | 访问范围 |
|------|------|------|----------|
| 8500 | HTTP | API / UI | 集群内部 |
| 8502 | gRPC | gRPC API (可选) | 集群内部 |
| 8600 | DNS (TCP/UDP) | DNS 查询 | 集群内部 |
| 8300 | TCP | Server RPC (Raft) | Server 之间 |
| 8301 | TCP/UDP | Serf LAN (Gossip) | 所有节点 |
| 8302 | TCP/UDP | Serf WAN (跨 DC) | 跨数据中心 |

### 环境变量配置

微服务中使用的环境变量：

```yaml
env:
  - name: CONSUL_HOST
    value: "consul-agent.isa-cloud-staging.svc.cluster.local"
  - name: CONSUL_PORT
    value: "8500"
  - name: CONSUL_DATACENTER
    value: "staging"
  - name: SERVICE_NAME
    value: "auth_service"
  - name: SERVICE_PORT
    value: "8201"
```


## 运维管理

### 日常操作命令

#### 1. 查看集群状态

```bash
# 查看集群成员
kubectl exec -n isa-cloud-staging consul-0 -- consul members

# 输出示例:
# Node              Address           Status  Type    Build   Protocol  DC
# consul-0          10.244.2.7:8301   alive   server  1.21.5  2         staging
# k8s-shared-agent  10.244.2.16:8301  alive   client  1.21.5  2         staging

# 查看 Leader 信息
kubectl exec -n isa-cloud-staging consul-0 -- consul operator raft list-peers

# 查看详细信息
kubectl exec -n isa-cloud-staging consul-0 -- consul info
```

#### 2. 服务管理

```bash
# 列出所有服务
kubectl exec -n isa-cloud-staging consul-0 -- consul catalog services

# 查看特定服务详情
kubectl exec -n isa-cloud-staging consul-0 -- consul catalog service auth_service

# 查看服务健康状态
kubectl exec -n isa-cloud-staging consul-0 -- consul catalog nodes -service=auth_service

# 查看服务元数据
kubectl exec -n isa-cloud-staging consul-0 -- \
  curl -s http://localhost:8500/v1/catalog/service/auth_service | jq '.[0].ServiceMeta'
```

#### 3. 健康检查

```bash
# 列出所有健康检查
kubectl exec -n isa-cloud-staging consul-agent-xxx -- consul catalog checks

# 查看失败的健康检查
kubectl exec -n isa-cloud-staging consul-0 -- \
  curl -s http://localhost:8500/v1/health/state/critical

# 查看特定服务的健康状态
kubectl exec -n isa-cloud-staging consul-0 -- \
  curl -s http://localhost:8500/v1/health/service/auth_service | jq
```

#### 4. KV 存储操作

```bash
# 写入配置
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul kv put config/app/database "postgresql://..."

# 读取配置
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul kv get config/app/database

# 列出所有 KV
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul kv get -recurse

# 删除 KV
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul kv delete config/app/database
```

### 监控和日志

#### 查看日志

```bash
# Consul Server 日志
kubectl logs -n isa-cloud-staging consul-0 --tail=100 -f

# Consul Agent 日志
kubectl logs -n isa-cloud-staging -l app=consul-agent --tail=100 -f

# 查看服务注册日志
kubectl logs -n isa-cloud-staging consul-agent-xxx | grep "Synced service"

# 查看健康检查日志
kubectl logs -n isa-cloud-staging consul-agent-xxx | grep "check"
```

#### Prometheus 指标

Consul 暴露 Prometheus 格式的指标：

```bash
# 获取指标
kubectl exec -n isa-cloud-staging consul-0 -- \
  curl -s http://localhost:8500/v1/agent/metrics?format=prometheus

# 关键指标:
# consul_raft_leader - Leader 状态
# consul_raft_state_candidate - 候选者数量
# consul_serf_member_status - 成员状态
# consul_catalog_service_count - 服务数量
# consul_health_service_query_tag - 健康检查查询
```

### 备份和恢复

#### 备份快照

```bash
# 创建快照
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul snapshot save /tmp/consul-backup-$(date +%Y%m%d).snap

# 下载快照到本地
kubectl cp isa-cloud-staging/consul-0:/tmp/consul-backup-20251117.snap \
  ./consul-backup-20251117.snap

# 自动化备份脚本
cat > backup-consul.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="./consul-backups"
mkdir -p $BACKUP_DIR

kubectl exec -n isa-cloud-staging consul-0 -- \
  consul snapshot save /tmp/backup-$DATE.snap

kubectl cp isa-cloud-staging/consul-0:/tmp/backup-$DATE.snap \
  $BACKUP_DIR/backup-$DATE.snap

kubectl exec -n isa-cloud-staging consul-0 -- \
  rm /tmp/backup-$DATE.snap

echo "Backup saved: $BACKUP_DIR/backup-$DATE.snap"

# 保留最近 7 天的备份
find $BACKUP_DIR -name "backup-*.snap" -mtime +7 -delete
EOF

chmod +x backup-consul.sh

# 定时备份 (cron)
# 0 2 * * * /path/to/backup-consul.sh
```

#### 恢复快照

```bash
# 上传快照到 Pod
kubectl cp ./consul-backup-20251117.snap \
  isa-cloud-staging/consul-0:/tmp/restore.snap

# 恢复快照 (需要停止服务)
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul snapshot restore /tmp/restore.snap

# 验证恢复
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul catalog services
```

### 扩容和升级

#### 扩容 Server 节点（生产环境）

```bash
# 修改 StatefulSet 副本数
kubectl scale statefulset consul -n isa-cloud-staging --replicas=3

# 等待新节点加入
kubectl get pods -n isa-cloud-staging -l app=consul -w

# 验证集群
kubectl exec -n isa-cloud-staging consul-0 -- consul members

# 更新 bootstrap_expect 配置
kubectl edit configmap consul-config -n isa-cloud-staging
# 修改 bootstrap_expect: 3

# 滚动重启
kubectl rollout restart statefulset consul -n isa-cloud-staging
```

#### 升级 Consul 版本

```bash
# 1. 检查当前版本
kubectl exec -n isa-cloud-staging consul-0 -- consul version

# 2. 更新镜像版本
kubectl set image statefulset/consul consul=hashicorp/consul:1.22.0 \
  -n isa-cloud-staging

# 3. 监控滚动更新
kubectl rollout status statefulset/consul -n isa-cloud-staging

# 4. 验证版本
kubectl exec -n isa-cloud-staging consul-0 -- consul version

# 5. 如果有问题，回滚
kubectl rollout undo statefulset/consul -n isa-cloud-staging
```


## 故障排查

### 常见问题和解决方案

#### 1. Agent 无法连接到 Server

**症状**:
```bash
kubectl logs -n isa-cloud-staging consul-agent-xxx
# 输出: [ERROR] agent: failed to sync remote state: No cluster leader
```

**排查步骤**:

```bash
# 1. 检查 Server 状态
kubectl get pods -n isa-cloud-staging -l app=consul

# 2. 检查 Server 日志
kubectl logs -n isa-cloud-staging consul-0 --tail=50

# 3. 检查网络连通性
kubectl exec -n isa-cloud-staging consul-agent-xxx -- \
  ping -c 3 consul-0.consul.isa-cloud-staging.svc.cluster.local

# 4. 检查端口
kubectl exec -n isa-cloud-staging consul-agent-xxx -- \
  nc -zv consul-0.consul.isa-cloud-staging.svc.cluster.local 8301
```

**解决方案**:
```bash
# 重启 Agent
kubectl rollout restart deployment consul-agent -n isa-cloud-staging

# 如果 Server 有问题，重启 Server
kubectl delete pod consul-0 -n isa-cloud-staging
```

#### 2. 服务注册失败

**症状**:
```
Failed to register service: Connection refused
```

**排查**:

```bash
# 1. 检查 Consul Agent 是否运行
kubectl get pods -n isa-cloud-staging -l app=consul-agent

# 2. 测试 API 连通性
kubectl run test-consul --rm -it --image=curlimages/curl:latest \
  --restart=Never -- \
  curl -v http://consul-agent.isa-cloud-staging.svc.cluster.local:8500/v1/status/leader

# 3. 检查 Service
kubectl get svc consul-agent -n isa-cloud-staging
kubectl get endpoints consul-agent -n isa-cloud-staging
```

**解决**:
```bash
# 确保微服务使用正确的 Consul 地址
# 环境变量: CONSUL_HOST=consul-agent.isa-cloud-staging.svc.cluster.local
# 端口: 8500
```

#### 3. 健康检查一直失败

**症状**:
```bash
kubectl exec -n isa-cloud-staging consul-0 -- \
  curl -s http://localhost:8500/v1/health/state/critical

# 输出: service:auth_service 一直 critical
```

**排查**:

```bash
# 1. 查看健康检查配置
kubectl exec -n isa-cloud-staging consul-0 -- \
  curl -s http://localhost:8500/v1/agent/checks | jq

# 2. 手动测试健康检查端点
kubectl run test-health --rm -it --image=curlimages/curl:latest \
  --restart=Never -- \
  curl -v http://auth.isa-cloud-staging.svc.cluster.local:8201/health

# 3. 检查服务 Pod 状态
kubectl get pods -n isa-cloud-staging -l app=auth

# 4. 检查服务日志
kubectl logs -n isa-cloud-staging -l app=auth --tail=100
```

**解决**:
```bash
# 如果健康检查配置错误，更新服务注册
# 注销旧服务
kubectl exec -n isa-cloud-staging consul-agent-xxx -- \
  consul services deregister -id=auth_service

# 重新注册（使用正确的健康检查）
```

#### 4. DNS 解析失败

**症状**:
```bash
nslookup auth_service.service.consul
# Server:  10.96.0.10
# Address: 10.96.0.10#53
# ** server can't find auth_service.service.consul: NXDOMAIN
```

**排查**:

```bash
# 1. 检查 Consul DNS 端口
kubectl exec -n isa-cloud-staging consul-0 -- \
  netstat -tulpn | grep 8600

# 2. 直接查询 Consul DNS
kubectl exec -n isa-cloud-staging consul-0 -- \
  dig @localhost -p 8600 auth_service.service.consul

# 3. 检查服务是否注册
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul catalog services
```

**解决**:
```yaml
# 配置 CoreDNS 转发 Consul 查询
kubectl edit configmap coredns -n kube-system

# 添加:
data:
  Corefile: |
    .:53 {
        # ... 其他配置
        forward .consul 10.106.0.100:8600  # consul-agent ClusterIP
    }
```

#### 5. 数据持久化丢失

**症状**: Server 重启后服务注册数据丢失

**排查**:

```bash
# 1. 检查 PVC
kubectl get pvc -n isa-cloud-staging

# 2. 检查 PV
kubectl get pv | grep consul

# 3. 查看数据目录
kubectl exec -n isa-cloud-staging consul-0 -- ls -lh /consul/data
```

**解决**:
```bash
# 确保 PVC 正常绑定
kubectl describe pvc data-consul-0 -n isa-cloud-staging

# 如果 PV 丢失，从备份恢复
# 见 "备份和恢复" 章节
```

#### 6. Raft 协议异常

**症状**:
```
[ERROR] consul.raft: failed to contact quorum of nodes
```

**排查**:

```bash
# 检查 Raft 状态
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul operator raft list-peers

# 查看 Raft 日志
kubectl logs -n isa-cloud-staging consul-0 | grep raft
```

**解决**:
```bash
# 单节点模式重新初始化
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul operator raft bootstrap

# 多节点模式：移除故障节点
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul operator raft remove-peer -id=<node-id>
```

### 调试技巧

#### 启用 DEBUG 日志

```bash
# 临时启用
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul monitor -log-level=debug

# 永久启用
kubectl edit configmap consul-config -n isa-cloud-staging
# 修改 log_level: "DEBUG"

kubectl rollout restart statefulset consul -n isa-cloud-staging
```

#### 使用 Consul UI

```bash
# 端口转发到本地
kubectl port-forward -n isa-cloud-staging svc/consul-ui 8500:8500

# 浏览器访问: http://localhost:8500
```

**UI 功能**:
- 查看所有服务和节点
- 实时健康检查状态
- KV 存储浏览和编辑
- Intentions (服务网格策略)
- 集群拓扑可视化

#### 抓包分析

```bash
# 在 Pod 中安装 tcpdump
kubectl exec -n isa-cloud-staging consul-0 -it -- /bin/sh
apk add tcpdump

# 抓取 Gossip 协议包
tcpdump -i any -n port 8301 -w /tmp/gossip.pcap

# 下载分析
kubectl cp isa-cloud-staging/consul-0:/tmp/gossip.pcap ./gossip.pcap
```


## 最佳实践

### 1. 生产环境部署建议

#### Server 集群配置

```yaml
# 生产环境: 3 或 5 个 Server（奇数）
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: consul
spec:
  replicas: 3  # 推荐 3 或 5
  template:
    spec:
      # 反亲和性：Server 分散到不同节点
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchExpressions:
              - key: app
                operator: In
                values:
                - consul
            topologyKey: kubernetes.io/hostname
      
      containers:
      - name: consul
        resources:
          requests:
            cpu: 500m      # 生产环境增加资源
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
```

**配置调整**:
```json
{
  "bootstrap_expect": 3,           // 期望 3 个 Server
  "performance": {
    "raft_multiplier": 1           // 最快的 Raft 性能
  },
  "autopilot": {
    "cleanup_dead_servers": true,  // 自动清理死节点
    "last_contact_threshold": "200ms",
    "max_trailing_logs": 250,
    "server_stabilization_time": "10s"
  }
}
```

#### 高可用配置

```yaml
# 使用 PodDisruptionBudget
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: consul-pdb
  namespace: isa-cloud-staging
spec:
  minAvailable: 2  # 至少 2 个 Server 可用
  selector:
    matchLabels:
      app: consul
```

### 2. 服务注册最佳实践

#### 元数据规范

```json
{
  "meta": {
    // 必需字段
    "api_path": "/api/v1/auth",        // API 路径
    "version": "1.0.0",                // 服务版本
    "protocol": "http",                // 协议类型
    
    // 可选字段（用于路由和治理）
    "auth_required": "true",           // 是否需要认证
    "rate_limit": "100",               // 速率限制
    "timeout": "30",                   // 超时时间（秒）
    "weight": "1",                     // 负载均衡权重
    "environment": "staging",          // 环境标识
    "team": "platform",                // 团队归属
    "repository": "github.com/..."     // 代码仓库
  }
}
```

#### 健康检查策略

```json
{
  "checks": [
    // HTTP 健康检查（推荐）
    {
      "id": "http-health",
      "name": "HTTP Health Check",
      "http": "http://service:port/health",
      "interval": "10s",
      "timeout": "3s",
      "deregister_critical_service_after": "30s"  // 失败 30s 后自动注销
    },
    
    // TTL 心跳检查（备用）
    {
      "id": "ttl-heartbeat",
      "name": "TTL Heartbeat",
      "ttl": "30s",
      "deregister_critical_service_after": "90s"
    }
  ]
}
```

**健康检查端点实现**:
```python
from fastapi import FastAPI, Response

app = FastAPI()

@app.get("/health")
async def health_check():
    # 检查依赖项
    try:
        # 检查数据库连接
        db.ping()
        
        # 检查 Redis 连接
        redis.ping()
        
        # 检查其他依赖
        # ...
        
        return {
            "status": "healthy",
            "checks": {
                "database": "ok",
                "redis": "ok"
            }
        }
    except Exception as e:
        return Response(
            content=f'{{"status": "unhealthy", "error": "{str(e)}"}}',
            status_code=503
        )
```

### 3. 安全加固

#### ACL 访问控制

```bash
# 启用 ACL
# configmap.yaml
{
  "acl": {
    "enabled": true,
    "default_policy": "deny",          // 默认拒绝
    "enable_token_persistence": true,
    "tokens": {
      "initial_management": "bootstrap-token"
    }
  }
}

# 创建 token
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul acl token create -description "APISIX Sync Token" \
  -policy-name "read-services"

# 服务注册时使用 token
curl -H "X-Consul-Token: <token>" \
  http://consul-agent:8500/v1/agent/service/register -d '{...}'
```

#### TLS 加密通信

```bash
# 生成 CA 证书
consul tls ca create

# 生成 Server 证书
consul tls cert create -server -dc staging

# 配置 TLS
{
  "verify_incoming": true,
  "verify_outgoing": true,
  "verify_server_hostname": true,
  "ca_file": "/consul/config/ca.pem",
  "cert_file": "/consul/config/server.pem",
  "key_file": "/consul/config/server-key.pem"
}
```

### 4. 性能优化

#### 资源配置建议

| 规模 | Server CPU | Server Mem | Agent CPU | Agent Mem | 存储 |
|------|-----------|-----------|-----------|-----------|------|
| 小型 (< 50 服务) | 200m | 512Mi | 100m | 128Mi | 2Gi |
| 中型 (50-200) | 500m | 1Gi | 200m | 256Mi | 5Gi |
| 大型 (200-1000) | 1000m | 2Gi | 500m | 512Mi | 10Gi |
| 超大型 (> 1000) | 2000m | 4Gi | 1000m | 1Gi | 20Gi |

#### 调优参数

```json
{
  "performance": {
    "raft_multiplier": 1,              // 1-10，越小越快
    "leave_drain_time": "5s",          // 节点离开前的排空时间
    "rpc_hold_timeout": "7s"           // RPC 保持超时
  },
  
  "limits": {
    "http_max_conns_per_client": 200,  // 每客户端最大 HTTP 连接
    "https_handshake_timeout": "5s",
    "rpc_max_conns_per_client": 100,
    "rpc_rate": 100,                   // RPC 速率限制（无限制=-1）
    "kv_max_value_size": 524288        // KV 最大值大小（512KB）
  },
  
  "dns_config": {
    "node_ttl": "0s",                  // 节点 DNS TTL
    "service_ttl": {
      "*": "5s"                        // 服务 DNS TTL
    },
    "udp_answer_limit": 3              // UDP DNS 响应数量限制
  }
}
```

### 5. 监控指标

#### 关键指标

```bash
# 集群健康
consul_autopilot_healthy              # 集群整体健康状态
consul_raft_leader                    # 是否是 Leader (0/1)
consul_raft_state_candidate           # 候选者数量
consul_raft_state_leader              # Leader 数量

# 性能指标
consul_raft_commitTime                # Raft 提交延迟
consul_raft_leader_lastContact        # 与 Leader 最后联系时间
consul_rpc_request_rate               # RPC 请求速率
consul_rpc_query_rate                 # 查询速率

# 服务指标
consul_catalog_service_count          # 服务总数
consul_health_service_query_tag       # 健康检查查询
consul_catalog_service_not_found      # 服务未找到次数
```

#### Prometheus 集成

```yaml
# ServiceMonitor (Prometheus Operator)
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: consul
  namespace: isa-cloud-staging
spec:
  selector:
    matchLabels:
      app: consul
  endpoints:
  - port: http
    path: /v1/agent/metrics
    params:
      format: ['prometheus']
    interval: 30s
```

### 6. 灾难恢复计划

#### 备份策略

```bash
# 每日备份脚本
#!/bin/bash
# daily-backup.sh

DATE=$(date +%Y%m%d)
S3_BUCKET="s3://consul-backups"

# 创建快照
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul snapshot save /tmp/backup-$DATE.snap

# 上传到 S3
kubectl cp isa-cloud-staging/consul-0:/tmp/backup-$DATE.snap \
  /tmp/backup-$DATE.snap
aws s3 cp /tmp/backup-$DATE.snap $S3_BUCKET/

# 保留最近 30 天
aws s3 ls $S3_BUCKET/ | awk '{print $4}' | \
  grep -v "$(date +%Y%m -d '30 days ago')" | \
  xargs -I {} aws s3 rm $S3_BUCKET/{}
```

#### 故障恢复流程

1. **Server 单节点故障**:
   - StatefulSet 自动重建
   - 新 Pod 自动加入集群
   - 数据从 PVC 恢复

2. **Server 多节点故障（丢失 quorum）**:
   ```bash
   # 从备份恢复
   kubectl cp backup-20251117.snap isa-cloud-staging/consul-0:/tmp/
   kubectl exec -n isa-cloud-staging consul-0 -- \
     consul snapshot restore /tmp/backup-20251117.snap
   ```

3. **完全灾难**:
   ```bash
   # 重新部署集群
   kubectl apply -f deployments/kubernetes/base/infrastructure/consul/
   
   # 恢复数据
   # 等待 consul-0 启动
   kubectl wait --for=condition=ready pod/consul-0 -n isa-cloud-staging
   
   # 恢复快照
   kubectl cp backup-latest.snap isa-cloud-staging/consul-0:/tmp/
   kubectl exec -n isa-cloud-staging consul-0 -- \
     consul snapshot restore /tmp/backup-latest.snap
   ```


## 附录

### A. 完整部署示例

#### 部署 Consul 集群

```bash
# 1. 创建 namespace（如果不存在）
kubectl create namespace isa-cloud-staging

# 2. 部署 Consul Server
kubectl apply -f deployments/kubernetes/base/infrastructure/consul/configmap.yaml
kubectl apply -f deployments/kubernetes/base/infrastructure/consul/service.yaml
kubectl apply -f deployments/kubernetes/base/infrastructure/consul/statefulset.yaml

# 3. 等待 Server 就绪
kubectl wait --for=condition=ready pod/consul-0 -n isa-cloud-staging --timeout=300s

# 4. 验证 Server
kubectl exec -n isa-cloud-staging consul-0 -- consul members

# 5. 部署 Consul Agent
kubectl apply -f deployments/kubernetes/base/infrastructure/consul/agent-configmap.yaml
kubectl apply -f deployments/kubernetes/base/infrastructure/consul/agent-service.yaml
kubectl apply -f deployments/kubernetes/base/infrastructure/consul/agent-deployment.yaml

# 6. 等待 Agent 就绪
kubectl wait --for=condition=ready pod -l app=consul-agent -n isa-cloud-staging --timeout=300s

# 7. 验证集群
kubectl exec -n isa-cloud-staging consul-0 -- consul members

# 8. 查看注册的服务
kubectl exec -n isa-cloud-staging consul-0 -- consul catalog services

# 9. 访问 UI（可选）
kubectl port-forward -n isa-cloud-staging svc/consul-ui 8500:8500
# 浏览器访问: http://localhost:8500
```

### B. API 参考

#### 服务注册 API

```bash
# 注册服务
POST /v1/agent/service/register
Content-Type: application/json

{
  "ID": "auth_service-01",
  "Name": "auth_service",
  "Tags": ["v1", "http"],
  "Address": "auth.isa-cloud-staging.svc.cluster.local",
  "Port": 8201,
  "Meta": {
    "api_path": "/api/v1/auth",
    "version": "1.0.0"
  },
  "Check": {
    "HTTP": "http://auth.isa-cloud-staging.svc.cluster.local:8201/health",
    "Interval": "10s",
    "Timeout": "3s"
  }
}

# 注销服务
PUT /v1/agent/service/deregister/:service_id

# 查询服务
GET /v1/catalog/service/:service_name

# 查询健康的服务实例
GET /v1/health/service/:service_name?passing=true
```

#### 健康检查 API

```bash
# 注册健康检查
PUT /v1/agent/check/register
{
  "ID": "service:auth_service",
  "Name": "Auth Service Health",
  "ServiceID": "auth_service",
  "HTTP": "http://...",
  "Interval": "10s"
}

# 更新 TTL 健康检查
PUT /v1/agent/check/pass/:check_id
PUT /v1/agent/check/fail/:check_id
PUT /v1/agent/check/warn/:check_id

# 查询健康检查状态
GET /v1/health/state/:state  # passing, warning, critical, any
```

#### KV 存储 API

```bash
# 写入 KV
PUT /v1/kv/:key
Body: value

# 读取 KV
GET /v1/kv/:key?raw

# 删除 KV
DELETE /v1/kv/:key

# 列出 keys
GET /v1/kv/:prefix?keys

# CAS (Compare-And-Set)
PUT /v1/kv/:key?cas=:modify_index
```

### C. 环境变量参考

#### Consul Server

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `CONSUL_BIND_INTERFACE` | `eth0` | 绑定网络接口 |
| `CONSUL_CLIENT_INTERFACE` | `eth0` | 客户端接口 |
| `CONSUL_DATA_DIR` | `/consul/data` | 数据目录 |
| `CONSUL_UI` | `true` | 启用 UI |
| `CONSUL_BOOTSTRAP_EXPECT` | `1` | 期望 Server 数量 |

#### Consul Agent

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `CONSUL_HTTP_ADDR` | `consul-agent:8500` | Consul HTTP API 地址 |
| `CONSUL_GRPC_ADDR` | `consul-agent:8502` | Consul gRPC API 地址 |
| `CONSUL_HTTP_TOKEN` | - | ACL Token |

#### 微服务集成

| 变量名 | 示例值 | 说明 |
|--------|--------|------|
| `CONSUL_HOST` | `consul-agent.isa-cloud-staging.svc.cluster.local` | Consul 地址 |
| `CONSUL_PORT` | `8500` | Consul 端口 |
| `CONSUL_DATACENTER` | `staging` | 数据中心名 |
| `SERVICE_NAME` | `auth_service` | 服务名称 |
| `SERVICE_PORT` | `8201` | 服务端口 |
| `SERVICE_TAGS` | `v1,http` | 服务标签（逗号分隔） |

### D. 常用命令速查

```bash
# 集群管理
consul members                      # 查看成员
consul info                         # 集群信息
consul operator raft list-peers     # Raft 节点

# 服务管理
consul catalog services             # 列出服务
consul catalog nodes                # 列出节点
consul catalog service <name>       # 查看服务

# 健康检查
consul catalog checks               # 所有检查
consul health service <name>        # 服务健康状态
consul health state critical        # 失败的检查

# KV 存储
consul kv put <key> <value>         # 写入
consul kv get <key>                 # 读取
consul kv delete <key>              # 删除
consul kv get -recurse              # 递归读取

# 快照
consul snapshot save backup.snap    # 备份
consul snapshot restore backup.snap # 恢复
consul snapshot inspect backup.snap # 检查快照

# 监控
consul monitor                      # 实时日志
consul monitor -log-level=debug     # Debug 日志
```

### E. 故障排查清单

- [ ] Consul Server Pod 状态正常？
- [ ] Consul Agent Pod 状态正常？
- [ ] `consul members` 显示所有节点？
- [ ] Leader 选举成功？
- [ ] 网络连通性正常（ping, nc）？
- [ ] DNS 解析正常？
- [ ] 服务已注册到 Consul？
- [ ] 健康检查通过？
- [ ] PVC 正常挂载？
- [ ] ConfigMap 配置正确？
- [ ] 资源限制充足（CPU, Memory）？
- [ ] 日志中无 ERROR？

### F. 相关资源

**官方文档**:
- [Consul 官方文档](https://www.consul.io/docs)
- [Consul on Kubernetes](https://www.consul.io/docs/k8s)
- [Service Mesh](https://www.consul.io/docs/connect)

**社区资源**:
- [Consul GitHub](https://github.com/hashicorp/consul)
- [Consul学习指南](https://learn.hashicorp.com/consul)
- [Consul最佳实践](https://www.consul.io/docs/install/performance)

**相关项目**:
- [Consul Template](https://github.com/hashicorp/consul-template)
- [Envconsul](https://github.com/hashicorp/envconsul)
- [Vault (配合使用)](https://www.vaultproject.io/)

### G. 当前集群状态快照

**生成时间**: 2025-11-17

**集群信息**:
- Datacenter: staging
- Server 节点数: 1
- Agent 节点数: 1
- 注册服务数: 42
- Consul 版本: 1.21.5

**注册的服务列表**:
```
业务服务 (33):
- account_service, agent_service, album_service
- audit_service, auth_service, authorization_service
- billing_service, calendar_service, compliance_service
- device_service, event_service, invitation_service
- isa-data, location_service, mcp_service
- media_service, memory_service, model_service
- notification_service, order_service, organization_service
- ota_service, payment_service, product_service
- session_service, storage_service, task_service
- telemetry_service, vault_service, wallet_service
- weather_service, web_service

gRPC 基础设施服务 (9):
- postgres_grpc_service, redis_grpc_service
- neo4j_grpc_service, nats_grpc_service
- duckdb_grpc_service, mqtt_grpc_service
- loki_grpc_service, minio_grpc_service
- qdrant_grpc_service
```

---

**文档版本**: v1.0  
**最后更新**: 2025-11-17  
**维护者**: isA Cloud Platform Team  
**反馈**: 如有问题或建议，请提交 Issue
