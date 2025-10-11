# NATS SDK 客户端

为 isA Cloud 平台提供统一的 NATS 事件总线客户端封装。

## 功能特性

### 核心操作
- ✅ **Pub/Sub**: Publish, Subscribe, QueueSubscribe
- ✅ **请求/响应**: Request (同步 RPC)
- ✅ **JetStream**: 持久化消息流
- ✅ **流管理**: CreateStream, DeleteStream, GetStreamInfo
- ✅ **消费者管理**: CreateConsumer, PullMessages, AckMessage
- ✅ **键值存储**: KV Put, Get, Delete
- ✅ **对象存储**: Object Put, Get, List

### 高级功能
- ✅ **队列组**: 负载均衡的消息分发
- ✅ **通配符订阅**: 支持 `*` 和 `>` 通配符
- ✅ **自动重连**: 网络故障自动恢复
- ✅ **消息确认**: 显式确认机制
- ✅ **持久化消费者**: Durable Consumers
- ✅ **Consul 服务发现**: 自动发现 NATS 集群

## 快速开始

### 安装

```bash
go get github.com/nats-io/nats.go
```

### 基础用法

```go
package main

import (
    "context"
    "log"

    "github.com/isa-cloud/isa_cloud/pkg/infrastructure/event/nats"
)

func main() {
    // 创建客户端配置
    cfg := &nats.Config{
        URLs:             []string{"nats://localhost:4222"},
        ClusterID:        "isa-cloud-cluster",
        JetStreamEnabled: true,
    }

    // 创建客户端
    client, err := nats.NewClient(cfg)
    if err != nil {
        log.Fatal(err)
    }
    defer client.Close()

    ctx := context.Background()

    // 发布事件
    err = client.Publish(ctx, "events.user.created", []byte(`{"user_id":"123"}`))
    if err != nil {
        log.Fatal(err)
    }

    // 订阅事件
    sub, err := client.Subscribe(ctx, "events.>", func(msg *nats.Message) error {
        log.Printf("Received: %s = %s", msg.Subject, string(msg.Data))
        return nil
    })
    if err != nil {
        log.Fatal(err)
    }
    defer sub.Unsubscribe()
}
```

### 使用配置文件

```go
import "github.com/isa-cloud/isa_cloud/pkg/infrastructure/event"

// 从配置文件加载
factory, err := event.NewEventClientFactory()
if err != nil {
    log.Fatal(err)
}

// 创建 NATS 客户端（自动 Consul 发现）
client, err := factory.NewNATSClient(context.Background())
if err != nil {
    log.Fatal(err)
}
defer client.Close()
```

## 详细示例

### 1. 基础 Pub/Sub

```go
ctx := context.Background()

// 发布事件
client.Publish(ctx, "events.order.created", []byte(`{"order_id":"123"}`))

// 订阅所有事件
client.Subscribe(ctx, "events.>", func(msg *nats.Message) error {
    log.Printf("Event: %s", msg.Subject)
    return nil
})

// 订阅特定事件
client.Subscribe(ctx, "events.order.*", func(msg *nats.Message) error {
    // 处理订单事件
    return nil
})
```

### 2. 队列组（负载均衡）

```go
// 多个工作节点订阅同一队列组
// 每条消息只会被一个节点处理

// Worker 1
client.QueueSubscribe(ctx, "work.tasks", "workers", func(msg *nats.Message) error {
    log.Printf("Worker 1 processing: %s", string(msg.Data))
    return nil
})

// Worker 2
client.QueueSubscribe(ctx, "work.tasks", "workers", func(msg *nats.Message) error {
    log.Printf("Worker 2 processing: %s", string(msg.Data))
    return nil
})

// 发布任务（会被任意一个 worker 处理）
client.Publish(ctx, "work.tasks", []byte("task1"))
```

### 3. 请求/响应模式（同步 RPC）

```go
// 服务端：响应请求
client.Subscribe(ctx, "service.ping", func(msg *nats.Message) error {
    // 处理请求并回复
    response := []byte("pong")
    return client.PublishWithReply(ctx, msg.Reply, "", response)
})

// 客户端：发送请求
response, err := client.Request(ctx, "service.ping", []byte("hello"), 5*time.Second)
if err != nil {
    log.Fatal(err)
}
log.Printf("Response: %s", string(response.Data))
```

### 4. JetStream 持久化流

```go
// 创建流
stream, err := client.CreateStream(ctx, &jetstream.StreamConfig{
    Name:     "ORDERS",
    Subjects: []string{"orders.>"},
    MaxAge:   30 * 24 * time.Hour, // 保留 30 天
})

// 发布到流
ack, err := client.PublishToStream(ctx, "orders.created", []byte(`{"order_id":"123"}`))
log.Printf("Published with sequence: %d", ack.Sequence)

// 创建消费者
consumer, err := client.CreateConsumer(ctx, "ORDERS", &jetstream.ConsumerConfig{
    Name:          "order-processor",
    FilterSubject: "orders.created",
    AckPolicy:     jetstream.AckExplicitPolicy,
})
```

### 5. 键值存储

```go
// 创建 KV 存储
kv, err := client.CreateKeyValue(ctx, "config")

// 设置键值
_, err = kv.Put(ctx, "feature.flag", []byte("enabled"))

// 获取键值
entry, err := kv.Get(ctx, "feature.flag")
log.Printf("Value: %s", string(entry.Value()))

// 删除键
err = kv.Delete(ctx, "feature.flag")
```

### 6. 对象存储

