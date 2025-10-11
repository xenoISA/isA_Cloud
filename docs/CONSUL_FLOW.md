# Consul 服务注册与 SDK 发现流程
# Consul Service Registration and SDK Discovery Flow

**文件名：** `docs/CONSUL_FLOW.md`

## 核心理解

### 服务 (deployments/) vs SDK (pkg/)

```
┌─────────────────────────────────────────────────────┐
│  Consul (Service Registry)                          │
│  存储所有服务的地址和端口                              │
└─────────────────────────────────────────────────────┘
         ↑ 注册                      ↓ 发现
         │                          │
    ┌────┴────┐              ┌──────┴──────┐
    │ 服务端   │              │  客户端      │
    │ (被发现) │              │  (发现服务)  │
    └─────────┘              └─────────────┘
```

---

## 详细流程

### 阶段 1: 服务启动和注册

```
┌─────────────────────────────────────────┐
│ 1. Docker 启动 MinIO 容器                │
│    环境变量:                              │
│    - CONSUL_ENABLED=true                │
│    - CONSUL_HOST=consul                 │
│    - CONSUL_PORT=8500                   │
│    - SERVICE_NAME=minio-service         │
└─────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────┐
│ 2. MinIO 容器内的启动脚本                 │
│    /usr/local/bin/start-minio.sh:       │
│    - 启动 MinIO 服务                     │
│    - 检查 CONSUL_ENABLED=true           │
│    - 调用 Consul API 注册自己           │
└─────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────┐
│ 3. Consul 注册信息                       │
│    {                                    │
│      "Name": "minio-service",           │
│      "Address": "minio",                │
│      "Port": 9000,                      │
│      "Check": {...}                     │
│    }                                    │
└─────────────────────────────────────────┘
```

### 阶段 2: SDK 客户端发现服务

```
┌─────────────────────────────────────────┐
│ 4. Cloud 应用容器启动                     │
│    (MCP/Model/Agent 服务)                │
│    需要使用 MinIO SDK                     │
└─────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────┐
│ 5. SDK 配置                              │
│    cfg := &minio.Config{                │
│        UseConsul: true,                 │
│        ServiceName: "minio-service",    │
│    }                                    │
└─────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────┐
│ 6. SDK 查询 Consul                       │
│    client := NewClient(cfg)             │
│    → SDK 内部调用 Consul API             │
│    → 查询 "minio-service"                │
│    → 获取 Address: "minio", Port: 9000  │
└─────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────┐
│ 7. SDK 连接到服务                        │
│    SDK → http://minio:9000              │
│    成功访问 MinIO 服务！                  │
└─────────────────────────────────────────┘
```

---

## 目录职责

### deployments/ - 服务部署

```
deployments/
├── dockerfiles/Staging/          # 服务镜像
│   └── Dockerfile.*.staging        → 服务容器，启动时注册到 Consul
│
├── configs/staging/              # 服务配置
│   └── *.{yaml,conf}               → 服务运行时配置
│
├── compose/                      # 服务编排
│   ├── sdk-services.yml            → 定义服务容器
│   └── ...
│
└── scripts/                      # 服务脚本
    ├── start-staging.sh            → 启动服务
    └── test-services.sh            → 测试服务注册
```

### pkg/ - SDK 客户端

```
pkg/
├── infrastructure/
│   ├── logging/loki/             # Loki SDK
│   │   └── client.go               → 通过 Consul 发现 Loki 服务
│   └── messaging/mqtt/           # MQTT SDK
│       └── client.go               → 通过 Consul 发现 MQTT 服务
│
└── storage/minio/                # MinIO SDK
    └── client.go                   → 通过 Consul 发现 MinIO 服务
```

### scripts/ - SDK 测试脚本

```
scripts/
├── test-unit.sh                  # SDK 单元测试
└── test-sdk.sh                   # SDK 集成测试
```

---

## 需要调整的地方

### 1. ✅ 脚本位置已调整

- `deployments/scripts/start-staging.sh` - 启动服务
- `deployments/scripts/test-services.sh` - 测试服务注册
- `scripts/test-unit.sh` - SDK 单元测试（保留在根目录）

### 2. 需要创建 SDK 集成测试

在应用容器中测试 SDK 通过 Consul 发现服务：

```go
// 在 Cloud 应用容器中运行
func TestSDKWithConsul(t *testing.T) {
    // SDK 配置使用 Consul
    cfg := &minio.Config{
        UseConsul:   true,
        ServiceName: "minio-service",
    }
    
    // SDK 通过 Consul 发现服务
    client, err := minio.NewClient(cfg)
    // 应该成功连接到 MinIO 服务
}
```

---

## Docker Compose 流程

### 正确的启动顺序

```yaml
# deployments/envs/staging/docker-compose.yml

services:
  # 1. 首先启动 Consul
  consul:
    image: consul:1.16
    ports: ["8500:8500"]
    
  # 2. 启动服务（自动注册到 Consul）
  loki:
    depends_on:
      - consul
    environment:
      - CONSUL_ENABLED=true        # ← 服务启动时注册
      - CONSUL_HOST=consul
      - SERVICE_NAME=loki-service
      
  minio:
    depends_on:
      - consul
    environment:
      - CONSUL_ENABLED=true        # ← 服务启动时注册
      - SERVICE_NAME=minio-service
      
  # 3. 启动应用容器（使用 SDK）
  mcp-service:
    depends_on:
      - consul
      - loki
      - minio
    environment:
      - CONSUL_HOST=consul         # ← SDK 通过 Consul 发现服务
      - USE_CONSUL=true
```

---

## 总结修正

### ❌ 之前的错误理解
- 把 SDK 测试脚本放在 `scripts/` 和服务脚本混在一起

### ✅ 正确的组织
- **deployments/scripts/** - 服务部署脚本（启动、停止、注册测试）
- **scripts/** - SDK 开发脚本（单元测试、SDK 测试）
- **服务** 通过环境变量注册到 Consul
- **SDK** 在应用容器中通过 Consul 发现服务

下一步我需要调整什么？

1. 更新 docker-compose.yml 的依赖关系？
2. 创建 SDK 集成测试（在应用容器中）？
3. 其他？



