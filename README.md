# isA Cloud - 云原生基础设施平台

<div align="center">

**Kubernetes 基础设施 + 服务网格 + API 网关**

[![Go Version](https://img.shields.io/badge/Go-1.23-00ADD8?logo=go)](https://go.dev/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-1.34-326CE5?logo=kubernetes)](https://kubernetes.io/)
[![Apache APISIX](https://img.shields.io/badge/APISIX-3.x-F04C23?logo=apache)](https://apisix.apache.org/)
[![Consul](https://img.shields.io/badge/Consul-1.21-F24C53?logo=consul)](https://www.consul.io/)
[![ArgoCD](https://img.shields.io/badge/ArgoCD-GitOps-EF7B4D?logo=argo)](https://argoproj.github.io/cd/)

</div>

---

## 📖 目录

- [概述](#概述)
- [架构](#架构)
- [仓库职责](#仓库职责)
- [核心组件](#核心组件)
- [快速开始](#快速开始)
- [服务列表](#服务列表)
- [部署指南](#部署指南)
- [运维管理](#运维管理)
- [文档索引](#文档索引)

---

## 🎯 概述

**isA Cloud** 是 isA 平台的云原生基础设施中心，负责：

### 本仓库提供

✅ **基础设施层**  
  - PostgreSQL, Redis, Neo4j, MinIO, NATS, Mosquitto, Loki, Grafana, Qdrant
  - Consul (服务发现), APISIX (API 网关)

✅ **gRPC 包装服务** (9 个 Go 服务)  
  - 为基础设施提供统一的 gRPC 接口
  - 源码位于 `cmd/` 目录

✅ **GitOps 配置**  
  - Kubernetes 部署配置 (Kustomize)
  - ArgoCD 应用定义
  - 多环境管理 (dev/staging/production)

✅ **CI/CD 流水线**  
  - GitHub Actions 自动构建
  - 镜像推送到 ECR
  - 自动更新部署配置

### 外部业务服务 (其他仓库)

这些服务的**源码在各自仓库**，isA_Cloud 只包含其 **Kubernetes 部署配置**：

- **isA_user** → 27 个用户微服务 (account, auth, session, organization...)
- **isA_Agent** → AI 智能代理服务
- **isA_MCP** → 模型控制协议服务
- **isA_Model** → AI 模型服务
- **isa-data** → 数据服务
- **web-service** → Web 服务

---

## 🏗️ 架构

### 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         外部流量                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
                   ┌───────────────┐
                   │ Apache APISIX │  API 网关 (Port: 9080)
                   │   (Gateway)   │  - 动态路由（自动同步 Consul）
                   └───────┬───────┘  - 认证/授权/限流/CORS
                           │
                           ▼
                   ┌───────────────┐
                   │    Consul     │  服务发现中心
                   │ (注册 42 服务) │  - 健康检查
                   └───────┬───────┘  - KV 存储
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ 基础设施层    │   │ gRPC 服务层  │   │ 业务服务层    │
│ (本仓库部署) │   │ (本仓库源码) │   │ (外部仓库)   │
├──────────────┤   ├──────────────┤   ├──────────────┤
│ PostgreSQL   │   │ postgres-grpc│   │ isA_user     │
│ Redis        │   │ redis-grpc   │   │  ├─ auth     │
│ Neo4j        │   │ neo4j-grpc   │   │  ├─ account  │
│ MinIO        │   │ nats-grpc    │   │  ├─ session  │
│ NATS         │   │ mqtt-grpc    │   │  └─ ... (27) │
│ Mosquitto    │   │ duckdb-grpc  │   │              │
│ Loki         │   │ minio-grpc   │   │ isA_Agent    │
│ Grafana      │   │ loki-grpc    │   │ isA_MCP      │
│ Qdrant       │   │ qdrant-grpc  │   │ isA_Model    │
└──────────────┘   └──────────────┘   │ isa-data     │
                                       │ isa-os  │
                                       └──────────────┘
```

### GitOps 工作流

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 开发者提交代码                                             │
│    ├─ isA_Cloud: 修改 gRPC 服务源码                          │
│    └─ 外部仓库: 修改业务服务源码                              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. CI 流水线 (GitHub Actions)                                │
│    本仓库:                                                   │
│    ├─ 检测变更的 gRPC 服务                                   │
│    ├─ Lint & Test                                           │
│    ├─ 构建 Docker 镜像                                       │
│    ├─ 推送到 ECR                                             │
│    └─ 安全扫描 (Trivy)                                       │
│                                                              │
│    外部仓库:                                                 │
│    ├─ 构建镜像 → ECR                                         │
│    └─ 触发 repository_dispatch → isA_Cloud                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. 更新 GitOps 配置 (自动)                                   │
│    ├─ 本仓库服务: 直接更新 deployment.yaml                   │
│    ├─ 外部服务: CD workflow 更新 deployment.yaml             │
│    └─ Git Commit & Push                                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. ArgoCD 自动同步 (30秒内)                                  │
│    ├─ 检测 Git 变化                                          │
│    ├─ 执行同步计划                                           │
│    └─ 应用到 Kubernetes                                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Kubernetes 滚动更新                                       │
│    ├─ 创建新 Pod                                             │
│    ├─ 健康检查                                               │
│    ├─ 服务自动注册到 Consul                                  │
│    └─ 替换旧 Pod                                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. APISIX 路由同步 (CronJob 每5分钟)                         │
│    ├─ 从 Consul 获取服务列表                                 │
│    ├─ 自动创建/更新路由                                      │
│    └─ 流量路由到新版本 ✅                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 仓库职责

### isA_Cloud (本仓库)

```
isA_Cloud/
├── cmd/                          # gRPC 服务源码 (9个 Go 服务)
│   ├── postgres-service/
│   ├── redis-service/
│   ├── neo4j-service/
│   ├── nats-service/
│   ├── mqtt-service/
│   ├── duckdb-service/
│   ├── minio-service/
│   ├── loki-service/
│   └── qdrant-service/
│
├── deployments/kubernetes/
│   ├── base/
│   │   ├── infrastructure/       # 基础设施部署配置
│   │   │   ├── consul/
│   │   │   ├── apisix/
│   │   │   ├── postgres/
│   │   │   ├── redis/
│   │   │   ├── neo4j/
│   │   │   ├── minio/
│   │   │   ├── nats/
│   │   │   ├── mosquitto/
│   │   │   ├── loki/
│   │   │   ├── grafana/
│   │   │   └── qdrant/
│   │   │
│   │   ├── grpc-services/        # gRPC 服务部署配置
│   │   │   ├── postgres-grpc/
│   │   │   ├── redis-grpc/
│   │   │   └── ...
│   │   │
│   │   └── applications/         # 外部服务部署配置（源码在其他仓库）
│   │       └── kustomization.yaml
│   │
│   └── overlays/                 # 多环境配置
│       ├── dev/
│       ├── staging/
│       └── production/
│
├── argocd/                       # ArgoCD 应用定义
│   ├── bootstrap/
│   └── applications/
│       ├── isa-cloud-dev.yaml
│       ├── isa-cloud-staging.yaml
│       └── isa-cloud-production.yaml
│
├── .github/workflows/            # CI/CD 流水线
│   ├── ci-golang.yaml            # gRPC 服务 CI
│   └── cd-update-images.yaml     # 外部服务镜像更新 CD
│
├── tests/                        # 测试脚本
│   ├── test_auth_via_apisix.sh
│   ├── test_mcp_via_apisix.sh
│   └── ...
│
└── docs/                         # 文档
    ├── cicd.md
    ├── how_to_consul.md
    ├── apisix_route_consul_sync.md
    └── production_deployment_guide.md
```

### 外部仓库

| 仓库 | 服务数量 | 技术栈 | CI/CD |
|------|---------|--------|-------|
| **isA_user** | 27 个用户微服务 | Python/FastAPI | CI 构建 → 通知 isA_Cloud → ArgoCD 部署 |
| **isA_Agent** | 1 个 AI 代理 | Python | 同上 |
| **isA_MCP** | 1 个协议服务 | Python | 同上 |
| **isA_Model** | 1 个模型服务 | Python | 同上 |

---

## 🔧 核心组件

### 1. Apache APISIX (API 网关)

**功能**:
- ✅ 统一流量入口 (Port: 9080)
- ✅ 动态路由（自动同步 Consul 服务）
- ✅ 认证授权 (JWT/Key Auth)
- ✅ 流量控制 (限流/熔断/超时)
- ✅ CORS/安全策略
- ✅ Prometheus 监控

**访问**:
- Gateway: `http://localhost:9080`
- Admin API: `http://localhost:9180`

**文档**: [APISIX 路由同步](./docs/apisix_route_consul_sync.md)

### 2. Consul (服务发现)

**功能**:
- ✅ 服务注册/发现
- ✅ 健康检查 (TCP/HTTP)
- ✅ KV 配置存储
- ✅ DNS 接口

**架构**:
- Server (StatefulSet, 1 副本)
- Agent (Deployment, 1 副本)

**注册服务**: 42 个
- 9 个 gRPC 服务（静态预注册）
- 33 个业务服务（动态注册）

**访问**: `http://localhost:8500`

**文档**: [Consul 完整指南](./docs/how_to_consul.md)

### 3. ArgoCD (GitOps)

**功能**:
- ✅ Git → Kubernetes 自动同步
- ✅ 声明式部署
- ✅ 回滚和审计
- ✅ 多环境管理

**配置**: `argocd/applications/`

**文档**: [CI/CD 流程](./docs/cicd.md)

---

## 🚀 快速开始

### 前置要求

| 工具 | 版本 | 安装 |
|------|------|------|
| **Docker** | 20.10+ | [Docker Desktop](https://www.docker.com/products/docker-desktop) |
| **kubectl** | 1.28+ | `brew install kubectl` |
| **kind** | 0.20+ | `brew install kind` |
| **Go** | 1.23+ | `brew install go` |

### 本地部署 (KIND)

```bash
# 1. 创建 KIND 集群
cd deployments/kubernetes/scripts
./kind-setup.sh

# 2. 构建 gRPC 服务镜像并加载
./kind-build-load.sh

# 3. 部署所有服务
./kind-deploy.sh

# 4. 检查服务状态
./check-services.sh

# 5. 访问服务
# APISIX Gateway
open http://localhost:9080

# Consul UI
open http://localhost:8500
```

### 验证部署

```bash
# 查看 Pod
kubectl get pods -n isa-cloud-staging

# 查看 Consul 注册的服务
kubectl exec -n isa-cloud-staging consul-0 -- consul catalog services

# 查看 APISIX 路由
kubectl exec -n isa-cloud-staging deploy/apisix -- \
  curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq '.list | length'
```

### 测试 API

```bash
# 测试认证服务
./tests/test_auth_via_apisix.sh

# 测试 MCP 服务
./tests/test_mcp_via_apisix.sh

# 或者手动测试
curl http://localhost:9080/api/v1/auth/info
curl http://localhost:9080/api/v1/mcp/health
```

---

## 📋 服务列表

### gRPC 包装服务 (本仓库 `cmd/`)

为基础设施提供统一的 gRPC 接口：

| 服务 | 端口 | 后端 | 功能 |
|------|------|------|------|
| **postgres-grpc** | 50061 | PostgreSQL:5432 | 关系型数据库 gRPC 接口 |
| **redis-grpc** | 50055 | Redis:6379 | 缓存服务 gRPC 接口 |
| **neo4j-grpc** | 50063 | Neo4j:7687 | 图数据库 gRPC 接口 |
| **nats-grpc** | 50056 | NATS:4222 | 消息队列 gRPC 接口 |
| **duckdb-grpc** | 50052 | DuckDB | 分析数据库 gRPC 接口 |
| **mqtt-grpc** | 50053 | Mosquitto:1883 | IoT 消息 gRPC 接口 |
| **loki-grpc** | 50054 | Loki:3100 | 日志聚合 gRPC 接口 |
| **minio-grpc** | 50051 | MinIO:9000 | 对象存储 gRPC 接口 |
| **qdrant-grpc** | 50062 | Qdrant:6333 | 向量数据库 gRPC 接口 |

### 基础设施服务 (本仓库 `deployments/`)

| 服务 | 端口 | 功能 |
|------|------|------|
| **APISIX** | 9080, 9180 | API 网关 |
| **Consul** | 8500, 8600 | 服务发现 |
| **PostgreSQL** | 5432 | 关系型数据库 |
| **Redis** | 6379 | 缓存/会话 |
| **Neo4j** | 7474, 7687 | 图数据库 |
| **MinIO** | 9000, 9001 | 对象存储 |
| **NATS** | 4222, 8222 | 消息队列 |
| **Mosquitto** | 1883, 9001 | MQTT Broker |
| **Loki** | 3100 | 日志聚合 |
| **Grafana** | 3000 | 可视化 |
| **Qdrant** | 6333 | 向量数据库 |

### 业务服务 (外部仓库)

#### isA_user 仓库 (27 个服务)

<details>
<summary><b>展开查看 27 个用户微服务</b></summary>

- **account_service** - 账户管理
- **auth_service** - 认证服务  
- **authorization_service** - 授权服务
- **session_service** - 会话管理
- **organization_service** - 组织管理
- **device_service** - 设备管理
- **location_service** - 位置服务
- **invitation_service** - 邀请管理
- **album_service** - 相册服务
- **memory_service** - 记忆存储
- **media_service** - 媒体处理
- **order_service** - 订单管理
- **product_service** - 产品管理
- **payment_service** - 支付服务
- **billing_service** - 账单服务
- **wallet_service** - 钱包服务
- **notification_service** - 通知服务
- **event_service** - 事件管理
- **calendar_service** - 日历服务
- **task_service** - 任务管理
- **audit_service** - 审计日志
- **telemetry_service** - 遥测数据
- **compliance_service** - 合规检查
- **ota_service** - OTA 更新
- **weather_service** - 天气服务
- **storage_service** - 存储服务
- **vault_service** - 保险箱服务

</details>

#### 其他外部服务

| 服务 | 仓库 | 功能 |
|------|------|------|
| **agent_service** | isA_Agent | AI 智能代理 |
| **mcp_service** | isA_MCP | 模型控制协议 |
| **model_service** | isA_Model | AI 模型服务 |
| **isa-data** | - | 数据服务 |
| **web_service** | - | Web 服务 |

**总计**: 33 个业务服务在 Consul 注册

---

## 📦 部署指南

### 环境

| 环境 | 集群 | 命名空间 | 分支 |
|------|------|---------|------|
| **dev** | KIND 本地 | isa-cloud-dev | develop |
| **staging** | KIND/EKS | isa-cloud-staging | main |
| **production** | EKS/GKE | isa-cloud-production | production |

### 部署到 Staging (EKS)

<details>
<summary><b>点击展开完整步骤</b></summary>

```bash
# 1. 创建 EKS 集群
eksctl create cluster \
  --name isa-cloud-staging \
  --region us-east-1 \
  --nodegroup-name workers \
  --node-type m5.xlarge \
  --nodes 3 \
  --managed

# 2. 配置 kubectl
aws eks update-kubeconfig --name isa-cloud-staging

# 3. 安装 ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f \
  https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 4. 获取 ArgoCD 密码
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d

# 5. 访问 ArgoCD
kubectl port-forward svc/argocd-server -n argocd 8080:443
# 浏览器: https://localhost:8080 (admin / <密码>)

# 6. 部署应用
kubectl apply -f argocd/applications/isa-cloud-staging.yaml

# 7. 查看状态
kubectl get pods -n isa-cloud-staging -w
```

</details>

**详细文档**: [生产部署指南](./docs/production_deployment_guide.md)

---

## 🛠️ 运维管理

### 查看服务

```bash
# 所有 Pod
kubectl get pods -n isa-cloud-staging

# Consul 服务
kubectl exec -n isa-cloud-staging consul-0 -- consul catalog services

# APISIX 路由数量
kubectl exec -n isa-cloud-staging deploy/apisix -- \
  curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq '.list | length'
```

### 查看日志

```bash
# 特定服务
kubectl logs -f -n isa-cloud-staging -l app=postgres-grpc

# Consul
kubectl logs -n isa-cloud-staging consul-0 --tail=100

# APISIX
kubectl logs -n isa-cloud-staging deploy/apisix --tail=100
```

### 扩缩容

```bash
# 手动扩容
kubectl scale deployment postgres-grpc -n isa-cloud-staging --replicas=3

# 自动扩缩容
kubectl autoscale deployment postgres-grpc -n isa-cloud-staging \
  --cpu-percent=80 --min=2 --max=10
```

### 访问 UI

```bash
# Consul UI
kubectl port-forward -n isa-cloud-staging svc/consul-ui 8500:8500
# http://localhost:8500

# Grafana
kubectl port-forward -n isa-cloud-staging svc/grafana 3000:3000
# http://localhost:3000 (admin / admin)
```

---

## 📚 文档索引

### 核心文档
- **[CI/CD 流程](./docs/cicd.md)** - GitHub Actions + ArgoCD 完整流程
- **[Consul 指南](./docs/how_to_consul.md)** - 服务发现、健康检查、运维
- **[APISIX 路由同步](./docs/apisix_route_consul_sync.md)** - 自动路由同步
- **[生产部署](./docs/production_deployment_guide.md)** - EKS/GKE 部署和 HPA

### 测试脚本
- [test_auth_via_apisix.sh](./tests/test_auth_via_apisix.sh)
- [test_mcp_via_apisix.sh](./tests/test_mcp_via_apisix.sh)
- [test_agent_via_apisix.sh](./tests/test_agent_via_apisix.sh)
- [test_storage_via_apisix.sh](./tests/test_storage_via_apisix.sh)

---

## 🤝 贡献

### Commit 规范

```
feat: 新功能
fix: Bug 修复
docs: 文档
refactor: 重构
perf: 性能优化
test: 测试
chore: 构建/工具
```

---

## 📄 许可证

MIT License

---

<div align="center">

**Made with ❤️ by the isA Team**

</div>