```go
// 创建对象存储
objStore, err := client.CreateObjectStore(ctx, "artifacts")

// 存储对象
_, err = objStore.PutBytes(ctx, "report.pdf", pdfData)

// 获取对象
obj, err := objStore.Get(ctx, "report.pdf")
data, _ := io.ReadAll(obj)

// 列出对象
objects, _ := objStore.List(ctx)
for obj := range objects {
    log.Printf("Object: %s (%d bytes)", obj.Name, obj.Size)
}
```

## 配置选项

### 配置文件 (configs/sdk/nats.yaml)

```yaml
# 基础配置
urls:
  - "nats://localhost:4222"
cluster_id: "isa-cloud-cluster"

# Consul 服务发现
use_consul: true
service_name: "nats-service"
grpc_port: 50056

# 连接配置
max_reconnect: 10
reconnect_wait: "2s"
timeout: "10s"
ping_interval: "2m"
max_pings_out: 2

# JetStream
jetstream_enabled: true
jetstream_domain: ""

# 认证
username: ""
password: ""
token: ""

# TLS
tls_enabled: false
```

### 环境变量

```bash
export ISA_CLOUD_NATS_URLS="nats://server1:4222,nats://server2:4222"
export ISA_CLOUD_NATS_USERNAME="admin"
export ISA_CLOUD_NATS_PASSWORD="password"
export ISA_CLOUD_NATS_USE_CONSUL=true
```

## 实际应用场景

### 微服务间事件通信

```go
// 用户服务：发布用户创建事件
userEvent := map[string]interface{}{
    "user_id": "123",
    "email": "user@example.com",
    "timestamp": time.Now(),
}
data, _ := json.Marshal(userEvent)
client.Publish(ctx, "events.user.created", data)

// 邮件服务：订阅用户创建事件
client.Subscribe(ctx, "events.user.created", func(msg *nats.Message) error {
    var event map[string]interface{}
    json.Unmarshal(msg.Data, &event)
    
    // 发送欢迎邮件
    sendWelcomeEmail(event["email"].(string))
    return nil
})
```

### 异步任务队列

```go
// 生产者：提交任务
for i := 0; i < 100; i++ {
    task := fmt.Sprintf("task-%d", i)
    client.Publish(ctx, "work.tasks", []byte(task))
}

// 消费者：处理任务（多个消费者负载均衡）
client.QueueSubscribe(ctx, "work.tasks", "task-workers", func(msg *nats.Message) error {
    log.Printf("Processing: %s", string(msg.Data))
    time.Sleep(1 * time.Second) // 模拟工作
    return nil
})
```

### 配置中心（使用 KV）

```go
kv, _ := client.GetKeyValue(ctx, "app-config")

// 设置配置
kv.Put(ctx, "database.url", []byte("postgres://..."))
kv.Put(ctx, "api.timeout", []byte("30s"))

// 读取配置
entry, _ := kv.Get(ctx, "database.url")
dbURL := string(entry.Value())

// 监听配置变化
watcher, _ := kv.Watch(ctx, "api.>")
for update := range watcher.Updates() {
    if update != nil {
        log.Printf("Config changed: %s = %s", update.Key(), string(update.Value()))
    }
}
```

### 文件分发（使用 Object Store）

```go
objStore, _ := client.GetObjectStore(ctx, "releases")

// 上传新版本
version := "v1.2.3"
binary, _ := os.ReadFile("app-v1.2.3.bin")
objStore.PutBytes(ctx, version, binary)

// 各节点下载更新
obj, _ := objStore.Get(ctx, version)
data, _ := io.ReadAll(obj)
os.WriteFile("app.bin", data, 0755)
```

## 通配符说明

- `*` - 匹配单个 token
  - `events.user.*` 匹配 `events.user.created`, `events.user.updated`
  
- `>` - 匹配一个或多个 tokens
  - `events.>` 匹配 `events.user.created`, `events.order.shipped.confirmed`

## Consul 服务发现

当启用 Consul 时，客户端会自动发现 NATS 集群：

```yaml
use_consul: true
service_name: "nats-service"
```

工作流程：
1. 查询 Consul 获取所有健康的 NATS 节点
2. 自动连接到发现的节点
3. 支持 NATS 集群的高可用
4. 如果 Consul 不可用，回退到配置的 URLs

## 性能优化建议

1. **使用队列组**: 多个消费者负载均衡
2. **批量发布**: 减少网络往返
3. **使用 JetStream**: 重要消息需要持久化
4. **合理设置 AckWait**: 平衡可靠性和性能
5. **使用通配符订阅**: 减少订阅数量
6. **消息大小控制**: 避免发送过大消息

## 故障排查

### 连接失败
```bash
# 检查 NATS 服务
nats-server --version

# 测试连接
nats pub test "hello"

# 检查 Consul 服务发现
curl http://localhost:8500/v1/health/service/nats-service
```

### JetStream 问题
```go
// 检查 JetStream 状态
if !client.IsConnected() {
    log.Fatal("Not connected to NATS")
}
```

## 相关文档

- [NATS 官方文档](https://docs.nats.io/)
- [JetStream 文档](https://docs.nats.io/nats-concepts/jetstream)
- [统一基础设施 SDK](../../../docs/UNIFIED_INFRASTRUCTURE_SDK.md)
- [Consul 集成](../../../docs/CONSUL_INTEGRATION_SUMMARY.md)

## 最佳实践

1. **使用 JetStream 持久化重要消息**
2. **队列组实现负载均衡**
3. **合理设置流的保留策略**
4. **使用持久化消费者保证消费进度**
5. **显式确认消息（AckExplicit）**
6. **监控流和消费者状态**
7. **使用通配符简化订阅管理**
8. **设置合理的重试次数和超时**



