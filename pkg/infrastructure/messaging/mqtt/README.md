# MQTT SDK - IoT 消息代理客户端

## 概述

MQTT SDK 为 isA Cloud 平台提供了统一的 MQTT 消息代理客户端封装，专为 IoT 设备通信和实时数据传输设计。

**文件名：** `pkg/infrastructure/messaging/mqtt/README.md`

## 功能特性

- ✅ **发布/订阅** - 标准的 MQTT Pub/Sub 模式
- ✅ **主题通配符** - 支持 `+` 和 `#` 通配符
- ✅ **QoS 支持** - 支持 QoS 0, 1, 2 三种级别
- ✅ **自动重连** - 连接断开后自动重连
- ✅ **保留消息** - 支持消息保留功能
- ✅ **遗嘱消息** - 支持 Last Will and Testament
- ✅ **TLS 加密** - 支持 TLS/SSL 连接
- ✅ **批量订阅** - 支持一次订阅多个主题

## 安装

```bash
go get github.com/isa-cloud/isa_cloud/pkg/infrastructure/messaging/mqtt
```

## 快速开始

### 1. 创建客户端

```go
package main

import (
    "fmt"
    "log"
    
    "github.com/isa-cloud/isa_cloud/pkg/infrastructure/messaging/mqtt"
)

func main() {
    // 创建配置
    cfg := &mqtt.Config{
        BrokerURL:     "tcp://localhost:1883",
        ClientID:      "my-app",
        Username:      "user",
        Password:      "pass",
        QoS:           1,
        AutoReconnect: true,
    }
    
    // 创建客户端
    client, err := mqtt.NewClient(cfg)
    if err != nil {
        log.Fatal(err)
    }
    defer client.Close()
    
    // 使用客户端...
}
```

### 2. 发布消息

```go
// 发布字符串消息
err := client.Publish("sensors/room1/temperature", "25.5", false)

// 发布字节消息
data := []byte("Hello MQTT")
err := client.Publish("devices/status", data, false)

// 发布 JSON 对象（自动序列化）
status := map[string]interface{}{
    "device_id": "dev123",
    "status":    "online",
    "timestamp": time.Now().Unix(),
}
err := client.Publish("devices/dev123/status", status, false)

// 发布保留消息
err := client.Publish("sensors/room1/config", "config-data", true)
```

### 3. 订阅消息

```go
// 订阅单个主题
err := client.Subscribe("sensors/room1/temperature", func(topic string, payload []byte) error {
    fmt.Printf("Received on %s: %s\n", topic, string(payload))
    return nil
})

// 使用通配符订阅多个设备
err := client.Subscribe("devices/+/telemetry", func(topic string, payload []byte) error {
    deviceID := mqtt.ExtractDeviceID(topic)
    fmt.Printf("Device %s data: %s\n", deviceID, string(payload))
    return nil
})

// 订阅所有子主题
err := client.Subscribe("sensors/#", func(topic string, payload []byte) error {
    fmt.Printf("Sensor data on %s: %s\n", topic, string(payload))
    return nil
})
```

### 4. 批量订阅

```go
// 订阅多个主题，不同 QoS
filters := map[string]byte{
    "sensors/+/temp":   1,  // QoS 1
    "sensors/+/humid":  1,  // QoS 1
    "devices/+/status": 2,  // QoS 2
}

err := client.SubscribeMultiple(filters, func(topic string, payload []byte) error {
    fmt.Printf("Multi-sub received: %s = %s\n", topic, string(payload))
    return nil
})
```

### 5. 取消订阅

```go
err := client.Unsubscribe("sensors/room1/temperature", "devices/+/telemetry")
```

## 配置选项

### Config 结构

```go
type Config struct {
    // 基础配置
    BrokerURL     string        // MQTT Broker 地址，如 "tcp://localhost:1883"
    ClientID      string        // 客户端 ID（必须唯一）
    Username      string        // 用户名（可选）
    Password      string        // 密码（可选）
    
    // 连接配置
    KeepAlive     time.Duration // 心跳间隔（默认：60s）
    PingTimeout   time.Duration // Ping 超时（默认：10s）
    CleanSession  bool          // 是否清除会话（默认：false）
    AutoReconnect bool          // 是否自动重连（默认：true）
    QoS           byte          // 默认 QoS（0, 1, 2）
    
    // TLS 配置
    TLSEnabled    bool          // 是否启用 TLS
    TLSCert       string        // 证书文件路径
    TLSKey        string        // 密钥文件路径
    TLSCA         string        // CA 证书路径
    
    // 遗嘱消息配置
    WillEnabled   bool          // 是否启用遗嘱消息
    WillTopic     string        // 遗嘱主题
    WillPayload   string        // 遗嘱内容
    WillQoS       byte          // 遗嘱 QoS
    WillRetain    bool          // 遗嘱保留
}
```

### 示例配置

