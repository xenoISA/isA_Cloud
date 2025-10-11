# Loki SDK - 日志聚合客户端

## 概述

Loki SDK 为 isA Cloud 平台提供了统一的日志聚合客户端封装，支持日志推送、查询和管理功能。

**文件名：** `pkg/infrastructure/logging/loki/README.md`

## 功能特性

- ✅ **日志推送** - 支持单条和批量日志推送
- ✅ **自动批处理** - 自动批量发送以提高性能
- ✅ **日志查询** - 支持 LogQL 查询语言
- ✅ **标签管理** - 支持静态和动态标签
- ✅ **健康检查** - 内置健康检查功能
- ✅ **重试机制** - 自动重试失败的请求
- ✅ **多租户支持** - 支持多租户模式

## 安装

```bash
go get github.com/isa-cloud/isa_cloud/pkg/infrastructure/logging/loki
```

## 快速开始

### 1. 创建客户端

```go
package main

import (
    "log"
    "time"
    
    "github.com/isa-cloud/isa_cloud/pkg/infrastructure/logging/loki"
)

func main() {
    // 创建配置
    cfg := &loki.Config{
        URL:       "http://localhost:3100",
        BatchSize: 100,
        BatchWait: 1 * time.Second,
        TenantID:  "tenant-1",
    }
    
    // 创建客户端
    client, err := loki.NewClient(cfg)
    if err != nil {
        log.Fatal(err)
    }
    defer client.Close()
    
    // 使用客户端...
}
```

### 2. 推送日志

```go
// 推送单条日志（简化接口）
err := client.PushLog("mcp", loki.LogLevelInfo, "User logged in", map[string]string{
    "user_id": "123",
    "action":  "login",
})

// 推送结构化日志
entry := loki.LogEntry{
    Timestamp: time.Now(),
    Line:      "Application started successfully",
    Labels: map[string]string{
        "app":     "mcp",
        "level":   "info",
        "service": "auth",
        "version": "1.0.0",
    },
}
err := client.Push(entry)
```

### 3. 批量推送

```go
entries := []loki.LogEntry{
    {
        Timestamp: time.Now(),
        Line:      "Request received",
        Labels:    map[string]string{"app": "mcp", "level": "info"},
    },
    {
        Timestamp: time.Now(),
        Line:      "Processing request",
        Labels:    map[string]string{"app": "mcp", "level": "debug"},
    },
}

err := client.PushBatch(entries)
```

### 4. 查询日志

```go
// 查询最近的错误日志
results, err := client.Query(
    `{app="mcp", level="error"}`,
    loki.QueryOptions{
        Start:     time.Now().Add(-1 * time.Hour),
        End:       time.Now(),
        Limit:     100,
        Direction: "backward",
    },
)

// 遍历结果
for _, result := range results {
    fmt.Printf("Labels: %v\n", result.Labels)
    for _, line := range result.Lines {
        fmt.Printf("  [%s] %s\n", line.Timestamp, line.Line)
    }
}
```

## 配置选项

### Config 结构

```go
type Config struct {
    // 基础配置
    URL          string            // Loki 服务地址，如 "http://localhost:3100"
    TenantID     string            // 租户 ID（多租户模式）
    
    // 认证配置
    Username     string            // 基础认证用户名
    Password     string            // 基础认证密码
    
    // 批处理配置
    BatchSize    int               // 批量发送大小（默认：100）
    BatchWait    time.Duration     // 批量等待时间（默认：1s）
    Timeout      time.Duration     // 请求超时时间（默认：10s）
    
    // 重试配置
    MaxRetries   int               // 最大重试次数（默认：3）
    RetryWait    time.Duration     // 重试等待时间（默认：1s）
    
    // 标签配置
    StaticLabels map[string]string // 静态标签（所有日志都会带上）
}
```

### 示例配置

```go
cfg := &loki.Config{
    URL:       "http://localhost:3100",
    TenantID:  "my-tenant",
    Username:  "admin",
    Password:  "secret",
    BatchSize: 200,
    BatchWait: 2 * time.Second,
    Timeout:   15 * time.Second,
    MaxRetries: 5,
    RetryWait:  2 * time.Second,
    StaticLabels: map[string]string{
        "environment": "production",
        "region":      "us-west-2",
    },
}
```

## 高级用法

### 1. 标签策略

```go
// 静态标签 - 在创建客户端时设置，所有日志都会带上
cfg.StaticLabels = map[string]string{
    "app":         "mcp",
    "environment": "prod",
    "cluster":     "us-west-2",
}

// 动态标签 - 在推送日志时设置
client.PushLog("mcp", loki.LogLevelInfo, "Request processed", map[string]string{
    "request_id":  "req-123",
    "user_id":     "user-456",
    "duration_ms": "145",
})
```

### 2. 查询标签信息

```go
// 查询可用的标签
labels, err := client.QueryLabels(
    time.Now().Add(-24*time.Hour),
    time.Now(),
)
for _, label := range labels {
    fmt.Println("Label:", label)
}

// 查询标签的可能值
values, err := client.QueryLabelValues(
    "app",
    time.Now().Add(-24*time.Hour),
    time.Now(),
)
// 返回: ["mcp", "model", "agent"]
```

