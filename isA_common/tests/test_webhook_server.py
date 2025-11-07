#!/usr/bin/env python3
"""
简单的 Webhook 测试服务器
用于接收 MQTT webhook 回调
"""

from flask import Flask, request, jsonify
import json
from datetime import datetime

app = Flask(__name__)

# 存储接收到的 webhook 消息
webhook_messages = []

@app.route('/webhook/mqtt', methods=['POST'])
def handle_mqtt_webhook():
    """接收 MQTT webhook 回调"""
    try:
        # 获取请求数据
        data = request.get_json()

        # 获取 headers
        headers = dict(request.headers)

        # 记录时间
        received_at = datetime.utcnow().isoformat()

        # 保存消息
        webhook_message = {
            'received_at': received_at,
            'headers': {
                'webhook_id': headers.get('X-Webhook-Id'),
                'timestamp': headers.get('X-Timestamp'),
                'signature': headers.get('X-Webhook-Signature'),
                'user_agent': headers.get('User-Agent'),
            },
            'data': data
        }
        webhook_messages.append(webhook_message)

        # 打印消息
        print(f"\n{'='*60}")
        print(f"📩 收到 Webhook 回调 (#{len(webhook_messages)})")
        print(f"{'='*60}")
        print(f"时间: {received_at}")
        print(f"Webhook ID: {webhook_message['headers']['webhook_id']}")
        print(f"设备 ID: {data.get('device_id')}")
        print(f"消息类型: {data.get('message_type')}")
        print(f"Topic: {data.get('topic')}")
        print(f"Payload: {data.get('payload', '')[:200]}")
        print(f"{'='*60}\n")

        # 返回成功响应
        return jsonify({
            'success': True,
            'message': 'Webhook received',
            'received_at': received_at
        }), 200

    except Exception as e:
        print(f"❌ 处理 webhook 错误: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


@app.route('/webhook/stats', methods=['GET'])
def get_stats():
    """获取 webhook 统计"""
    return jsonify({
        'total_messages': len(webhook_messages),
        'messages': webhook_messages[-10:]  # 最近 10 条
    })


@app.route('/webhook/clear', methods=['POST'])
def clear_messages():
    """清空消息"""
    global webhook_messages
    count = len(webhook_messages)
    webhook_messages = []
    return jsonify({
        'success': True,
        'cleared': count
    })


if __name__ == '__main__':
    print("\n" + "="*60)
    print("MQTT Webhook 测试服务器")
    print("="*60)
    print("\n监听地址: http://localhost:8999/webhook/mqtt")
    print("统计接口: http://localhost:8999/webhook/stats")
    print("清空接口: http://localhost:8999/webhook/clear")
    print("\n按 Ctrl+C 停止服务器\n")

    app.run(host='0.0.0.0', port=8999, debug=True)
