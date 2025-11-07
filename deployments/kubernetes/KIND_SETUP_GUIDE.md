# 🎯 isA Cloud - kind 本地部署指南

## 📌 概述

本指南说明如何使用 **kind (Kubernetes in Docker)** 在本地部署 isA Cloud 平台的所有服务。

### 为什么选择 kind？

相比 Minikube：
- ✅ **更快的启动速度** - 基于容器，秒级启动
- ✅ **多节点支持** - 轻松创建多节点集群
- ✅ **更接近生产环境** - 与真实 K8s 集群行为一致
- ✅ **本地镜像加载** - 无需推送到远程仓库
- ✅ **资源占用更少** - 共享主机 Docker daemon
- ✅ **CI/CD 友好** - 广泛用于测试流水线

---

## 🚀 快速开始（5 分钟）

### 1️⃣ 安装依赖

```bash
# macOS
brew install kind kubectl

# Linux
# kind
curl -Lo ./kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64
chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/

# Windows
choco install kind kubectl
```

### 2️⃣ 创建集群

```bash
cd deployments/kubernetes/scripts
./kind-setup.sh
```

**配置详情** (kind-config.yaml):
- 1 个控制平面节点 + 2 个工作节点
- 预配置端口映射（8500, 9001, 3000, 8080 等）
- Pod CIDR: 10.244.0.0/16
- Service CIDR: 10.96.0.0/12

### 3️⃣ 构建并加载镜像

```bash
# 选择要构建的服务
./kind-build-load.sh

# 选项:
# 1) 全部服务 - 约 10-15 分钟
# 2) 仅基础设施 - 约 3-5 分钟 (推荐首次使用)
# 3) 仅 gRPC 服务 - 约 5-8 分钟
# 4) 自定义选择
```

### 4️⃣ 部署服务

```bash
./kind-deploy.sh

# 选择部署模式:
# 1) 完整部署
# 2) 仅基础设施 (推荐首次使用)
# 3) 仅 gRPC 服务
# 4) 使用 Kustomize overlay
```

### 5️⃣ 验证部署

```bash
# 查看 Pod 状态
kubectl get pods -n isa-cloud-staging

# 访问 Consul UI
open http://localhost:8500

# 测试 Redis 连接
kubectl exec -it -n isa-cloud-staging \
  $(kubectl get pod -l app=redis -n isa-cloud-staging -o jsonpath='{.items[0].metadata.name}') \
  -- redis-cli ping
```

---

## 📁 目录结构

```
deployments/kubernetes/
├── kind-config.yaml           # kind 集群配置
├── scripts/
│   ├── kind-setup.sh          # 创建 kind 集群
│   ├── kind-build-load.sh     # 构建并加载镜像
│   ├── kind-deploy.sh         # 部署服务
│   └── kind-teardown.sh       # 删除集群和清理
├── base/
│   ├── namespace/             # 命名空间定义
│   ├── infrastructure/        # 基础设施服务 (Consul, Redis, etc.)
│   └── grpc-services/         # gRPC 微服务
├── overlays/
│   ├── staging/               # 本地/staging 环境配置
│   └── production/            # 生产环境配置
├── README.md                  # 总体说明
├── QUICK_START.md            # 详细快速开始指南
└── KIND_SETUP_GUIDE.md       # 本文档
```

---

## 🔧 关键配置说明

### 1. kind-config.yaml

```yaml
name: isa-cloud-local          # 集群名称
nodes:
  - role: control-plane        # 控制平面 + 端口映射
  - role: worker               # 工作节点 1
  - role: worker               # 工作节点 2
```

**端口映射**:
| 服务 | 容器端口 | 主机端口 | 用途 |
|------|----------|----------|------|
| Consul UI | 8500 | 8500 | Web 控制台 |
| Redis | 6379 | 6379 | 数据库 |
| MinIO API | 9000 | 9000 | 对象存储 |
| MinIO Console | 9001 | 9001 | Web 控制台 |
| NATS | 4222 | 4222 | 消息队列 |
| Grafana | 3000 | 3000 | 监控仪表板 |
| Gateway | 8080 | 8080 | API 网关 |

