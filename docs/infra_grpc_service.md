# isA_Cloud Infrastructure gRPC Services 架构说明

**一个文件说清楚整个架构：从 SDK → Config → Proto → gRPC Service → Docker 部署**

---

## 📋 目录
1. [架构概览](#架构概览)
2. [目录结构](#目录结构)
3. [服务组成](#服务组成)
4. [服务启动](#服务启动)
5. [开发流程](#开发流程)

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                     Python 微服务                             │
│                  (通过 gRPC 调用)                             │
└──────────────┬──────────────────────────────────────────────┘
               │ gRPC
               ↓
┌─────────────────────────────────────────────────────────────┐
│              Go gRPC Services (6个独立服务)                   │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │  MinIO   │  DuckDB  │   MQTT   │   Loki   │  Redis   │  │
│  │ Service  │ Service  │ Service  │ Service  │ Service  │  │
│  │  :50051  │  :50052  │  :50053  │  :50054  │  :50055  │  │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘  │
│  ┌──────────┐                                                │
│  │   NATS   │  每个服务包含：                                │
│  │ Service  │  - gRPC Server (proto 定义)                    │
│  │  :50056  │  - SDK Client (pkg/ 实现)                      │
│  └──────────┘  - Config (configs/sdk/*.yaml)                │
│                - Auth & Multi-tenancy                        │
└──────────────┬──────────────────────────────────────────────┘
               │ Native Protocol
               ↓
┌─────────────────────────────────────────────────────────────┐
│          底层基础设施 (Infrastructure)                         │
│  MinIO │ DuckDB │ Mosquitto │ Loki │ Redis │ NATS           │
└─────────────────────────────────────────────────────────────┘
               ↑
               │ Consul Service Discovery
               │
       ┌───────┴────────┐
       │  Consul Agent  │
       └────────────────┘
```

**核心理念**：
- Python 服务**不直接**访问基础设施
- 所有访问通过 Go gRPC Services 统一管理
- gRPC Services 提供认证、多租户、权限控制

---

## 目录结构

```
isA_Cloud/
│
├── pkg/infrastructure/              # 📦 SDK 客户端层
│   ├── storage/minio/              # MinIO SDK
│   │   ├── client.go               # SDK 实现
│   │   └── README.md               # 使用文档
│   ├── analytics/duckdb/           # DuckDB SDK
│   ├── messaging/mqtt/             # MQTT SDK
│   ├── logging/loki/               # Loki SDK
│   ├── cache/redis/                # Redis SDK
│   └── event/nats/                 # NATS SDK
│
├── configs/sdk/                     # ⚙️ SDK 配置层
│   ├── minio.yaml                  # MinIO 配置 (Consul + 连接参数)
│   ├── duckdb.yaml                 # DuckDB 配置
│   ├── mqtt.yaml                   # MQTT 配置
│   ├── loki.yaml                   # Loki 配置
│   ├── redis.yaml                  # Redis 配置
│   ├── nats.yaml                   # NATS 配置
│   └── README.md                   # 配置说明
│
├── api/proto/                       # 🔌 gRPC 协议层
│   ├── common.proto                # 公共消息定义
│   ├── minio_service.proto         # MinIO gRPC 接口
│   ├── duckdb_service.proto        # DuckDB gRPC 接口
│   ├── mqtt_service.proto          # MQTT gRPC 接口
│   ├── loki_service.proto          # Loki gRPC 接口
│   ├── redis_service.proto         # Redis gRPC 接口
│   └── nats_service.proto          # NATS gRPC 接口
│
├── cmd/                             # 🚀 gRPC 服务层
│   ├── minio-service/              # MinIO gRPC 服务
│   │   ├── main.go                 # 服务入口
│   │   └── server/
│   │       ├── server.go           # gRPC 实现
│   │       └── auth.go             # 认证授权
│   ├── duckdb-service/             # DuckDB gRPC 服务
│   ├── mqtt-service/               # MQTT gRPC 服务
│   ├── loki-service/               # Loki gRPC 服务
│   ├── redis-service/              # Redis gRPC 服务
│   └── nats-service/               # NATS gRPC 服务
│
├── deployments/                     # 🐳 部署层
│   ├── dockerfiles/                # Dockerfiles
│   │   ├── Dockerfile.minio-service
│   │   ├── Dockerfile.duckdb-service
│   │   ├── Dockerfile.mqtt-service
│   │   ├── Dockerfile.loki-service
│   │   ├── Dockerfile.redis-service
│   │   └── Dockerfile.nats-service
│   └── compose/
│       ├── grpc-services.yml       # 6个 gRPC 服务编排
│       ├── infrastructure.yml      # 基础设施 (Redis, NATS, Consul)
│       └── sdk-services.yml        # SDK 服务 (MinIO, DuckDB, Loki, MQTT)
│
├── scripts/                         # 🛠️ 工具脚本
│   └── generate-grpc.sh            # 生成 gRPC Go 代码
│
├── Makefile.grpc                    # 构建和运行
└── ARCHITECTURE.md                  # 本文档 ⭐
```

---

## 服务组成

### 每个 gRPC 服务包含 4 层

以 **Redis Service** 为例说明：

#### 1️⃣ SDK 层 (`pkg/infrastructure/cache/redis/`)

**文件**: `client.go`

```go
// SDK 封装了 Redis 原生客户端
type Client struct {
    client *redis.Client
    config *config.CacheConfig
}

// 提供业务方法
func (c *Client) Set(ctx context.Context, key, value string, exp time.Duration) error
func (c *Client) Get(ctx context.Context, key string) (string, error)
func (c *Client) AcquireLock(ctx context.Context, key string, ttl time.Duration) (*Lock, error)
```

**作用**：
- 封装 Redis 原生操作
- 处理连接管理
- 集成 Consul 服务发现

#### 2️⃣ 配置层 (`configs/sdk/redis.yaml`)

```yaml
redis:
  # 直连配置
  host: localhost
  port: 6379
  password: ""
  database: 0
  
  # Consul 服务发现
  consul:
    enabled: true
    service_name: redis-service
    
  # 连接池
  pool:
    max_idle: 10
    max_active: 100
```

**作用**：
- 定义连接参数
- 启用 Consul 自动发现
- 配置连接池和超时

#### 3️⃣ Proto 层 (`api/proto/redis_service.proto`)

```protobuf
service RedisService {
  rpc Set(SetRequest) returns (SetResponse);
  rpc Get(GetRequest) returns (GetResponse);
  rpc AcquireLock(AcquireLockRequest) returns (AcquireLockResponse);
}

message SetRequest {
  string key = 1;
  string value = 2;
  int64 expiration_seconds = 3;
}
```

**作用**：
- 定义 gRPC 接口
- 定义请求/响应消息
- 生成 Go 代码

**生成代码**：
```bash
./scripts/generate-grpc.sh  # 生成 api/proto/*.pb.go
```

#### 4️⃣ gRPC 服务层 (`cmd/redis-service/`)

**`main.go`** (服务入口):
```go
func main() {
    // 1. 加载配置
    cfg := loadConfig()
    
    // 2. 初始化 Redis SDK
    redisClient := redis.NewClient(cfg)
    
    // 3. 创建 gRPC Server
    grpcServer := grpc.NewServer(
        grpc.UnaryInterceptor(authInterceptor),
    )
    
    // 4. 注册 Redis Service
    pb.RegisterRedisServiceServer(grpcServer, server.NewRedisServer(redisClient))
    
    // 5. 注册到 Consul
    consulClient.RegisterService(...)
    
    // 6. 启动监听
    grpcServer.Serve(lis)
}
```

**`server/server.go`** (gRPC 实现):
```go
type RedisServer struct {
    redisClient *redis.Client
}

func (s *RedisServer) Set(ctx context.Context, req *pb.SetRequest) (*pb.SetResponse, error) {
    // 1. 获取用户信息 (从 context)
    userID := getUserIDFromContext(ctx)
    
    // 2. 多租户隔离
    tenantKey := fmt.Sprintf("tenant:%s:%s", userID, req.Key)
    
    // 3. 调用 SDK
    err := s.redisClient.Set(ctx, tenantKey, req.Value, ...)
    
    // 4. 返回结果
    return &pb.SetResponse{Success: true}, nil
}
```

**`server/auth.go`** (认证授权):
```go
func authInterceptor(ctx context.Context, req interface{}, ...) (interface{}, error) {
    // 1. 验证 JWT Token
    token := extractToken(ctx)
    claims := validateJWT(token)
    
    // 2. 检查权限
    if !hasPermission(claims, "redis:write") {
        return nil, status.Error(codes.PermissionDenied, "无权限")
    }
    
    // 3. 注入用户信息到 context
    ctx = context.WithValue(ctx, "user_id", claims.UserID)
    
    return handler(ctx, req)
}
```

**作用**：
- 实现 gRPC 接口
- 调用 SDK 层
- 处理认证授权
- 多租户隔离
- 错误处理

---

## 服务启动

### 方式 1: Docker Compose (推荐) 🐳

**一键启动所有服务**：

```bash
# 1. 启动基础设施 (Redis, NATS, Consul, MinIO, Loki, Mosquitto)
docker-compose -f deployments/compose/infrastructure.yml up -d
docker-compose -f deployments/compose/sdk-services.yml up -d

# 2. 启动 6 个 gRPC 服务
docker-compose -f deployments/compose/grpc-services.yml up -d

# 检查状态
docker ps | grep -E "(redis-service|mqtt-service|loki-service|nats-service|minio-service|duckdb-service)"

# 查看日志
docker-compose -f deployments/compose/grpc-services.yml logs -f redis-service
```

**Docker 自动完成**：
1. ✅ 安装 `protoc`
2. ✅ 生成 gRPC Go 代码
3. ✅ 构建服务二进制
4. ✅ 启动容器
5. ✅ 注册到 Consul

**端口映射**：
- MinIO Service: `50051`
- DuckDB Service: `50052`
- MQTT Service: `50053`
- Loki Service: `50054`
- Redis Service: `50055`
- NATS Service: `50056`

### 方式 2: 本地开发 💻

**手动步骤**：

```bash
# 1. 生成 gRPC Go 代码
./scripts/generate-grpc.sh

# 2. 构建所有服务
make -f Makefile.grpc build-services

# 3. 启动单个服务
./bin/redis-service &

# 或启动所有服务
make -f Makefile.grpc dev

# 停止
make -f Makefile.grpc stop
```

**环境变量**：
```bash
export REDIS_HOST=localhost
export REDIS_PORT=6379
export CONSUL_ADDR=localhost:8500
export JWT_SECRET=your-secret-key
```

---

## 开发流程

### 添加新的 gRPC 服务

以添加 **PostgreSQL Service** 为例：

#### 步骤 1: 创建 SDK (`pkg/infrastructure/database/postgres/`)

```go
// client.go
package postgres

type Client struct {
    db *sql.DB
}

func NewClient(cfg *config.DatabaseConfig) (*Client, error) {
    db, err := sql.Open("postgres", cfg.DSN())
    return &Client{db: db}, err
}

func (c *Client) Query(ctx context.Context, sql string) (*sql.Rows, error) {
    return c.db.QueryContext(ctx, sql)
}
```

#### 步骤 2: 创建配置 (`configs/sdk/postgres.yaml`)

```yaml
postgres:
  host: localhost
  port: 5432
  database: mydb
  username: postgres
  password: secret
  
  consul:
    enabled: true
    service_name: postgres-service
```

#### 步骤 3: 定义 Proto (`api/proto/postgres_service.proto`)

```protobuf
syntax = "proto3";
package postgres;
option go_package = "isA_Cloud/api/proto";

service PostgresService {
  rpc ExecuteQuery(QueryRequest) returns (QueryResponse);
}

message QueryRequest {
  string sql = 1;
}

message QueryResponse {
  repeated Row rows = 1;
}
```

#### 步骤 4: 生成 gRPC 代码

```bash
./scripts/generate-grpc.sh
# 生成: api/proto/postgres_service.pb.go
#      api/proto/postgres_service_grpc.pb.go
```

#### 步骤 5: 实现 gRPC 服务 (`cmd/postgres-service/`)

```bash
mkdir -p cmd/postgres-service/server
```

**`main.go`**:
```go
package main

import (
    "isA_Cloud/pkg/infrastructure/database/postgres"
    pb "isA_Cloud/api/proto"
)

func main() {
    // 1. 加载配置
    cfg := loadConfig()
    
    // 2. 初始化 SDK
    pgClient, _ := postgres.NewClient(cfg)
    
    // 3. 启动 gRPC
    grpcServer := grpc.NewServer()
    pb.RegisterPostgresServiceServer(grpcServer, server.NewPostgresServer(pgClient))
    grpcServer.Serve(lis)
}
```

**`server/server.go`**:
```go
type PostgresServer struct {
    pgClient *postgres.Client
}

func (s *PostgresServer) ExecuteQuery(ctx context.Context, req *pb.QueryRequest) (*pb.QueryResponse, error) {
    rows, err := s.pgClient.Query(ctx, req.Sql)
    // ... 处理结果
    return &pb.QueryResponse{Rows: rows}, nil
}
```

#### 步骤 6: 创建 Dockerfile (`deployments/dockerfiles/Dockerfile.postgres-service`)

```dockerfile
FROM golang:1.23-alpine AS builder
RUN apk add --no-cache protobuf protobuf-dev git make
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@latest && \
    go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
COPY . .
RUN protoc --go_out=. --go_opt=paths=source_relative \
    --go-grpc_out=. --go-grpc_opt=paths=source_relative \
    api/proto/common.proto \
    api/proto/postgres_service.proto
RUN go build -o bin/postgres-service cmd/postgres-service/main.go

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /app
COPY --from=builder /app/bin/postgres-service /app/postgres-service
COPY configs/ /app/configs/
EXPOSE 50057
CMD ["/app/postgres-service"]
```

#### 步骤 7: 添加到 Docker Compose (`deployments/compose/grpc-services.yml`)

```yaml
services:
  postgres-service:
    build:
      context: ../..
      dockerfile: deployments/dockerfiles/Dockerfile.postgres-service
    image: isa-cloud/postgres-service:latest
    container_name: postgres-grpc-service
    ports:
      - "50057:50057"
    environment:
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - CONSUL_ADDR=consul:8500
    networks:
      - isa-cloud-network
    depends_on:
      - consul
      - postgres
```

#### 步骤 8: 启动服务

```bash
docker-compose -f deployments/compose/grpc-services.yml up -d postgres-service
```

---

## 常用命令

### 开发命令

```bash
# 生成 gRPC 代码
./scripts/generate-grpc.sh

# 构建所有服务
make -f Makefile.grpc build-services

# 构建单个服务
go build -o bin/redis-service cmd/redis-service/main.go

# 运行单个服务
./bin/redis-service

# 测试 gRPC 服务 (需要安装 grpcurl)
grpcurl -plaintext -d '{"key":"test","value":"123"}' \
  localhost:50055 redis.RedisService/Set
```

### Docker 命令

```bash
# 构建镜像
docker-compose -f deployments/compose/grpc-services.yml build redis-service

# 启动服务
docker-compose -f deployments/compose/grpc-services.yml up -d

# 查看日志
docker-compose -f deployments/compose/grpc-services.yml logs -f redis-service

# 重启服务
docker-compose -f deployments/compose/grpc-services.yml restart redis-service

# 停止服务
docker-compose -f deployments/compose/grpc-services.yml down

# 进入容器
docker exec -it redis-grpc-service sh
```

### Consul 命令

```bash
# 查看注册的服务
curl http://localhost:8500/v1/catalog/services

# 查看 Redis Service 实例
curl http://localhost:8500/v1/health/service/redis-grpc-service

# 注销服务
curl -X PUT http://localhost:8500/v1/agent/service/deregister/redis-grpc-service
```

---

## 配置说明

### SDK 配置文件格式

所有 SDK 配置文件 (`configs/sdk/*.yaml`) 遵循统一格式：

```yaml
service_name:
  # 基础连接配置
  host: localhost
  port: 6379
  
  # Consul 服务发现
  consul:
    enabled: true              # 启用 Consul
    service_name: service-name # 服务名
    tag: production            # 服务标签
    
  # 连接池配置
  pool:
    max_idle: 10
    max_active: 100
    idle_timeout: 300s
    
  # 超时配置
  timeout:
    connect: 5s
    read: 30s
    write: 30s
```

### gRPC 服务环境变量

```bash
# 服务配置
export SERVICE_NAME=redis-service
export SERVICE_PORT=50055

# SDK 配置文件路径
export CONFIG_PATH=/app/configs/sdk/redis.yaml

# Consul 配置
export CONSUL_ADDR=localhost:8500
export CONSUL_ENABLED=true

# 认证配置
export JWT_SECRET=your-jwt-secret
export AUTH_ENABLED=true

# 日志配置
export LOG_LEVEL=info
export LOG_FORMAT=json
```

---

## 认证和多租户

### JWT Token 格式

```json
{
  "user_id": "user123",
  "org_id": "org456",
  "roles": ["admin", "user"],
  "permissions": ["redis:read", "redis:write"],
  "exp": 1234567890
}
```

### 调用示例 (Python 客户端)

```python
import grpc
from api.proto import redis_service_pb2, redis_service_pb2_grpc

# 创建 channel
channel = grpc.insecure_channel('localhost:50055')
stub = redis_service_pb2_grpc.RedisServiceStub(channel)

# 添加认证 metadata
metadata = [('authorization', 'Bearer YOUR_JWT_TOKEN')]

# 调用服务
response = stub.Set(
    redis_service_pb2.SetRequest(key='test', value='123'),
    metadata=metadata
)
```

### 多租户键隔离

所有 key 自动添加租户前缀：

```
原始 key: user:123
实际存储: tenant:org456:user:123
```

---

## 故障排查

### 1. gRPC 服务无法启动

**检查**:
```bash
# 检查端口占用
lsof -i :50055

# 检查配置文件
cat configs/sdk/redis.yaml

# 检查环境变量
env | grep -E "(REDIS|CONSUL)"
```

### 2. Consul 连接失败

**检查**:
```bash
# Consul 是否运行
curl http://localhost:8500/v1/status/leader

# 服务是否注册
curl http://localhost:8500/v1/catalog/services
```

### 3. SDK 连接失败

**检查**:
```bash
# 基础设施是否运行
docker ps | grep -E "(redis|nats|minio)"

# 测试连接
redis-cli -h localhost -p 6379 ping
```

### 4. 认证失败

**检查**:
```bash
# JWT Token 是否有效
echo $JWT_TOKEN | base64 -d

# 检查权限配置
cat configs/auth/permissions.yaml
```

---

## 总结

### 核心流程

```
Proto 定义 → 生成 Go 代码 → 实现 gRPC Server → 调用 SDK → 访问基础设施
   ↓            ↓                ↓                ↓           ↓
.proto 文件   *.pb.go      server/server.go   pkg/client.go  Redis/NATS/...
```

### 关键文件

| 层级 | 文件位置 | 作用 |
|------|---------|------|
| SDK | `pkg/infrastructure/*/client.go` | 封装底层客户端 |
| 配置 | `configs/sdk/*.yaml` | 连接参数和 Consul |
| Proto | `api/proto/*_service.proto` | gRPC 接口定义 |
| 服务 | `cmd/*-service/main.go` | gRPC 服务入口 |
| 部署 | `deployments/dockerfiles/Dockerfile.*` | Docker 镜像 |
| 编排 | `deployments/compose/grpc-services.yml` | 服务编排 |

### 快速开始

```bash
# 1. 启动基础设施
docker-compose -f deployments/compose/infrastructure.yml up -d
docker-compose -f deployments/compose/sdk-services.yml up -d

# 2. 启动 gRPC 服务
docker-compose -f deployments/compose/grpc-services.yml up -d

# 3. 检查状态
docker ps
curl http://localhost:8500/v1/catalog/services

# 4. 测试调用 (需要 JWT Token)
grpcurl -plaintext -H "authorization: Bearer TOKEN" \
  -d '{"key":"test","value":"hello"}' \
  localhost:50055 redis.RedisService/Set
```

---

**就这么简单！从 SDK → Config → Proto → gRPC Service，一目了然！** 🚀

