# 🚀 isA Cloud - Kubernetes 快速开始 (kind)

## ✅ 前置要求

- **Docker Desktop** - kind 需要 Docker 运行
- **kubectl** v1.28+ - Kubernetes 命令行工具
- **kind** v0.20+ - Kubernetes in Docker

### 安装 kind

```bash
# macOS
brew install kind

# Linux
curl -Lo ./kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind

# Windows (使用 PowerShell 管理员模式)
choco install kind

# 验证安装
kind version
```

---

## 🎯 快速开始（3 步完成）

### 步骤 1：创建 kind 集群

```bash
cd deployments/kubernetes/scripts

# 创建集群（使用预配置的 kind-config.yaml）
./kind-setup.sh
```

这将创建一个包含以下配置的集群：
- **1 个控制平面节点 + 2 个工作节点**
- **预配置端口映射** - 直接访问服务无需端口转发
- **集群名称**: `isa-cloud-local`

### 步骤 2：构建并加载镜像

```bash
# 交互式选择要构建的服务
./kind-build-load.sh
```

选项：
1. **全部服务** - 构建所有基础设施和 gRPC 服务
2. **仅基础设施** - Consul, Redis, MinIO, NATS, Loki
3. **仅 gRPC 服务** - 所有微服务
4. **自定义** - 选择特定服务

**建议**: 首次使用选择 **选项 2（仅基础设施）** 快速验证

### 步骤 3：部署服务

```bash
# 交互式部署
./kind-deploy.sh
```

选择部署模式：
1. 完整部署
2. 仅基础设施
3. 仅 gRPC 服务
4. 使用 Kustomize overlay（推荐）

---

## 🌐 访问服务

由于 kind 配置了端口映射，可以直接访问：

```bash
# Consul UI - 服务发现和注册
http://localhost:8500

# MinIO Console - 对象存储管理
http://localhost:9001
# 默认凭证: minioadmin / minioadmin

# Grafana - 监控仪表板
http://localhost:3000
# 默认凭证: admin / admin

# Infrastructure Gateway - API 网关
http://localhost:8080

# Redis
redis-cli -h localhost -p 6379

# NATS
nats-cli -s localhost:4222
```

或使用 kubectl 端口转发：

```bash
# Consul UI
kubectl port-forward -n isa-cloud-staging svc/consul 8500:8500

# Loki
kubectl port-forward -n isa-cloud-staging svc/loki 3100:3100
```

---

## 🔍 管理和监控

### 查看资源状态

```bash
# 查看所有 Pods
kubectl get pods -n isa-cloud-staging

# 查看所有服务
kubectl get svc -n isa-cloud-staging

# 查看所有资源
kubectl get all -n isa-cloud-staging

# 持续监控 Pod 状态
kubectl get pods -n isa-cloud-staging -w
```

### 查看日志

```bash
# 查看特定服务日志
kubectl logs -n isa-cloud-staging -l app=consul --tail=100 -f

# 查看所有事件
kubectl get events -n isa-cloud-staging --sort-by='.lastTimestamp'

# 查看特定 Pod 日志
kubectl logs -n isa-cloud-staging <pod-name> -f
```

### 调试

```bash
# 查看 Pod 详细信息
kubectl describe pod <pod-name> -n isa-cloud-staging

# 进入 Pod 执行命令
kubectl exec -it -n isa-cloud-staging <pod-name> -- /bin/sh

# 查看 Pod 资源使用情况
kubectl top pods -n isa-cloud-staging
```

---

## 🔧 常用 kind 命令

```bash
# 查看集群列表
kind get clusters

# 查看集群节点
kubectl get nodes

# 查看已加载的镜像
docker exec -it isa-cloud-local-control-plane crictl images

# 手动加载镜像到 kind
kind load docker-image <image-name>:<tag> --name isa-cloud-local

# 导出集群日志（调试用）
kind export logs --name isa-cloud-local ./logs

# 获取集群配置
kind get kubeconfig --name isa-cloud-local
```

---

## 🧪 完整测试流程示例

### 场景 1: 快速验证 Redis

```bash
# 1. 创建集群
./kind-setup.sh

# 2. 构建 Redis 镜像
cd ../../..
eval $(kind export docker-env --name isa-cloud-local)
docker build -t redis:staging -f deployments/dockerfiles/Staging/Dockerfile.redis.staging .

# 3. 加载镜像
kind load docker-image redis:staging --name isa-cloud-local

# 4. 部署 Redis
kubectl apply -f deployments/kubernetes/base/namespace/
kubectl apply -f deployments/kubernetes/base/infrastructure/redis/

# 5. 等待 Pod 就绪
kubectl wait --for=condition=ready pod -l app=redis -n isa-cloud-staging --timeout=5m

# 6. 测试连接
kubectl exec -it -n isa-cloud-staging \
  $(kubectl get pod -l app=redis -n isa-cloud-staging -o jsonpath='{.items[0].metadata.name}') \
  -- redis-cli ping
# 应返回: PONG
```

### 场景 2: 完整基础设施部署

```bash
# 使用自动化脚本
cd deployments/kubernetes/scripts

# 1. 创建集群
./kind-setup.sh

# 2. 构建所有基础设施镜像
./kind-build-load.sh
# 选择: 2) 仅基础设施

# 3. 部署
./kind-deploy.sh
# 选择: 2) 仅基础设施

# 4. 验证
kubectl get pods -n isa-cloud-staging
kubectl get svc -n isa-cloud-staging

# 5. 访问 Consul UI
open http://localhost:8500
```