```go
cfg := &mqtt.Config{
    BrokerURL:     "tcp://broker.example.com:1883",
    ClientID:      "isa-cloud-gateway",
    Username:      "mqtt_user",
    Password:      "mqtt_pass",
    KeepAlive:     60 * time.Second,
    PingTimeout:   10 * time.Second,
    CleanSession:  true,
    AutoReconnect: true,
    QoS:           1,
    
    // 遗嘱消息
    WillEnabled: true,
    WillTopic:   "devices/gateway/status",
    WillPayload: "offline",
    WillQoS:     1,
    WillRetain:  true,
}
```

## QoS 级别详解

MQTT 提供三种服务质量级别：

### QoS 0 - 最多一次（At most once）

```go
// 不保证消息送达，可能丢失
client.PublishWithQoS("sensors/temp", "25.5", 0, false)
```

**适用场景：**
- 传感器数据（可容忍偶尔丢失）
- 实时状态更新

### QoS 1 - 至少一次（At least once）

```go
// 保证消息送达，但可能重复
client.PublishWithQoS("commands/execute", data, 1, false)
```

**适用场景：**
- 一般消息传递
- 命令执行（幂等操作）

### QoS 2 - 恰好一次（Exactly once）

```go
// 保证消息恰好送达一次，无重复
client.PublishWithQoS("payments/transaction", data, 2, false)
```

**适用场景：**
- 关键业务数据
- 金融交易
- 不能重复执行的操作

## 主题通配符

### 单级通配符 `+`

匹配单个层级：

```go
// 匹配: sensors/room1/temp, sensors/room2/temp
client.Subscribe("sensors/+/temp", handler)

// 匹配: devices/dev1/telemetry, devices/dev2/telemetry
client.Subscribe("devices/+/telemetry", handler)
```

### 多级通配符 `#`

匹配多个层级（必须在最后）：

```go
// 匹配所有 sensors 下的主题
client.Subscribe("sensors/#", handler)

// 匹配: sensors/room1/temp, sensors/room1/humid, sensors/room1/light/level
```

### 组合使用

```go
// 匹配: building1/floor2/room3/temp
client.Subscribe("building1/+/+/temp", handler)

// 匹配: home/living_room/temp, home/bedroom/humid/level1
client.Subscribe("home/+/#", handler)
```

## 高级用法

### 1. TLS/SSL 连接

```go
cfg := &mqtt.Config{
    BrokerURL:  "ssl://broker.example.com:8883",
    ClientID:   "secure-client",
    TLSEnabled: true,
    TLSCert:    "/path/to/client.crt",
    TLSKey:     "/path/to/client.key",
    TLSCA:      "/path/to/ca.crt",
}

client, err := mqtt.NewClient(cfg)
```

### 2. 遗嘱消息（Last Will and Testament）

```go
cfg := &mqtt.Config{
    BrokerURL:   "tcp://localhost:1883",
    ClientID:    "iot-device-1",
    
    // 设备断开时自动发送此消息
    WillEnabled: true,
    WillTopic:   "devices/iot-device-1/status",
    WillPayload: `{"status": "offline", "timestamp": "2024-10-10T10:30:00Z"}`,
    WillQoS:     1,
    WillRetain:  true,
}
```

### 3. 保留消息（Retained Messages）

```go
// 发布保留消息 - 新订阅者会立即收到最后一条消息
client.Publish("devices/config", `{"refresh_rate": 60}`, true)

// 删除保留消息 - 发送空消息
client.Publish("devices/config", "", true)
```

### 4. 连接管理

```go
// 检查连接状态
if client.IsConnected() {
    fmt.Println("Connected to broker")
}

// 手动重连
err := client.Reconnect()
if err != nil {
    log.Printf("Reconnect failed: %v", err)
}

// 获取统计信息
stats := client.GetStats()
fmt.Printf("Connected: %v\n", stats["connected"])
fmt.Printf("Subscribed topics: %v\n", stats["subscribed_topics"])
```

### 5. 从主题中提取信息

```go
// 提取设备 ID
topic := "devices/dev123/telemetry"
deviceID := mqtt.ExtractDeviceID(topic)
// 返回: "dev123"

// 提取主题各部分
parts := mqtt.ExtractTopicParts("sensors/room1/temperature")
// 返回: ["sensors", "room1", "temperature"]
```

## 实际应用场景

### 场景 1: IoT 设备遥测

```go
// 设备端 - 发送遥测数据
telemetry := map[string]interface{}{
    "temperature": 25.5,
    "humidity":    60.0,
    "timestamp":   time.Now().Unix(),
}
client.Publish("devices/sensor001/telemetry", telemetry, false)

// 服务端 - 接收遥测数据
client.Subscribe("devices/+/telemetry", func(topic string, payload []byte) error {
    deviceID := mqtt.ExtractDeviceID(topic)
    
    var data map[string]interface{}
    json.Unmarshal(payload, &data)
    
    log.Printf("Device %s: temp=%.1f, humid=%.1f",
        deviceID, data["temperature"], data["humidity"])
    
    return nil
})
```

### 场景 2: 设备命令控制

