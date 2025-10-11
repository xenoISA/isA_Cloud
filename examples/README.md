# isA Cloud 示例代码
# isA Cloud Examples

## 概述

这个目录包含 isA Cloud 平台各个 SDK 的使用示例代码，帮助开发者快速上手。

## 示例列表

### Go 示例

| 文件 | SDK | 说明 |
|------|-----|------|
| `go/loki_example.go` | Loki SDK | 日志聚合客户端使用示例 |
| `go/mqtt_example.go` | MQTT SDK | IoT 消息代理客户端使用示例 |
| `go/minio_example.go` | MinIO SDK | 对象存储客户端使用示例（待创建） |
| `go/duckdb_example.go` | DuckDB SDK | 分析数据库客户端使用示例（待创建） |

### Python 示例

| 文件 | SDK | 说明 |
|------|-----|------|
| `python/loki_example.py` | Loki SDK | 日志聚合客户端使用示例（待创建） |
| `python/mqtt_example.py` | MQTT SDK | IoT 消息代理客户端使用示例（待创建） |
| `python/minio_example.py` | MinIO SDK | 对象存储客户端使用示例 |
| `python/duckdb_example.py` | DuckDB SDK | 分析数据库客户端使用示例（待创建） |

## 运行示例

### Go 示例

```bash
# Loki 示例
go run examples/go/loki_example.go

# MQTT 示例
go run examples/go/mqtt_example.go

# MinIO 示例（待创建）
go run examples/go/minio_example.go
```

### Python 示例

```bash
# MinIO 示例
python examples/python/minio_example.py

# 其他示例（待创建）
python examples/python/loki_example.py
python examples/python/mqtt_example.py
```

## 前置条件

### 启动本地服务

在运行示例之前，需要启动相应的本地服务：

```bash
# Loki（日志服务）
docker run -d --name loki -p 3100:3100 grafana/loki:latest

# MQTT Broker（消息代理）
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto:latest

# MinIO（对象存储）
docker run -d --name minio \
  -p 9000:9000 -p 9001:9001 \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  minio/minio server /data --console-address ":9001"

# 或使用 docker-compose 启动所有服务
cd deployments/envs/staging
docker-compose up -d
```

## 配置

示例默认使用 `configs/sdk/` 目录中的配置文件。您可以：

1. **修改配置文件**：编辑 `configs/sdk/<service>.yaml`
2. **使用环境变量**：导出环境变量覆盖配置
3. **使用示例配置**：参考 `configs/examples/` 目录

详见：[SDK 配置指南](../configs/sdk/README.md)

## 示例说明

### Loki 示例 (`go/loki_example.go`)

演示功能：
- 创建 Loki 客户端
- 推送单条日志
- 推送不同级别的日志（debug, info, warn, error, fatal）
- 批量推送日志
- 查询日志
- 查询标签和标签值
- 健康检查

### MQTT 示例 (`go/mqtt_example.go`)

演示功能：
- 创建发布者和订阅者客户端
- 发布/订阅消息
- 使用主题通配符
- 不同 QoS 级别
- 保留消息
- 遗嘱消息
- JSON 消息序列化

### MinIO 示例 (`python/minio_example.py`)

演示功能：
- 创建 MinIO 客户端
- 创建和删除存储桶
- 上传和下载对象
- 列举对象
- 生成预签名 URL

## 目录结构

```
examples/
├── go/                          # Go 语言示例
│   ├── loki_example.go
│   ├── mqtt_example.go
│   ├── minio_example.go
│   └── duckdb_example.go
│
├── python/                      # Python 语言示例
│   ├── loki_example.py
│   ├── mqtt_example.py
│   ├── minio_example.py
│   └── duckdb_example.py
│
└── README.md                    # 本文件
```

## 相关资源

### SDK 文档
- [Loki SDK](../pkg/infrastructure/logging/loki/README.md)
- [MQTT SDK](../pkg/infrastructure/messaging/mqtt/README.md)
- [MinIO SDK](../pkg/storage/minio/README.md)
- [DuckDB SDK](../pkg/analytics/duckdb/README.md)

### 配置文件
- [SDK 配置](../configs/sdk/)
- [配置示例](../configs/examples/)

### 测试
- [单元测试](../tests/unit/)
- [集成测试](../tests/integration/)

## 贡献示例

欢迎贡献新的示例代码！请遵循以下规范：

### 命名规范
- Go: `<service>_example.go`
- Python: `<service>_example.py`

### 代码规范
- 包含详细的中英文注释
- 演示主要功能
- 包含错误处理
- 添加使用说明

## 支持

如有问题，请参考：
- [统一基础设施 SDK](../docs/UNIFIED_INFRASTRUCTURE_SDK.md)
- [SDK 实施总结](../docs/SDK_IMPLEMENTATION_SUMMARY.md)



