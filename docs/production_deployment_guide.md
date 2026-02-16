# 生产环境部署与自动扩缩容指南

## 目录

- [概述](#概述)
- [从 KIND 到生产环境](#从-kind-到生产环境)
- [生产环境选择](#生产环境选择)
- [迁移策略](#迁移策略)
- [水平自动扩缩容 (HPA)](#水平自动扩缩容-hpa)
- [完整部署示例](#完整部署示例)
- [监控和运维](#监控和运维)

## 概述

本文档详细说明如何将当前基于 KIND (Kubernetes IN Docker) 的本地开发环境迁移到生产环境，以及如何实现服务的水平自动扩缩容。

### 当前环境概况

**本地开发环境 (KIND)**:
- **集群类型**: KIND (Docker 容器模拟的 Kubernetes)
- **节点数**: 3 个 (1 control-plane + 2 workers)
- **Kubernetes 版本**: v1.34.0
- **运行环境**: macOS Docker Desktop
- **服务部署**: 单副本 (replicas: 1)
- **存储**: 本地 PV (hostPath)
- **网络**: Docker bridge 网络
- **负载均衡**: 端口映射到 localhost

**限制**:
- ❌ 无真实的云负载均衡器
- ❌ 无持久化块存储
- ❌ 无自动扩缩容
- ❌ 无高可用保证
- ❌ 资源受限于单机
- ❌ 无生产级监控

**适用场景**: 开发、测试、本地调试


## 从 KIND 到生产环境

### 架构对比

```
┌─────────────────────────────────────────────────────────────────┐
│                   开发环境 (KIND)                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────┐               │
│  │        Docker Desktop (macOS)                │               │
│  │  ┌────────────────────────────────────────┐  │               │
│  │  │   KIND Cluster (Docker Containers)     │  │               │
│  │  │                                        │  │               │
│  │  │  ┌──────────┐  ┌──────────┐           │  │               │
│  │  │  │ Control  │  │ Worker-1 │           │  │               │
│  │  │  │  Plane   │  │          │           │  │               │
│  │  │  └──────────┘  └──────────┘           │  │               │
│  │  │       │              │                 │  │               │
│  │  │       └──────┬───────┘                 │  │               │
│  │  │              │                         │  │               │
│  │  │         [Pods: 1 replica]              │  │               │
│  │  │         [Storage: hostPath]            │  │               │
│  │  │         [LB: Port mapping]             │  │               │
│  │  └────────────────────────────────────────┘  │               │
│  └──────────────────────────────────────────────┘               │
│                                                                  │
│  访问: localhost:8500, localhost:9080, etc.                      │
└─────────────────────────────────────────────────────────────────┘

                           ↓ 迁移

┌─────────────────────────────────────────────────────────────────┐
│              生产环境 (托管 Kubernetes / 自建)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────┐           │
│  │       云提供商 (AWS/GCP/Azure/阿里云)             │           │
│  │  ┌────────────────────────────────────────────┐  │           │
│  │  │   Managed Kubernetes (EKS/GKE/AKS/ACK)    │  │           │
│  │  │                                            │  │           │
│  │  │  ┌──────────┐  ┌──────────┐  ┌────────┐   │  │           │
│  │  │  │ Master-1 │  │ Master-2 │  │Master-3│   │  │  (托管)   │
│  │  │  └──────────┘  └──────────┘  └────────┘   │  │           │
│  │  │       │              │              │      │  │           │
│  │  │  ┌────┴──────────────┴──────────────┴───┐ │  │           │
│  │  │  │                                       │ │  │           │
│  │  │  │  ┌────────┐  ┌────────┐  ┌────────┐  │ │  │           │
│  │  │  │  │Worker-1│  │Worker-2│  │Worker-3│  │ │  │           │
│  │  │  │  │(m5.2xl)│  │(m5.2xl)│  │(m5.2xl)│  │ │  │           │
│  │  │  │  └────────┘  └────────┘  └────────┘  │ │  │           │
│  │  │  │                                       │ │  │           │
│  │  │  │  [Pods: HPA 2-10 replicas]           │ │  │           │
│  │  │  │  [Storage: EBS/Persistent Disk]      │ │  │           │
│  │  │  │  [LB: Cloud Load Balancer]           │ │  │           │
│  │  │  └───────────────────────────────────────┘ │  │           │
│  │  └────────────────────────────────────────────┘  │           │
│  └──────────────────────────────────────────────────┘           │
│                                                                  │
│  访问: https://api.example.com (公网域名 + SSL)                  │
└─────────────────────────────────────────────────────────────────┘
```

### 关键差异

| 维度 | KIND (开发) | 生产环境 |
|------|------------|----------|
| **控制平面** | Docker 容器 | 托管 HA 或自建 HA |
| **节点** | 虚拟 (Docker) | 真实 VM/物理机 |
| **副本数** | 1 (单副本) | 2-10+ (HPA) |
| **存储** | hostPath | Cloud Block Storage (EBS/PD) |
| **负载均衡** | 端口映射 | Cloud LB (ALB/NLB/GLB) |
| **网络** | Docker bridge | VPC + CNI (Calico/Cilium) |
| **监控** | 手动 | Prometheus + Grafana |
| **日志** | kubectl logs | ELK/Loki + 持久化 |
| **备份** | 手动快照 | 自动备份 + DR |
| **安全** | 本地访问 | RBAC + NetworkPolicy + PSP |
| **成本** | $0 | $$$ (按需计费) |


## 生产环境选择

### 选项 1: 托管 Kubernetes (推荐)

#### AWS EKS (Elastic Kubernetes Service)

**优势**:
- ✅ 控制平面完全托管，自动升级
- ✅ 与 AWS 服务深度集成 (ELB, EBS, RDS, etc.)
- ✅ 企业级安全和合规性
- ✅ 自动扩缩容 (Cluster Autoscaler)
- ✅ 丰富的实例类型选择

**成本估算** (us-east-1):
```
控制平面: $0.10/小时 × 24 × 30 = ~$73/月
Worker 节点:
  - t3.medium × 3: $0.0416/h × 3 × 730h = ~$91/月
  - m5.xlarge × 3: $0.192/h × 3 × 730h = ~$421/月
负载均衡器: ~$20/月
存储 (EBS): $0.10/GB × 100GB = ~$10/月

总计 (小型): ~$194/月
总计 (中型): ~$524/月
```

**部署步骤**:
```bash
# 1. 安装 eksctl
brew install eksctl

# 2. 创建 EKS 集群
eksctl create cluster \
  --name isa-cloud-prod \
  --region us-east-1 \
  --version 1.30 \
  --nodegroup-name standard-workers \
  --node-type m5.xlarge \
  --nodes 3 \
  --nodes-min 2 \
  --nodes-max 10 \
  --managed

# 3. 配置 kubectl
aws eks update-kubeconfig --name isa-cloud-prod --region us-east-1

# 4. 验证连接
kubectl get nodes
```

#### GKE (Google Kubernetes Engine)

**优势**:
- ✅ 最成熟的托管 K8s (Google 原创)
- ✅ 控制平面免费
- ✅ 自动修复和升级
- ✅ 按秒计费
- ✅ 与 GCP 服务集成 (Cloud SQL, Cloud Storage, etc.)

**成本估算** (us-central1):
```
控制平面: 免费
Worker 节点:
  - e2-standard-2 × 3: $0.067/h × 3 × 730h = ~$147/月
  - n2-standard-4 × 3: $0.194/h × 3 × 730h = ~$425/月
负载均衡器: ~$18/月
存储 (Persistent Disk): $0.10/GB × 100GB = ~$10/月

总计 (小型): ~$175/月
总计 (中型): ~$453/月
```

**部署步骤**:
```bash
# 1. 安装 gcloud
brew install --cask google-cloud-sdk

# 2. 认证
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# 3. 创建 GKE 集群
gcloud container clusters create isa-cloud-prod \
  --region us-central1 \
  --num-nodes 3 \
  --machine-type n2-standard-4 \
  --enable-autoscaling \
  --min-nodes 2 \
  --max-nodes 10 \
  --enable-autorepair \
  --enable-autoupgrade

# 4. 配置 kubectl
gcloud container clusters get-credentials isa-cloud-prod --region us-central1

# 5. 验证
kubectl get nodes
```

#### Azure AKS (Azure Kubernetes Service)

**优势**:
- ✅ 与 Microsoft Azure 生态系统集成
- ✅ 企业级安全 (Azure AD, RBAC)
- ✅ 控制平面免费
- ✅ Windows 容器支持

**成本估算** (East US):
```
控制平面: 免费
Worker 节点:
  - Standard_D2s_v3 × 3: $0.096/h × 3 × 730h = ~$210/月
  - Standard_D4s_v3 × 3: $0.192/h × 3 × 730h = ~$421/月

总计 (小型): ~$228/月
总计 (中型): ~$439/月
```

**部署步骤**:
```bash
# 1. 安装 Azure CLI
brew install azure-cli

# 2. 登录
az login

# 3. 创建资源组
az group create --name isa-cloud-rg --location eastus

# 4. 创建 AKS 集群
az aks create \
  --resource-group isa-cloud-rg \
  --name isa-cloud-prod \
  --node-count 3 \
  --node-vm-size Standard_D4s_v3 \
  --enable-cluster-autoscaler \
  --min-count 2 \
  --max-count 10 \
  --enable-addons monitoring

# 5. 配置 kubectl
az aks get-credentials --resource-group isa-cloud-rg --name isa-cloud-prod

# 6. 验证
kubectl get nodes
```

#### 阿里云 ACK (Alibaba Cloud Container Service)

**优势**:
- ✅ 国内访问速度快
- ✅ 与阿里云生态集成
- ✅ 支持神龙架构
- ✅ 价格相对便宜

**成本估算** (华东2):
```
控制平面: ¥0.42/小时 = ~¥308/月
Worker 节点:
  - ecs.c6.xlarge × 3: ¥0.51/h × 3 × 730h = ~¥1,117/月

总计: ~¥1,425/月 (~$200/月)
```

### 选项 2: 自建 Kubernetes

#### 使用 kubeadm (传统方式)

**优势**:
- ✅ 完全控制
- ✅ 无供应商锁定
- ✅ 成本可控

**劣势**:
- ❌ 需要自己维护控制平面
- ❌ 需要自己处理升级
- ❌ 需要专业运维团队

**适用场景**: 
- 有专业 K8s 运维团队
- 特殊合规要求
- 已有 IDC 资源

**部署参考**:
```bash
# 控制平面初始化
sudo kubeadm init --pod-network-cidr=10.244.0.0/16

# Worker 节点加入
sudo kubeadm join <control-plane-ip>:6443 --token <token> \
  --discovery-token-ca-cert-hash sha256:<hash>

# 安装网络插件 (Calico)
kubectl apply -f https://docs.projectcalico.org/manifests/calico.yaml
```

#### 使用 k3s (轻量级)

**优势**:
- ✅ 资源占用小
- ✅ 部署简单
- ✅ 适合边缘计算

**安装**:
```bash
# Master 节点
curl -sfL https://get.k3s.io | sh -

# Worker 节点
curl -sfL https://get.k3s.io | K3S_URL=https://master:6443 \
  K3S_TOKEN=<token> sh -
```

### 推荐方案对比

| 场景 | 推荐方案 | 理由 |
|------|---------|------|
| **创业公司/小型团队** | GKE | 控制平面免费，按秒计费 |
| **AWS 生态** | EKS | 深度集成 AWS 服务 |
| **Azure 生态** | AKS | 企业级安全，AD 集成 |
| **国内部署** | 阿里云 ACK | 访问速度快，价格实惠 |
| **边缘/IoT** | k3s | 轻量级，资源占用小 |
| **金融/政府** | 自建 + kubeadm | 完全控制，满足合规 |