---

## 🐛 常见问题排查

### 1. Pod 一直处于 Pending

```bash
# 查看原因
kubectl describe pod <pod-name> -n isa-cloud-staging

# 常见原因:
# - 镜像未加载到 kind
# - 资源不足（CPU/内存）
# - 持久卷未创建
```

**解决方法**:
```bash
# 检查镜像是否在 kind 中
docker exec -it isa-cloud-local-control-plane crictl images | grep <image-name>

# 如果镜像不存在，加载镜像
kind load docker-image <image>:staging --name isa-cloud-local
```

### 2. ImagePullBackOff 错误

```bash
# 检查 Pod 事件
kubectl describe pod <pod-name> -n isa-cloud-staging
```

**原因**: kind 无法从外部拉取镜像

**解决方法**:
```bash
# 方案 1: 在 Deployment/StatefulSet 中设置
imagePullPolicy: Never  # 或 IfNotPresent

# 方案 2: 确保镜像已加载到 kind
kind load docker-image <image>:staging --name isa-cloud-local
```

### 3. 服务无法访问

```bash
# 检查 Service 状态
kubectl get svc -n isa-cloud-staging

# 检查端点
kubectl get endpoints -n isa-cloud-staging

# 测试服务连通性
kubectl run -it --rm debug --image=busybox --restart=Never -- wget -O- http://<service-name>.<namespace>.svc.cluster.local:<port>
```

### 4. 磁盘空间不足

```bash
# 清理未使用的镜像
docker system prune -a

# 清理 kind 集群
kind delete cluster --name isa-cloud-local

# 清理构建缓存
docker builder prune
```

---

## 🗑️ 清理环境

### 删除特定服务

```bash
# 删除基础设施
kubectl delete -k deployments/kubernetes/base/infrastructure/

# 删除 gRPC 服务
kubectl delete -k deployments/kubernetes/base/grpc-services/

# 删除 namespace（会删除其中所有资源）
kubectl delete namespace isa-cloud-staging
```

### 完全清理

```bash
# 使用脚本（推荐）
./kind-teardown.sh

# 或手动删除
kind delete cluster --name isa-cloud-local

# 清理相关镜像
docker images | grep ":staging" | awk '{print $3}' | xargs docker rmi -f
```

---

## 📊 资源配置

### 默认 kind 集群配置

- **CPU**: 根据 Docker Desktop 设置
- **内存**: 根据 Docker Desktop 设置
- **节点**: 1 控制平面 + 2 工作节点
- **网络**:
  - Pod CIDR: `10.244.0.0/16`
  - Service CIDR: `10.96.0.0/12`

### 建议的 Docker Desktop 资源

运行完整平台建议：
- **CPU**: 6-8 核
- **内存**: 8-12 GB
- **磁盘**: 50+ GB

仅基础设施：
- **CPU**: 4 核
- **内存**: 6 GB
- **磁盘**: 20+ GB

在 Docker Desktop > Settings > Resources 中调整

---

## 🎓 学习路径

**初学者**:
1. ✅ 创建 kind 集群
2. ✅ 部署单个服务（Redis）
3. ✅ 学习 kubectl 基本命令
4. ✅ 查看日志和状态

**中级**:
1. ✅ 部署多个相互依赖的服务
2. ✅ 使用 Kustomize 管理配置
3. ✅ 理解 Service 和网络
4. ✅ 配置持久化存储

**高级**:
1. ✅ 自定义 kind 配置（添加更多节点）
2. ✅ 集成 CI/CD 流程
3. ✅ 性能调优和监控
4. ✅ 准备云端部署（EKS/GKE/AKS）

---

## 📚 相关文档

- [kind 官方文档](https://kind.sigs.k8s.io/)
- [Kubernetes 文档](https://kubernetes.io/docs/)
- [kubectl 速查表](https://kubernetes.io/docs/reference/kubectl/cheatsheet/)
- [Kustomize 文档](https://kustomize.io/)

---

## 💡 最佳实践

1. **使用 imagePullPolicy: Never** - 对于本地镜像
2. **资源限制** - 为每个容器设置 requests 和 limits
3. **健康检查** - 配置 liveness 和 readiness probes
4. **版本控制** - 镜像使用明确的标签，避免使用 `latest`
5. **日志收集** - 使用 Loki 聚合日志
6. **监控** - 使用 Grafana 查看指标

---

## 🆘 获取帮助

如果遇到问题：

1. **查看 Pod 日志**:
   ```bash
   kubectl logs -n isa-cloud-staging <pod-name>
   ```

2. **查看事件**:
   ```bash
   kubectl get events -n isa-cloud-staging --sort-by='.lastTimestamp'
   ```

3. **描述资源**:
   ```bash
   kubectl describe pod/<pod-name> -n isa-cloud-staging
   ```

4. **检查集群状态**:
   ```bash
   kubectl cluster-info dump
   ```

5. **导出日志**:
   ```bash
   kind export logs --name isa-cloud-local ./debug-logs
   ```

祝你使用愉快！🎉

---

## 🔄 下一步

- 📖 阅读 [README.md](./README.md) 了解完整架构
- 🚀 查看 [MIGRATION_PLAN.md](./MIGRATION_PLAN.md) 了解云端迁移策略
- 🛠️ 探索 [base/](./base/) 目录了解 Kubernetes 资源配置
