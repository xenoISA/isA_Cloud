# MQTT Client Adapter 使用指南

## 📋 概述

MQTT Client Adapter 是 isA_Cloud 平台的**协议转换层**，实现了 **MQTT ↔ HTTP/gRPC** 的双向桥接，替代了原有的 Gateway MQTT Adapter。

### 核心功能

✅ **gRPC Stream 订阅** - 实时推送 MQTT 设备消息到 Python 微服务  
✅ **Webhook 回调** - HTTP POST 回调机制，支持自定义认证和签名  
✅ **设备消息分类** - 自动识别 telemetry、status、auth 等消息类型  
✅ **灵活过滤** - 支持按设备 ID、消息类型、topic 模式过滤

---

## 🏗️ 架构设计

### 消息流向

**设备 → 服务**：
\`\`\`
IoT Device → MQTT Broker → mqtt-service (订阅) → gRPC Stream/Webhook → Python Service
\`\`\`

**服务 → 设备**：
\`\`\`
Python Service → gRPC RPC → mqtt-service (发布) → MQTT Broker → IoT Device
\`\`\`

---

## 🚀 快速开始

### 基础连接

\`\`\`python
from isa_common import MQTTClient

# 初始化客户端
client = MQTTClient(
    host='localhost',
    port=50053,
    user_id='your_user_id',
    lazy_connect=False  # 立即连接
)

# 健康检查
health = client.health_check()
print(f"MQTT Service: {health['healthy']}")
\`\`\`

---

## 📡 方式一：gRPC Stream 订阅（推荐）

### 特点

- ✅ **实时性高** - 消息即时推送，延迟 < 100ms
- ✅ **性能好** - 单连接支持高并发，无需轮询
- ⚠️ **长连接** - 需要保持连接活跃

### 使用方法

\`\`\`python
from isa_common import MQTTClient

client = MQTTClient(host='localhost', port=50053, user_id='service_001', lazy_connect=False)

def handle_device_message(device_id, message_type, topic, payload, timestamp, metadata):
    """
    处理接收到的设备消息
    
    Args:
        device_id (str): 设备 ID
        message_type (int): 消息类型
            1 = TELEMETRY (遥测数据)
            2 = STATUS (状态更新)
            3 = AUTH (认证请求)
            4 = REGISTRATION (注册请求)
        topic (str): 原始 MQTT topic
        payload (bytes): 消息内容
        timestamp: 时间戳
        metadata (dict): 元数据
    """
    print(f"设备 {device_id} 发送消息:")
    print(f"  类型: {message_type}")
    print(f"  数据: {payload.decode()}")

# 订阅所有设备消息
client.subscribe_device_messages(callback=handle_device_message)
\`\`\`

### 过滤消息

\`\`\`python
# 只监听遥测数据和状态更新
client.subscribe_device_messages(
    message_types=[1, 2],  # TELEMETRY, STATUS
    callback=handle_device_message
)

# 只监听特定设备
client.subscribe_device_messages(
    device_ids=['device-001', 'device-002'],
    callback=handle_device_message
)

# 自定义 topic 模式
client.subscribe_device_messages(
    topic_patterns=['devices/+/telemetry'],
    callback=handle_device_message
)
\`\`\`

### 后台运行

\`\`\`python
import threading

def subscribe_in_background():
    client = MQTTClient(host='localhost', port=50053, user_id='bg_service', lazy_connect=False)
    try:
        client.subscribe_device_messages(message_types=[1, 2], callback=handle_device_message)
    except Exception as e:
        print(f"订阅错误: {e}")

thread = threading.Thread(target=subscribe_in_background, daemon=False)
thread.start()
\`\`\`

---

## 🔗 方式二：Webhook 回调

### 特点

- ✅ **解耦性好** - 服务无需维持长连接
- ✅ **易于扩展** - 多个服务可独立注册 webhook
- ✅ **支持认证** - 自定义 HTTP headers + HMAC 签名

### 注册 Webhook

\`\`\`python
from isa_common import MQTTClient

client = MQTTClient(host='localhost', port=50053, user_id='device_service')

result = client.register_webhook(
    url="http://device-service:8201/api/v1/mqtt/webhook",
    message_types=[1, 2],  # TELEMETRY, STATUS
    topic_patterns=["devices/+/telemetry"],
    headers={"Authorization": "Bearer YOUR_TOKEN"},
    secret="your-webhook-secret"  # 用于 HMAC 签名
)

webhook_id = result['webhook_id']
print(f"✅ Webhook 注册成功: {webhook_id}")
\`\`\`

### 实现接收端

\`\`\`python
from flask import Flask, request, jsonify
import hmac
import hashlib

app = Flask(__name__)
WEBHOOK_SECRET = "your-webhook-secret"

@app.route('/api/v1/mqtt/webhook', methods=['POST'])
def handle_mqtt_webhook():
    # 1. 验证签名
    signature = request.headers.get('X-Webhook-Signature')
    payload = request.get_data()
    expected_sig = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    
    if signature != expected_sig:
        return jsonify({'error': 'Invalid signature'}), 403
    
    # 2. 处理数据
    data = request.get_json()
    device_id = data['device_id']
    payload_data = data['payload']
    
    print(f"收到设备 {device_id} 的消息: {payload_data}")
    
    # 3. 返回成功（重要！）
    return jsonify({'success': True}), 200

app.run(host='0.0.0.0', port=8201)
\`\`\`

### Webhook Payload 格式

\`\`\`json
{
  "webhook_id": "xxx-xxx-xxx",
  "device_id": "device-001",
  "message_type": "DEVICE_MESSAGE_TELEMETRY",
  "topic": "devices/device-001/telemetry",
  "payload": "{\\"temperature\\": 25.5}",
  "timestamp": "2025-11-07T14:10:51Z",
  "qos": 1
}
\`\`\`

**Headers**:
- \`Content-Type: application/json\`
- \`X-Webhook-ID: xxx-xxx-xxx\`
- \`X-Webhook-Signature: abc123...\` (HMAC-SHA256)
- \`Authorization: Bearer YOUR_TOKEN\` (如果注册时提供)

---

## 📤 发送消息到设备

\`\`\`python
from isa_common import MQTTClient

client = MQTTClient(host='localhost', port=50053, user_id='control_service')

# 连接
conn = client.connect('command-sender')
session_id = conn['session_id']

# 发送命令
client.publish_json(
    session_id=session_id,
    topic='devices/device-001/commands',
    data={'command': 'restart'},
    qos=1
)

# 断开
client.disconnect(session_id)
\`\`\`

---

## 🧪 测试

\`\`\`bash
# 运行测试
cd isA_common
python3 tests/test_mqtt_device_stream.py

# 手动发送测试消息
docker exec staging-mosquitto mosquitto_pub -t 'devices/test-001/telemetry' -m '{"temp": 25}'
\`\`\`

---

## ⚙️ 消息类型

| 值 | 名称 | Topic 示例 |
|----|------|------------|
| 1 | TELEMETRY | \`devices/{id}/telemetry\` |
| 2 | STATUS | \`devices/{id}/status\` |
| 3 | AUTH | \`devices/{id}/auth\` |
| 4 | REGISTRATION | \`devices/{id}/registration\` |

---

## ❓ 常见问题

### Stream 收不到消息

**解决**：
\`\`\`python
# 使用 lazy_connect=False
client = MQTTClient(host='localhost', port=50053, user_id='test', lazy_connect=False)

# 线程设置为 daemon=False
thread = threading.Thread(target=subscribe, daemon=False)
thread.start()
\`\`\`

### Webhook 回调失败

**解决**：
\`\`\`python
# Docker 环境使用 host.docker.internal
url="http://host.docker.internal:8201/webhook"

# Webhook 必须返回 200
return jsonify({'success': True}), 200
\`\`\`

---

## 🎯 最佳实践

**使用 Stream**：
- 需要实时处理（延迟 < 100ms）
- 消息频率高（> 10 msg/s）

**使用 Webhook**：
- 服务无状态，易于扩展
- 多个独立服务接收消息

---

**最后更新**：2025-11-07  
**测试状态**：✅ 全部测试通过
