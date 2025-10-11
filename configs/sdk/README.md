# SDK 客户端配置说明
# SDK Client Configuration Guide

## 概述

此目录包含 isA Cloud 平台所有 SDK 的客户端配置文件。这些配置供**开发者**在应用程序中使用 SDK 时参考。

## 配置文件列表

| 文件 | SDK | 用途 |
|------|-----|------|
| `minio.yaml` | MinIO SDK | 对象存储客户端配置 |
| `duckdb.yaml` | DuckDB SDK | 分析数据库客户端配置 |
| `mqtt.yaml` | MQTT SDK | IoT 消息代理客户端配置 |
| `loki.yaml` | Loki SDK | 日志聚合客户端配置 |
| `redis.yaml` | Redis SDK | 缓存客户端配置 |
| `nats.yaml` | NATS SDK | 事件总线客户端配置 |

## 使用方法

### 方法 1：直接使用配置文件

```go
import "gopkg.in/yaml.v2"

// 读取配置文件
data, _ := ioutil.ReadFile("configs/sdk/loki.yaml")
var cfg loki.Config
yaml.Unmarshal(data, &cfg)

// 创建客户端
client, _ := loki.NewClient(&cfg)
```

### 方法 2：环境变量覆盖

每个 SDK 都支持通过环境变量覆盖配置：

```bash
# Loki
export ISA_CLOUD_LOKI_URL="http://loki.example.com:3100"
export ISA_CLOUD_LOKI_TENANT_ID="production"

# MQTT
export ISA_CLOUD_MQTT_BROKER_URL="ssl://mqtt.example.com:8883"
export ISA_CLOUD_MQTT_USERNAME="myuser"
export ISA_CLOUD_MQTT_PASSWORD="mypass"
```

### 方法 3：程序中直接配置

```go
cfg := &loki.Config{
    URL:       "http://localhost:3100",
    BatchSize: 100,
    BatchWait: 1 * time.Second,
}
client, _ := loki.NewClient(cfg)
```

## 配置示例

完整的环境配置示例请参考 `configs/examples/` 目录：

- `development.yaml` - 开发环境配置
- `production.yaml` - 生产环境配置
- `with-consul.yaml` - 使用 Consul 服务发现的配置

## 与服务配置的区别

| 配置类型 | 目录 | 用途 | 使用者 |
|---------|------|------|--------|
| **SDK 客户端配置** | `configs/sdk/` | 应用程序中使用 SDK | 开发者 |
| **服务部署配置** | `deployments/configs/services/` | 部署和运行服务 | 运维人员 |

## 相关文档

- [Loki SDK 文档](../../pkg/infrastructure/logging/loki/README.md)
- [MQTT SDK 文档](../../pkg/infrastructure/messaging/mqtt/README.md)
- [使用示例](../../examples/README.md)
- [统一基础设施 SDK](../../docs/UNIFIED_INFRASTRUCTURE_SDK.md)