### 2. imagePullPolicy 配置

所有 manifests 使用 `imagePullPolicy: IfNotPresent`:
- 如果本地有镜像，使用本地版本 ✅
- 如果本地没有，从仓库拉取 ✅
- 适合本地开发和云端部署 ✅

**生产环境**可通过 overlay 覆盖为 `Always`。

### 3. 镜像命名规范

```bash
# 基础设施服务
consul:staging
redis:staging
minio:staging
nats:staging
loki:staging

# gRPC 服务
duckdb-service:staging
loki-service:staging
minio-service:staging
mqtt-service:staging
nats-service:staging
redis-service:staging
neo4j-service:staging
postgres-service:staging
qdrant-service:staging

# Gateway
gateway:staging
```

---

## 📊 服务清单

### 基础设施服务 (Infrastructure)

| 服务 | 副本数 | 类型 | 用途 |
|------|--------|------|------|
| Consul | 3 | StatefulSet | 服务发现和配置 |
| Redis | 1 | StatefulSet | 缓存和消息队列 |
| MinIO | 1 | StatefulSet | 对象存储 |
| NATS | 1 | StatefulSet | 消息队列 |
| Loki | 1 | StatefulSet | 日志聚合 |
| Grafana | 1 | Deployment | 监控仪表板 |

### gRPC 微服务 (Services)

| 服务 | 副本数 | 端口 | 依赖 |
|------|--------|------|------|
| redis-service | 2 | 50055 | Redis, Consul |
| duckdb-service | 2 | 50051 | Consul |
| loki-service | 2 | 50052 | Loki, Consul |
| minio-service | 2 | 50053 | MinIO, Consul |
| mqtt-service | 2 | 50054 | Consul |
| nats-service | 2 | 50056 | NATS, Consul |
| neo4j-service | 2 | 50057 | Neo4j, Consul |
| postgres-service | 2 | 50058 | PostgreSQL, Consul |
| qdrant-service | 2 | 50059 | Qdrant, Consul |

### 网关 (Gateway)

| 服务 | 副本数 | 端口 | 用途 |
|------|--------|------|------|
| gateway | 2 | 8080 | Infrastructure Gateway |

---

## 🎯 部署策略建议

### 阶段 1: 基础验证（初次使用）
```bash
# 仅部署 Redis 进行快速验证
./kind-setup.sh
./kind-build-load.sh  # 选择自定义 -> redis
./kind-deploy.sh      # 选择仅基础设施 -> 只应用 Redis

# 验证
kubectl get pods -n isa-cloud-staging
kubectl logs -n isa-cloud-staging -l app=redis
```

### 阶段 2: 基础设施（第一次完整部署）
```bash
./kind-build-load.sh  # 选择 2) 仅基础设施
./kind-deploy.sh      # 选择 2) 仅基础设施

# 等待所有 Pod Running
kubectl get pods -n isa-cloud-staging -w

# 访问 Consul UI 确认服务注册
open http://localhost:8500
```

### 阶段 3: 微服务（功能扩展）
```bash
./kind-build-load.sh  # 选择 3) 仅 gRPC 服务
./kind-deploy.sh      # 选择 3) 仅 gRPC 服务

# 验证服务注册
curl http://localhost:8500/v1/catalog/services
```

### 阶段 4: 完整平台（生产模拟）
```bash
./kind-build-load.sh  # 选择 1) 全部服务
./kind-deploy.sh      # 选择 1) 完整部署

# 监控整体状态
watch kubectl get pods -n isa-cloud-staging
```

---

## 🛠️ 常用操作

### 查看集群信息
```bash
# 集群状态
kubectl cluster-info --context kind-isa-cloud-local

# 节点列表
kubectl get nodes

# 所有资源
kubectl get all -n isa-cloud-staging
```

### 查看日志
```bash
# 特定服务
kubectl logs -n isa-cloud-staging -l app=consul --tail=100 -f

# 所有事件
kubectl get events -n isa-cloud-staging --sort-by='.lastTimestamp'

# Pod 日志
kubectl logs -n isa-cloud-staging <pod-name> -f
```