### 3. 健康检查

```go
import "context"

ctx := context.Background()
err := client.HealthCheck(ctx)
if err != nil {
    log.Printf("Loki health check failed: %v", err)
} else {
    log.Println("Loki is healthy")
}
```

### 4. 获取统计信息

```go
stats := client.GetStats()
fmt.Printf("Buffer size: %v\n", stats["buffer_size"])
fmt.Printf("Batch size: %v\n", stats["batch_size"])
fmt.Printf("Static labels: %v\n", stats["static_labels"])
```

### 5. 手动刷新缓冲区

```go
// 在关闭应用前手动刷新所有缓冲的日志
err := client.Flush()
if err != nil {
    log.Printf("Failed to flush logs: %v", err)
}
```

## LogQL 查询示例

### 基础查询

```go
// 查询特定应用的日志
`{app="mcp"}`

// 查询特定级别的日志
`{app="mcp", level="error"}`

// 查询多个服务
`{app=~"mcp|model|agent"}`
```

### 过滤查询

```go
// 包含特定文本
`{app="mcp"} |= "error"`

// 不包含特定文本
`{app="mcp"} != "debug"`

// 正则表达式匹配
`{app="mcp"} |~ "user_id=[0-9]+"`
```

### 聚合查询

```go
// 统计日志数量
`count_over_time({app="mcp"}[5m])`

// 按级别聚合
`sum by (level) (count_over_time({app="mcp"}[1h]))`
```

## 日志级别

SDK 定义了标准的日志级别：

```go
const (
    LogLevelDebug LogLevel = "debug"
    LogLevelInfo  LogLevel = "info"
    LogLevelWarn  LogLevel = "warn"
    LogLevelError LogLevel = "error"
    LogLevelFatal LogLevel = "fatal"
)
```

使用示例：

```go
client.PushLog("mcp", loki.LogLevelDebug, "Detailed debug info", nil)
client.PushLog("mcp", loki.LogLevelInfo, "Normal operation", nil)
client.PushLog("mcp", loki.LogLevelWarn, "Warning message", nil)
client.PushLog("mcp", loki.LogLevelError, "Error occurred", nil)
client.PushLog("mcp", loki.LogLevelFatal, "Fatal error", nil)
```

## 性能优化

### 1. 批处理配置

```go
// 高吞吐量场景
cfg.BatchSize = 500
cfg.BatchWait = 5 * time.Second

// 低延迟场景
cfg.BatchSize = 50
cfg.BatchWait = 500 * time.Millisecond
```

### 2. 异步推送

SDK 内部已经实现了异步批处理，无需手动处理。

### 3. 标签优化

```go
// 好的标签策略 - 使用低基数标签
labels := map[string]string{
    "app":         "mcp",
    "environment": "prod",
    "level":       "error",
}

// 避免高基数标签（如用户 ID、请求 ID）直接作为标签
// 应该将这些信息放在日志内容中
message := fmt.Sprintf("Request failed: user_id=%s, request_id=%s", userID, reqID)
```

## 与 Grafana 集成

### 1. 在 Grafana 中添加 Loki 数据源

1. 打开 Grafana
2. 进入 Configuration → Data Sources
3. 添加 Loki 数据源
4. 配置 URL: `http://localhost:3100`

### 2. 创建仪表盘

```logql
# 错误日志面板
{app="mcp", level="error"}

# 请求速率面板
rate({app="mcp"}[5m])

# Top 错误消息
topk(10, sum by (message) (count_over_time({app="mcp", level="error"}[1h])))
```

## 故障排查

### 问题 1: 连接失败

```go
// 检查 Loki URL 是否正确
cfg.URL = "http://localhost:3100"  // 确保端口正确

// 检查健康状态
err := client.HealthCheck(context.Background())
```

### 问题 2: 日志未显示

```go
// 手动刷新缓冲区
client.Flush()

// 检查批处理配置
cfg.BatchSize = 10  // 降低批处理大小以更快看到结果
cfg.BatchWait = 1 * time.Second
```

### 问题 3: 认证失败

```go
// 多租户模式
cfg.TenantID = "my-tenant"

// 基础认证
cfg.Username = "admin"
cfg.Password = "password"
```

## 最佳实践

1. **使用静态标签** - 为所有日志设置通用标签
2. **标签基数控制** - 避免使用高基数值作为标签
3. **批处理优化** - 根据场景调整批处理大小
4. **结构化日志** - 使用 JSON 格式的日志内容
5. **优雅关闭** - 确保在程序退出前调用 `Close()`

## 示例项目

完整示例请参考：`examples/python/loki_client_example.go`

## 相关文档

- [Loki 官方文档](https://grafana.com/docs/loki/)
- [LogQL 查询语言](https://grafana.com/docs/loki/latest/logql/)
- [isA Cloud 统一基础设施 SDK](../../docs/UNIFIED_INFRASTRUCTURE_SDK.md)

## 支持

如有问题或建议，请联系 isA Cloud 开发团队。