```go
// 服务端 - 发送命令
command := map[string]interface{}{
    "action": "update_config",
    "params": map[string]interface{}{
        "refresh_rate": 30,
    },
}
client.PublishWithQoS("devices/sensor001/commands", command, 2, false)

// 设备端 - 接收命令
client.SubscribeWithQoS("devices/sensor001/commands", 2, func(topic string, payload []byte) error {
    var cmd map[string]interface{}
    json.Unmarshal(payload, &cmd)
    
    // 执行命令
    action := cmd["action"].(string)
    switch action {
    case "update_config":
        // 更新配置
    case "restart":
        // 重启设备
    }
    
    return nil
})
```

### 场景 3: 实时状态监控

```go
// 所有设备定期发送状态
client.Publish("devices/sensor001/status", `{"status":"online","battery":85}`, true)

// 监控中心订阅所有设备状态
client.Subscribe("devices/+/status", func(topic string, payload []byte) error {
    deviceID := mqtt.ExtractDeviceID(topic)
    
    var status map[string]interface{}
    json.Unmarshal(payload, &status)
    
    // 更新数据库或仪表盘
    updateDeviceStatus(deviceID, status)
    
    return nil
})
```

### 场景 4: 多层次建筑监控

```go
// 订阅整栋建筑的所有传感器
client.Subscribe("building1/#", func(topic string, payload []byte) error {
    parts := mqtt.ExtractTopicParts(topic)
    // parts: ["building1", "floor2", "room3", "temperature"]
    
    building := parts[0]
    floor := parts[1]
    room := parts[2]
    sensorType := parts[3]
    
    log.Printf("%s/%s/%s - %s: %s", building, floor, room, sensorType, string(payload))
    return nil
})
```

## 性能优化

### 1. 连接池（多客户端）

```go
// 为不同用途创建不同客户端
publisherClient, _ := mqtt.NewClient(publisherConfig)
subscriberClient, _ := mqtt.NewClient(subscriberConfig)

// 发布使用 publisherClient
publisherClient.Publish("topic", data, false)

// 订阅使用 subscriberClient
subscriberClient.Subscribe("topic", handler)
```

### 2. QoS 选择

```go
// 高频实时数据 - 使用 QoS 0
client.PublishWithQoS("sensors/temp", data, 0, false)

// 一般消息 - 使用 QoS 1
client.PublishWithQoS("commands/execute", data, 1, false)

// 关键消息 - 使用 QoS 2
client.PublishWithQoS("transactions/payment", data, 2, false)
```

### 3. 批量处理

```go
// 使用 goroutine 并发处理消息
client.Subscribe("devices/+/telemetry", func(topic string, payload []byte) error {
    go func() {
        // 异步处理
        processData(payload)
    }()
    return nil
})
```

## 故障排查

### 问题 1: 连接失败

```go
// 检查 Broker URL 格式
cfg.BrokerURL = "tcp://localhost:1883"  // 正确
cfg.BrokerURL = "mqtt://localhost:1883" // 错误

// 检查连接状态
if !client.IsConnected() {
    log.Println("Not connected to broker")
}
```

### 问题 2: 消息未收到

```go
// 确保使用了正确的 QoS
client.SubscribeWithQoS("topic", 1, handler)

// 检查主题通配符
client.Subscribe("devices/+/telemetry", handler)  // 正确
client.Subscribe("devices/*/telemetry", handler)  // 错误（* 不是有效通配符）
```

### 问题 3: 重复消息

```go
// QoS 1 可能产生重复，需要在应用层去重
var processedMsgIDs sync.Map

client.Subscribe("topic", func(topic string, payload []byte) error {
    msgID := extractMessageID(payload)
    if _, exists := processedMsgIDs.LoadOrStore(msgID, true); exists {
        return nil // 重复消息，跳过
    }
    
    // 处理消息
    return nil
})
```

## 最佳实践

1. **使用唯一的客户端 ID** - 避免多个客户端使用相同 ID
2. **合理选择 QoS** - 根据场景选择合适的 QoS 级别
3. **使用保留消息** - 用于配置和状态信息
4. **设置遗嘱消息** - 让系统知道设备异常断开
5. **主题命名规范** - 使用层次结构，便于通配符订阅
6. **优雅断开** - 使用 `Close()` 而不是直接终止进程

## 主题命名规范建议

```go
// 好的命名方式
"devices/sensor001/telemetry"
"building1/floor2/room3/temperature"
"commands/device123/restart"

// 避免的命名方式
"sensor001"                    // 缺乏层次
"devices_sensor001_telemetry"  // 使用下划线而非斜杠
"temp/building1"               // 顺序不合理
```

## 示例项目

完整示例请参考：`examples/python/mqtt_client_example.go`

## 相关文档

- [MQTT 协议规范](https://mqtt.org/mqtt-specification/)
- [Eclipse Paho MQTT Go](https://github.com/eclipse/paho.mqtt.golang)
- [isA Cloud 统一基础设施 SDK](../../docs/UNIFIED_INFRASTRUCTURE_SDK.md)

## 支持

如有问题或建议，请联系 isA Cloud 开发团队。