### 调试 Pod
```bash
# 进入 Pod
kubectl exec -it -n isa-cloud-staging <pod-name> -- /bin/sh

# 查看详细信息
kubectl describe pod <pod-name> -n isa-cloud-staging

# 端口转发（如果端口映射不工作）
kubectl port-forward -n isa-cloud-staging svc/consul 8500:8500
```

### 扩缩容
```bash
# 手动扩容
kubectl scale deployment/redis-grpc -n isa-cloud-staging --replicas=3

# 查看 HPA（如果配置了）
kubectl get hpa -n isa-cloud-staging
```

### 更新镜像
```bash
# 重新构建镜像
docker build -t redis-service:staging -f deployments/dockerfiles/Dockerfile.redis-service .

# 加载到 kind
kind load docker-image redis-service:staging --name isa-cloud-local

# 重启 Deployment
kubectl rollout restart deployment/redis-grpc -n isa-cloud-staging

# 查看滚动更新状态
kubectl rollout status deployment/redis-grpc -n isa-cloud-staging
```

---

## 🐛 故障排查

### Pod 一直 Pending

**症状**: Pod 卡在 Pending 状态

**检查**:
```bash
kubectl describe pod <pod-name> -n isa-cloud-staging
```

**常见原因和解决方法**:

1. **镜像未加载**
```bash
# 检查镜像是否在 kind 中
docker exec -it isa-cloud-local-control-plane crictl images

# 加载镜像
kind load docker-image <image>:staging --name isa-cloud-local
```

2. **资源不足**
```bash
# 增加 Docker Desktop 资源配额
# Settings > Resources > 调整 CPU/内存

# 或减少副本数
kubectl scale deployment/<name> -n isa-cloud-staging --replicas=1
```

3. **PVC 未绑定**
```bash
# 查看 PVC 状态
kubectl get pvc -n isa-cloud-staging

# kind 使用 local-path-provisioner，会自动创建 PV
# 如果长时间未绑定，检查 StorageClass
kubectl get storageclass
```

### ImagePullBackOff

**症状**: Pod 报 ErrImagePull 或 ImagePullBackOff

**检查**:
```bash
kubectl describe pod <pod-name> -n isa-cloud-staging
```

**解决方法**:
```bash
# 确认镜像已构建
docker images | grep <image-name>

# 加载到 kind
kind load docker-image <image>:staging --name isa-cloud-local

# 或设置 imagePullPolicy: Never
# (已在 base manifests 中设置为 IfNotPresent)
```

### CrashLoopBackOff

**症状**: Pod 反复重启

**检查日志**:
```bash
kubectl logs -n isa-cloud-staging <pod-name> --previous
kubectl logs -n isa-cloud-staging <pod-name> -f
```

**常见原因**:
1. **依赖服务未就绪** - 等待依赖服务启动
2. **配置错误** - 检查 ConfigMap/Secret
3. **资源限制过小** - 调整 resources.limits
4. **健康检查失败** - 调整 livenessProbe

### 服务无法访问

**症状**: 无法通过 localhost 访问服务

**检查端口映射**:
```bash
# 查看 kind 配置
kubectl get nodes -o wide

# 检查 Service
kubectl get svc -n isa-cloud-staging

# 测试端口转发
kubectl port-forward -n isa-cloud-staging svc/consul 8500:8500
```

**解决方法**:
1. **确认 Pod Running**:
```bash
kubectl get pods -n isa-cloud-staging -l app=consul
```

2. **检查防火墙**:
```bash
# macOS
sudo lsof -i :8500

# Linux
sudo netstat -tlnp | grep 8500
```

3. **重新创建集群**:
```bash
./kind-teardown.sh
./kind-setup.sh
```

---

## 🧹 清理环境

### 删除特定服务
```bash
# 删除 gRPC 服务
kubectl delete -k deployments/kubernetes/base/grpc-services/

# 删除基础设施
kubectl delete -k deployments/kubernetes/base/infrastructure/
```

### 完全清理（推荐）
```bash
# 使用脚本
./kind-teardown.sh

# 包括:
# - 删除 kind 集群
# - 可选清理 Docker 镜像
```

