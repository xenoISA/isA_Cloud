#!/usr/bin/env python3
"""
MQTT 设备消息流测试
测试新增的 SubscribeDeviceMessages 和 Webhook 功能
"""

import threading
import time

from isa_common import MQTTClient

# 测试配置
MQTT_HOST = "localhost"
MQTT_PORT = 50053
USER_ID = "test_user_001"
ORG_ID = "test_org"


def test_device_message_stream():
    """
    测试 1: 订阅设备消息流（gRPC Streaming）
    """
    print("\n" + "=" * 60)
    print("测试 1: 设备消息流订阅 (gRPC Stream)")
    print("=" * 60)

    client = MQTTClient(host=MQTT_HOST, port=MQTT_PORT, user_id=USER_ID, organization_id=ORG_ID)

    # 消息计数器
    message_count = {"count": 0}

    def handle_device_message(device_id, message_type, topic, payload, timestamp, metadata):
        """处理接收到的设备消息"""
        message_count["count"] += 1
        print(f"\n📩 收到设备消息 #{message_count['count']}")
        print(f"   设备 ID: {device_id}")
        print(f"   消息类型: {message_type}")
        print(f"   Topic: {topic}")
        print(f"   Payload: {payload[:200]}")
        print(f"   时间戳: {timestamp}")
        print(f"   元数据: {metadata}")

    try:
        # 启动订阅（在后台线程运行）
        print("\n🔄 开始订阅设备消息...")
        print("   订阅消息类型: TELEMETRY (1), STATUS (2)")

        # 在单独线程中订阅
        subscribe_thread = threading.Thread(
            target=client.subscribe_device_messages,
            kwargs={
                "message_types": [1, 2],  # TELEMETRY and STATUS
                "callback": handle_device_message,
            },
            daemon=True,
        )
        subscribe_thread.start()

        # 等待一段时间接收消息
        print("\n⏳ 等待 10 秒接收设备消息...")
        print("   (请在另一个终端发送 MQTT 消息进行测试)")
        print("   示例: mosquitto_pub -t 'devices/test-device-001/telemetry' -m '{\"temp\": 25.5}'")

        time.sleep(10)

        print(f"\n✅ 测试完成！共接收 {message_count['count']} 条消息")

    except KeyboardInterrupt:
        print("\n\n⚠️  测试中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
    finally:
        client.close()


def test_webhook_registration():
    """
    测试 2: Webhook 注册和管理
    """
    print("\n" + "=" * 60)
    print("测试 2: Webhook 注册和管理")
    print("=" * 60)

    client = MQTTClient(host=MQTT_HOST, port=MQTT_PORT, user_id=USER_ID, organization_id=ORG_ID)

    try:
        # 1. 注册 webhook
        print("\n📝 注册 Webhook...")
        webhook_result = client.register_webhook(
            url="http://localhost:8999/webhook/mqtt",  # 测试 URL
            message_types=[1, 2],  # TELEMETRY and STATUS
            topic_patterns=["devices/+/telemetry", "devices/+/status"],
            headers={"Authorization": "Bearer test-token"},
            secret="my-secret-key",
        )

        if webhook_result:
            webhook_id = webhook_result["webhook_id"]
            print("✅ Webhook 注册成功!")
            print(f"   Webhook ID: {webhook_id}")
            print(f"   URL: {webhook_result['webhook']['url']}")
        else:
            print("❌ Webhook 注册失败")
            return

        # 2. 列出所有 webhooks
        print("\n📋 列出所有 Webhooks...")
        webhooks = client.list_webhooks(include_disabled=True)
        print(f"✅ 找到 {len(webhooks)} 个 Webhook:")
        for wh in webhooks:
            print(f"   - {wh['webhook_id']}: {wh['url']}")
            print(f"     成功: {wh['success_count']}, 失败: {wh['failure_count']}")

        # 3. 等待一段时间，让 webhook 接收消息
        print("\n⏳ 等待 10 秒测试 Webhook 回调...")
        print("   (请在另一个终端发送 MQTT 消息)")
        print("   或启动测试 webhook 服务器: python3 tests/test_webhook_server.py")
        time.sleep(10)

        # 4. 再次列出 webhooks 查看统计
        print("\n📊 查看 Webhook 统计...")
        webhooks = client.list_webhooks()
        for wh in webhooks:
            if wh["webhook_id"] == webhook_id:
                print("✅ Webhook 统计:")
                print(f"   成功回调: {wh['success_count']}")
                print(f"   失败回调: {wh['failure_count']}")

        # 5. 注销 webhook
        print(f"\n🗑️  注销 Webhook {webhook_id}...")
        if client.unregister_webhook(webhook_id):
            print("✅ Webhook 注销成功")
        else:
            print("❌ Webhook 注销失败")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
    finally:
        client.close()


def test_simulated_device():
    """
    测试 3: 模拟设备发送消息
    """
    print("\n" + "=" * 60)
    print("测试 3: 模拟设备发送消息")
    print("=" * 60)

    client = MQTTClient(host=MQTT_HOST, port=MQTT_PORT, user_id=USER_ID, organization_id=ORG_ID)

    try:
        # 连接
        print("\n🔌 连接到 MQTT 服务...")
        conn = client.connect("test-device-simulator")

        if not conn:
            print("❌ 连接失败")
            return

        session_id = conn["session_id"]
        print(f"✅ 连接成功! Session ID: {session_id}")

        # 发送遥测数据
        print("\n📤 发送设备遥测数据...")
        telemetry_data = {
            "device_id": "test-device-001",
            "temperature": 25.5,
            "humidity": 60.2,
            "timestamp": int(time.time()),
        }

        client.publish_json(
            session_id=session_id,
            topic="devices/test-device-001/telemetry",
            data=telemetry_data,
            qos=1,
        )
        print("✅ 遥测数据已发送")

        # 发送状态更新
        print("\n📤 发送设备状态...")
        status_data = {
            "device_id": "test-device-001",
            "status": "online",
            "battery": 85,
            "timestamp": int(time.time()),
        }

        client.publish_json(
            session_id=session_id, topic="devices/test-device-001/status", data=status_data, qos=1
        )
        print("✅ 状态数据已发送")

        # 等待一下让消息被处理
        time.sleep(2)

        # 断开连接
        print("\n🔌 断开连接...")
        client.disconnect(session_id)
        print("✅ 断开成功")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
    finally:
        client.close()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("MQTT 设备消息流端到端测试")
    print("=" * 60)
    print("\n测试目标:")
    print("  1. gRPC Stream - 订阅设备消息")
    print("  2. Webhook - 注册和管理")
    print("  3. 模拟设备 - 发送消息")
    print("\n前置条件:")
    print("  - MQTT Broker 运行在 localhost:1883")
    print("  - mqtt-service 运行在 localhost:50053")
    print("")

    # 运行测试
    try:
        # 测试 3: 先发送一些消息
        test_simulated_device()

        # 测试 2: Webhook
        test_webhook_registration()

        # 测试 1: Stream (会一直监听，需要手动中断)
        test_device_message_stream()

    except KeyboardInterrupt:
        print("\n\n✅ 测试完成!")