### 手动清理
```bash
# 删除集群
kind delete cluster --name isa-cloud-local

# 清理镜像
docker images | grep ":staging" | awk '{print $3}' | xargs docker rmi -f

# 清理构建缓存
docker builder prune -a
```

---

## 🔄 与 Minikube 的对比

| 特性 | kind | Minikube |
|------|------|----------|
| 启动速度 | ⚡️ 秒级 | 🐢 分钟级 |
| 资源占用 | ✅ 低 | ⚠️ 高 |
| 多节点支持 | ✅ 原生支持 | ⚠️ 需额外配置 |
| 镜像加载 | ✅ 直接加载 | ⚠️ 需特殊处理 |
| CI/CD | ✅ 广泛使用 | ⚠️ 较少使用 |
| 生产相似度 | ✅ 高 | ⚠️ 中等 |
| Dashboard | ❌ 需手动安装 | ✅ 内置 |
| 适用场景 | 开发/测试/CI | 学习/快速验证 |

---

## 💡 最佳实践

### 1. 镜像管理
```bash
# 使用明确的标签，避免 :latest
image: redis-service:staging  # ✅ 好
image: redis-service:latest   # ❌ 不好

# 设置合适的 imagePullPolicy
imagePullPolicy: IfNotPresent  # ✅ 本地开发
imagePullPolicy: Always        # ✅ 生产环境
```

### 2. 资源限制
```yaml
resources:
  requests:    # 最小保证资源
    cpu: 100m
    memory: 256Mi
  limits:      # 最大可用资源
    cpu: 500m
    memory: 512Mi
```

### 3. 健康检查
```yaml
livenessProbe:   # 存活检查（失败则重启）
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:  # 就绪检查（失败则移出负载均衡）
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
```

### 4. 日志和监控
```bash
# 使用结构化日志
{"level":"info","msg":"Server started","port":8080}

# 导出日志到 Loki
kubectl logs -n isa-cloud-staging -l app=myapp | loki-cli push

# 配置 Grafana 仪表板
open http://localhost:3000
```

### 5. 服务依赖
```yaml
# 使用 initContainers 等待依赖服务
initContainers:
- name: wait-for-redis
  image: busybox:1.36
  command:
  - sh
  - -c
  - until nc -z redis 6379; do sleep 2; done
```

---

## 📚 相关资源

### 文档
- [kind 官方文档](https://kind.sigs.k8s.io/)
- [Kubernetes 文档](https://kubernetes.io/docs/)
- [Kustomize 文档](https://kustomize.io/)
- [kubectl 速查表](https://kubernetes.io/docs/reference/kubectl/cheatsheet/)

### 项目文档
- [README.md](./README.md) - 总体架构说明
- [QUICK_START.md](./QUICK_START.md) - 详细快速开始
- [MIGRATION_PLAN.md](./MIGRATION_PLAN.md) - 云端迁移策略

### 脚本
- `kind-setup.sh` - 创建集群
- `kind-build-load.sh` - 构建和加载镜像
- `kind-deploy.sh` - 部署服务
- `kind-teardown.sh` - 清理环境

---

## 🆘 获取帮助

如果遇到问题：

1. **查看日志**: `kubectl logs -n isa-cloud-staging <pod-name>`
2. **查看事件**: `kubectl get events -n isa-cloud-staging`
3. **描述资源**: `kubectl describe pod <pod-name> -n isa-cloud-staging`
4. **导出调试信息**: `kind export logs --name isa-cloud-local ./logs`
5. **重新开始**: `./kind-teardown.sh && ./kind-setup.sh`

---

## ✅ 检查清单

部署前确认：
- [ ] Docker Desktop 已启动
- [ ] kind 和 kubectl 已安装
- [ ] Docker Desktop 资源配额充足（至少 4 CPU / 6GB 内存）
- [ ] 端口 8500, 9001, 3000, 8080 等未被占用

部署后验证：
- [ ] 集群节点全部 Ready
- [ ] 所有 Pod 全部 Running
- [ ] 可以访问 Consul UI (http://localhost:8500)
- [ ] 服务成功注册到 Consul
- [ ] 日志正常输出无错误

---

祝你使用愉快！如有问题欢迎反馈。🎉
