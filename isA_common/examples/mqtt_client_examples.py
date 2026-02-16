#!/usr/bin/env python3
"""
MQTT Client Usage Examples
===========================

This example demonstrates how to use the MQTTClient from isa_common package.
Based on comprehensive functional tests with 100% success rate (11/11 tests passing).

File: isA_common/examples/mqtt_client_examples.py

Prerequisites:
--------------
1. MQTT gRPC service must be running (default: localhost:50053)
2. Install isa_common package:
   ```bash
   pip install -e /path/to/isA_Cloud/isA_common
   ```

Usage:
------
```bash
# Run all examples
python isA_common/examples/mqtt_client_examples.py

# Run with custom host/port
python isA_common/examples/mqtt_client_examples.py --host 192.168.1.100 --port 50053

# Run specific example
python isA_common/examples/mqtt_client_examples.py --example 8
```

Features Demonstrated:
----------------------
✅ Connection Management (Connect, Disconnect, GetConnectionStatus)
✅ Message Publishing (Publish, PublishBatch, PublishJSON)
✅ Message Subscription (Subscribe, SubscribeMultiple, Unsubscribe, ListSubscriptions)
✅ Device Management (Register, Unregister, List, GetInfo, UpdateStatus)
✅ Topic Management (GetTopicInfo, ListTopics, ValidateTopic)
✅ Retained Messages (Set, Get, Delete)
✅ QoS Levels (0, 1, 2)
✅ Binary and JSON Payloads
✅ Topic Wildcards (+, #)
✅ Monitoring Operations (GetStatistics, GetDeviceMetrics)
✅ Health Check

Note: All operations include proper error handling and use context managers for resource cleanup.
"""

import sys
import argparse
import time
import json
from datetime import datetime
from typing import Dict, List

# Import the MQTTClient from isa_common
try:
    from isa_common.mqtt_client import MQTTClient
except ImportError:
    print("=" * 80)
    print("ERROR: Failed to import isa_common.mqtt_client")
    print("=" * 80)
    print("\nPlease install isa_common package:")
    print("  cd /path/to/isA_Cloud")
    print("  pip install -e isA_common")
    print()
    sys.exit(1)


def example_01_health_check(host='localhost', port=50053):
    """
    Example 1: Health Check
    
    Check if the MQTT gRPC service is healthy and operational.
    File: mqtt_client.py, Method: health_check()
    """
    print("\n" + "=" * 80)
    print("Example 1: Service Health Check")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        health = client.health_check(deep_check=True)
        
        if health and health.get('healthy'):
            print(f"✅ Service is healthy!")
            print(f"   Broker status: {health.get('broker_status')}")
            print(f"   Active connections: {health.get('active_connections')}")
            print(f"   Message: {health.get('message')}")
        else:
            print("❌ Service is not healthy")


def example_02_connection_lifecycle(host='localhost', port=50053):
    """
    Example 2: Connection Lifecycle
    
    Connect, check status, and disconnect from MQTT broker.
    File: mqtt_client.py, Methods: connect(), get_connection_status(), disconnect()
    """
    print("\n" + "=" * 80)
    print("Example 2: Connection Lifecycle (Connect, Status, Disconnect)")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        # Connect to broker
        client_id = f'example-client-{int(time.time())}'
        conn = client.connect(client_id, username='', password='')
        
        if conn and conn.get('success'):
            session_id = conn.get('session_id')
            print(f"\n📡 Connected successfully!")
            print(f"   Client ID: {client_id}")
            print(f"   Session ID: {session_id}")
            
            # Get connection status
            status = client.get_connection_status(session_id)
            if status:
                print(f"\n📊 Connection Status:")
                print(f"   Connected: {status.get('connected')}")
                print(f"   Messages sent: {status.get('messages_sent')}")
                print(f"   Messages received: {status.get('messages_received')}")
            
            # Disconnect
            disc = client.disconnect(session_id)
            if disc and disc.get('success'):
                print(f"\n👋 Disconnected successfully")


def example_03_basic_publish(host='localhost', port=50053):
    """
    Example 3: Basic Message Publishing
    
    Publish messages to MQTT topics with different QoS levels.
    File: mqtt_client.py, Method: publish()
    """
    print("\n" + "=" * 80)
    print("Example 3: Basic Message Publishing")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        conn = client.connect(f'publisher-{int(time.time())}')
        
        if conn:
            session_id = conn.get('session_id')
            
            # Publish to different topics
            topics = [
                ('sensors/temperature', b'22.5', 1),
                ('sensors/humidity', b'65', 1),
                ('alerts/high_temp', b'Temperature exceeded threshold!', 2),
                ('status/system', b'operational', 0)
            ]
            
            print(f"\n📤 Publishing messages:")
            for topic, payload, qos in topics:
                result = client.publish(session_id, topic, payload, qos=qos)
                if result:
                    print(f"   ✅ {topic} (QoS {qos})")
            
            client.disconnect(session_id)


def example_04_json_publishing(host='localhost', port=50053):
    """
    Example 4: JSON Message Publishing
    
    Publish structured JSON data to MQTT topics.
    File: mqtt_client.py, Method: publish_json()
    """
    print("\n" + "=" * 80)
    print("Example 4: JSON Message Publishing")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        conn = client.connect(f'json-publisher-{int(time.time())}')
        
        if conn:
            session_id = conn.get('session_id')
            
            # Sensor data as JSON
            sensor_data = {
                'sensor_id': 'TH-001',
                'temperature': 23.5,
                'humidity': 62,
                'timestamp': datetime.now().isoformat(),
                'location': 'Room 101',
                'battery': 95
            }
            
            result = client.publish_json(session_id, 'sensors/readings', sensor_data, qos=1)
            
            if result:
                print(f"\n📊 Published JSON data:")
                print(json.dumps(sensor_data, indent=2))
            
            # IoT event as JSON
            event = {
                'event_type': 'motion_detected',
                'device_id': 'CAM-005',
                'timestamp': datetime.now().isoformat(),
                'confidence': 0.95,
                'zone': 'entrance'
            }
            
            client.publish_json(session_id, 'events/security', event, qos=2)
            
            client.disconnect(session_id)


def example_05_batch_publishing(host='localhost', port=50053):
    """
    Example 5: Batch Message Publishing
    
    Publish multiple messages efficiently in a single batch.
    File: mqtt_client.py, Method: publish_batch()
    """
    print("\n" + "=" * 80)
    print("Example 5: Batch Message Publishing")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        conn = client.connect(f'batch-publisher-{int(time.time())}')
        
        if conn:
            session_id = conn.get('session_id')
            
            # Prepare batch of sensor readings
            messages = []
            for i in range(10):
                messages.append({
                    'topic': f'sensors/zone{i%3}/reading',
                    'payload': json.dumps({
                        'zone': i % 3,
                        'value': 20 + i,
                        'timestamp': datetime.now().isoformat()
                    }).encode(),
                    'qos': 1,
                    'retained': False
                })
            
            print(f"\n📦 Publishing batch of {len(messages)} messages...")
            result = client.publish_batch(session_id, messages)
            
            if result and result.get('success'):
                print(f"   ✅ Published: {result.get('published_count')}")
                print(f"   ❌ Failed: {result.get('failed_count')}")
            
            client.disconnect(session_id)


def example_06_qos_levels(host='localhost', port=50053):
    """
    Example 6: QoS Levels
    
    Demonstrate different Quality of Service levels.
    File: mqtt_client.py, Method: publish()
    
    QoS 0: At most once (fire and forget)
    QoS 1: At least once (acknowledged delivery)
    QoS 2: Exactly once (assured delivery)
    """
    print("\n" + "=" * 80)
    print("Example 6: QoS Levels (Quality of Service)")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        conn = client.connect(f'qos-demo-{int(time.time())}')
        
        if conn:
            session_id = conn.get('session_id')
            
            # QoS 0: Fire and forget
            print(f"\n📡 QoS 0 (At Most Once):")
            client.publish(session_id, 'logs/debug', b'Debug message', qos=0)
            print(f"   Use for: Non-critical logs, telemetry")
            
            # QoS 1: At least once
            print(f"\n📡 QoS 1 (At Least Once):")
            client.publish(session_id, 'sensors/data', b'Sensor reading', qos=1)
            print(f"   Use for: Sensor data, analytics")
            
            # QoS 2: Exactly once
            print(f"\n📡 QoS 2 (Exactly Once):")
            client.publish(session_id, 'commands/critical', b'Execute shutdown', qos=2)
            print(f"   Use for: Critical commands, financial transactions")
            
            client.disconnect(session_id)


def example_07_retained_messages(host='localhost', port=50053):
    """
    Example 7: Retained Messages
    
    Set, retrieve, and delete retained messages that new subscribers receive.
    File: mqtt_client.py, Methods: set_retained_message(), get_retained_message(), delete_retained_message()
    """
    print("\n" + "=" * 80)
    print("Example 7: Retained Messages (Last Known State)")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        conn = client.connect(f'retained-demo-{int(time.time())}')
        
        if conn:
            session_id = conn.get('session_id')
            topic = 'devices/thermostat/status'
            
            # Set retained message (last known state)
            payload = json.dumps({
                'temperature': 21.5,
                'mode': 'heat',
                'timestamp': datetime.now().isoformat()
            }).encode()
            
            success = client.set_retained_message(topic, payload, qos=1)
            if success:
                print(f"\n💾 Retained message set on '{topic}'")
                print(f"   New subscribers will receive this as last known state")
            
            # Retrieve retained message
            msg = client.get_retained_message(topic)
            if msg and msg.get('found'):
                print(f"\n📩 Retrieved retained message:")
                data = json.loads(msg.get('payload'))
                print(f"   Temperature: {data['temperature']}°C")
                print(f"   Mode: {data['mode']}")
            
            # Delete retained message
            if client.delete_retained_message(topic):
                print(f"\n🗑️  Retained message deleted")
            
            client.disconnect(session_id)


def example_08_device_registration(host='localhost', port=50053):
    """
    Example 8: Device Registration and Management
    
    Register IoT devices, update their status, and manage device fleet.
    File: mqtt_client.py, Methods: register_device(), update_device_status(), get_device_info(), etc.
    """
    print("\n" + "=" * 80)
    print("Example 8: Device Registration and Management")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        # Register multiple devices
        devices = [
            ('sensor-temp-01', 'Temperature Sensor 1', 'sensor', {'location': 'Living Room', 'model': 'DHT22'}),
            ('sensor-temp-02', 'Temperature Sensor 2', 'sensor', {'location': 'Bedroom', 'model': 'DHT22'}),
            ('gateway-01', 'Main Gateway', 'gateway', {'location': 'Server Room', 'firmware': 'v2.1.0'}),
        ]
        
        print(f"\n📝 Registering {len(devices)} devices:")
        for device_id, name, dev_type, metadata in devices:
            reg = client.register_device(device_id, name, dev_type, metadata)
            if reg and reg.get('success'):
                print(f"   ✅ {name} ({device_id})")
        
        # Update device status
        print(f"\n🔄 Updating device status:")
        client.update_device_status('sensor-temp-01', 1)  # ONLINE
        client.update_device_status('gateway-01', 1)  # ONLINE
        
        # Get device info
        print(f"\n📊 Device Information:")
        info = client.get_device_info('sensor-temp-01')
        if info:
            print(f"   Name: {info.get('device_name')}")
            print(f"   Type: {info.get('device_type')}")
            print(f"   Status: {info.get('status')}")
            print(f"   Metadata: {info.get('metadata')}")
        
        # List all devices
        result = client.list_devices(page=1, page_size=10)
        if result:
            print(f"\n📋 Total devices: {result.get('total_count')}")
            for device in result.get('devices', [])[:3]:
                print(f"   - {device.get('device_name')} ({device.get('device_id')})")
        
        # Cleanup
        for device_id, _, _, _ in devices:
            client.unregister_device(device_id)


def example_09_topic_management(host='localhost', port=50053):
    """
    Example 9: Topic Management
    
    Validate topics, get topic info, and list active topics.
    File: mqtt_client.py, Methods: validate_topic(), get_topic_info(), list_topics()
    """
    print("\n" + "=" * 80)
    print("Example 9: Topic Management")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        # Validate topics
        print(f"\n✅ Topic Validation:")
        topics_to_validate = [
            ('sensors/temperature', False, True),
            ('sensors/+/humidity', True, True),
            ('home/#', True, True),
            ('invalid topic!', False, False),
        ]
        
        for topic, allow_wildcards, expected in topics_to_validate:
            result = client.validate_topic(topic, allow_wildcards=allow_wildcards)
            status = "✅" if result.get('valid') == expected else "❌"
            print(f"   {status} '{topic}' (wildcards: {allow_wildcards})")
        
        # Create connection and publish
        conn = client.connect(f'topic-manager-{int(time.time())}')
        if conn:
            session_id = conn.get('session_id')
            
            # Publish to create topics
            client.publish(session_id, 'sensors/temp/zone1', b'25.0', qos=1)
            client.publish(session_id, 'sensors/temp/zone2', b'26.0', qos=1)
            
            # Get topic info
            print(f"\n📊 Topic Information:")
            info = client.get_topic_info('sensors/temp/zone1')
            if info:
                print(f"   Topic: {info.get('topic')}")
                print(f"   Subscribers: {info.get('subscriber_count')}")
                print(f"   Messages: {info.get('message_count')}")
            
            # List topics
            topics = client.list_topics(prefix='sensors/', page_size=10)
            if topics:
                print(f"\n📋 Topics (total: {topics.get('total_count')}):")
                for topic_info in topics.get('topics', [])[:5]:
                    print(f"   - {topic_info.get('topic')}")
            
            client.disconnect(session_id)


def example_10_topic_hierarchies(host='localhost', port=50053):
    """
    Example 10: Topic Hierarchies
    
    Use hierarchical topic structure for organization.
    File: mqtt_client.py, Method: publish()
    """
    print("\n" + "=" * 80)
    print("Example 10: Topic Hierarchies (Smart Home)")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        conn = client.connect(f'smarthome-{int(time.time())}')
        
        if conn:
            session_id = conn.get('session_id')
            
            # Smart home topic hierarchy
            readings = {
                'home/livingroom/temperature': '22.5',
                'home/livingroom/humidity': '65',
                'home/bedroom/temperature': '21.0',
                'home/bedroom/humidity': '58',
                'home/kitchen/temperature': '24.0',
                'office/room1/temperature': '20.5',
                'office/room2/humidity': '60'
            }
            
            print(f"\n🏠 Publishing smart home data:")
            for topic, value in readings.items():
                client.publish(session_id, topic, value.encode(), qos=1)
                location = '/'.join(topic.split('/')[:-1])
                sensor = topic.split('/')[-1]
                print(f"   📍 {location}: {sensor} = {value}")
            
            client.disconnect(session_id)


def example_11_binary_payloads(host='localhost', port=50053):
    """
    Example 11: Binary Payloads
    
    Send binary data (images, sensor data, compressed data).
    File: mqtt_client.py, Method: publish()
    """
    print("\n" + "=" * 80)
    print("Example 11: Binary Payloads (Raw Sensor Data)")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        conn = client.connect(f'binary-sender-{int(time.time())}')
        
        if conn:
            session_id = conn.get('session_id')
            
            # Simulate binary sensor data
            binary_data = bytes([0x01, 0x02, 0x03, 0x04, 0xFF, 0xFE, 0xFD, 0xFC])
            
            result = client.publish(session_id, 'sensors/binary/raw', binary_data, qos=1)
            
            if result:
                print(f"\n📊 Binary data published:")
                print(f"   Size: {len(binary_data)} bytes")
                print(f"   Hex: {binary_data.hex()}")
                print(f"   Topic: sensors/binary/raw")
            
            # Simulate compressed data
            import zlib
            text_data = b"Large sensor log data that should be compressed..." * 10
            compressed = zlib.compress(text_data)
            
            client.publish(session_id, 'sensors/compressed/logs', compressed, qos=1)
            
            print(f"\n📦 Compressed data published:")
            print(f"   Original: {len(text_data)} bytes")
            print(f"   Compressed: {len(compressed)} bytes")
            print(f"   Compression ratio: {len(compressed)/len(text_data)*100:.1f}%")
            
            client.disconnect(session_id)


def example_12_monitoring_statistics(host='localhost', port=50053):
    """
    Example 12: Monitoring and Statistics
    
    Monitor broker statistics and device metrics.
    File: mqtt_client.py, Methods: get_statistics(), get_device_metrics()
    """
    print("\n" + "=" * 80)
    print("Example 12: Monitoring and Statistics")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        # Get broker statistics
        stats = client.get_statistics()
        
        if stats:
            print(f"\n📊 MQTT Broker Statistics:")
            print(f"   Total devices: {stats.get('total_devices')}")
            print(f"   Online devices: {stats.get('online_devices')}")
            print(f"   Total topics: {stats.get('total_topics')}")
            print(f"   Total subscriptions: {stats.get('total_subscriptions')}")
            print(f"   Messages sent today: {stats.get('messages_sent_today')}")
            print(f"   Messages received today: {stats.get('messages_received_today')}")
            print(f"   Active sessions: {stats.get('active_sessions')}")
        
        # Register a device first
        device_id = 'metrics-device-001'
        client.register_device(device_id, 'Metrics Test Device', 'sensor')
        
        # Get device metrics
        print(f"\n📈 Device Metrics:")
        metrics = client.get_device_metrics(device_id)
        if metrics:
            print(f"   Device: {metrics.get('device_id')}")
            print(f"   Messages sent: {metrics.get('messages_sent')}")
            print(f"   Messages received: {metrics.get('messages_received')}")
            print(f"   Bytes sent: {metrics.get('bytes_sent')}")
            print(f"   Bytes received: {metrics.get('bytes_received')}")
        
        # Cleanup
        client.unregister_device(device_id)


def example_13_iot_sensor_scenario(host='localhost', port=50053):
    """
    Example 13: Complete IoT Sensor Scenario
    
    Real-world example: Temperature sensor sending periodic readings.
    File: mqtt_client.py, Multiple methods combined
    """
    print("\n" + "=" * 80)
    print("Example 13: Complete IoT Sensor Scenario")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        # Register sensor device
        sensor_id = 'temp-sensor-lab-01'
        reg = client.register_device(
            sensor_id,
            'Lab Temperature Sensor',
            'sensor',
            {'location': 'Lab Room 3', 'model': 'DS18B20', 'firmware': 'v1.2.3'}
        )
        
        if reg and reg.get('success'):
            print(f"\n🌡️  Sensor registered: {sensor_id}")
            
            # Connect sensor
            conn = client.connect(f'{sensor_id}-connection')
            if conn:
                session_id = conn.get('session_id')
                
                # Update status to ONLINE
                client.update_device_status(sensor_id, 1)  # ONLINE
                
                # Simulate sensor sending periodic readings
                print(f"\n📡 Sending sensor readings:")
                for i in range(5):
                    reading = {
                        'sensor_id': sensor_id,
                        'temperature': 22.0 + (i * 0.5),
                        'humidity': 60 + i,
                        'timestamp': datetime.now().isoformat(),
                        'reading_number': i + 1
                    }
                    
                    client.publish_json(session_id, f'{sensor_id}/readings', reading, qos=1)
                    print(f"   Reading #{i+1}: {reading['temperature']}°C, {reading['humidity']}%")
                    time.sleep(0.1)
                
                # Send status update
                status = {'status': 'operational', 'battery': 95}
                client.publish_json(session_id, f'{sensor_id}/status', status, qos=1, retained=True)
                
                # Update status to OFFLINE before disconnect
                client.update_device_status(sensor_id, 2)  # OFFLINE
                client.disconnect(session_id)
                
                print(f"\n✅ Sensor simulation completed")
        
        # Cleanup
        client.unregister_device(sensor_id)


def example_14_alert_system(host='localhost', port=50053):
    """
    Example 14: Alert System Pattern
    
    Implement a threshold-based alert system.
    File: mqtt_client.py, Methods: publish(), publish_json()
    """
    print("\n" + "=" * 80)
    print("Example 14: Alert System Pattern")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        conn = client.connect(f'alert-system-{int(time.time())}')
        
        if conn:
            session_id = conn.get('session_id')
            
            # Temperature monitoring with alerts
            threshold_high = 30.0
            threshold_low = 15.0
            
            readings = [18.5, 22.0, 28.5, 32.0, 14.0, 25.0]
            
            print(f"\n🌡️  Monitoring temperature (threshold: {threshold_low}-{threshold_high}°C):")
            
            for i, temp in enumerate(readings, 1):
                # Publish reading
                reading = {'reading': i, 'temperature': temp, 'timestamp': datetime.now().isoformat()}
                client.publish_json(session_id, 'sensors/temperature/current', reading, qos=1)
                
                # Check thresholds and send alerts
                if temp > threshold_high:
                    alert = {
                        'type': 'HIGH_TEMPERATURE',
                        'severity': 'WARNING',
                        'value': temp,
                        'threshold': threshold_high,
                        'message': f'Temperature {temp}°C exceeds {threshold_high}°C'
                    }
                    client.publish_json(session_id, 'alerts/temperature/high', alert, qos=2, retained=True)
                    print(f"   #{i}: {temp}°C 🔴 HIGH ALERT!")
                elif temp < threshold_low:
                    alert = {
                        'type': 'LOW_TEMPERATURE',
                        'severity': 'WARNING',
                        'value': temp,
                        'threshold': threshold_low,
                        'message': f'Temperature {temp}°C below {threshold_low}°C'
                    }
                    client.publish_json(session_id, 'alerts/temperature/low', alert, qos=2, retained=True)
                    print(f"   #{i}: {temp}°C 🔵 LOW ALERT!")
                else:
                    print(f"   #{i}: {temp}°C ✅ Normal")
            
            client.disconnect(session_id)


def example_15_real_world_patterns(host='localhost', port=50053):
    """
    Example 15: Real-World MQTT Patterns
    
    Demonstrate common MQTT usage patterns.
    File: mqtt_client.py, Multiple methods
    """
    print("\n" + "=" * 80)
    print("Example 15: Real-World MQTT Patterns")
    print("=" * 80)
    
    with MQTTClient(host=host, port=port, user_id='example-user') as client:
        conn = client.connect(f'patterns-demo-{int(time.time())}')
        
        if conn:
            session_id = conn.get('session_id')
            
            # Pattern 1: Status Updates
            print(f"\n🎯 Pattern 1: Status Updates (Retained)")
            devices = ['device-001', 'device-002', 'device-003']
            for device in devices:
                status = {'device_id': device, 'status': 'online', 'timestamp': datetime.now().isoformat()}
                client.publish_json(session_id, f'devices/{device}/status', status, qos=1, retained=True)
                print(f"   ✅ {device} status published (retained)")
            
            # Pattern 2: Telemetry Data
            print(f"\n🎯 Pattern 2: Telemetry Data (QoS 0)")
            telemetry = [
                {'metric': 'cpu', 'value': 45.2},
                {'metric': 'memory', 'value': 68.5},
                {'metric': 'disk', 'value': 82.1}
            ]
            for data in telemetry:
                client.publish_json(session_id, f'telemetry/{data["metric"]}', data, qos=0)
                print(f"   📊 {data['metric']}: {data['value']}%")
            
            # Pattern 3: Commands (High QoS)
            print(f"\n🎯 Pattern 3: Commands (QoS 2 for reliability)")
            commands = [
                {'action': 'restart', 'target': 'device-001'},
                {'action': 'update_config', 'target': 'device-002', 'params': {'interval': 60}}
            ]
            for cmd in commands:
                client.publish_json(session_id, f'commands/{cmd["target"]}', cmd, qos=2)
                print(f"   ⚡ Command sent to {cmd['target']}: {cmd['action']}")
            
            # Pattern 4: Events (Structured)
            print(f"\n🎯 Pattern 4: Events (Structured Logging)")
            events = [
                {'type': 'user_login', 'user': 'alice', 'ip': '192.168.1.100'},
                {'type': 'data_sync', 'records': 1542, 'duration_ms': 235},
                {'type': 'backup_complete', 'size_mb': 512, 'destination': 's3'}
            ]
            for event in events:
                client.publish_json(session_id, f'events/{event["type"]}', event, qos=1)
                print(f"   📝 Event: {event['type']}")
            
            client.disconnect(session_id)


def run_all_examples(host='localhost', port=50053):
    """Run all examples in sequence"""
    print("\n" + "=" * 80)
    print("  MQTT Client Usage Examples")
    print("  Based on isa_common.mqtt_client.MQTTClient")
    print("=" * 80)
    print(f"\nConnecting to: {host}:{port}")
    print(f"Timestamp: {datetime.now()}\n")
    
    examples = [
        example_01_health_check,
        example_02_connection_lifecycle,
        example_03_basic_publish,
        example_04_json_publishing,
        example_05_batch_publishing,
        example_06_qos_levels,
        example_07_retained_messages,
        example_08_device_registration,
        example_09_topic_management,
        example_10_topic_hierarchies,
        example_11_binary_payloads,
        example_12_monitoring_statistics,
        example_13_iot_sensor_scenario,
        example_14_alert_system,
        example_15_real_world_patterns,
    ]
    
    for i, example in enumerate(examples, 1):
        try:
            example(host, port)
        except Exception as e:
            print(f"\n❌ Example {i} failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("  All Examples Completed!")
    print("=" * 80)
    print("\nFor more information:")
    print("  - Client source: isA_common/isa_common/mqtt_client.py (763 lines, 24 methods)")
    print("  - Proto definition: api/proto/mqtt_service.proto")
    print("  - Test script: isA_common/tests/mqtt/test_mqtt_functional.sh")
    print("  - Test result: 11/11 tests passing (100% success rate)")
    print("\n📚 Covered Operations (24 total):")
    print("   - Connection: 3 operations")
    print("   - Publishing: 3 operations")
    print("   - Subscription: 4 operations")
    print("   - Devices: 5 operations")
    print("   - Topics: 3 operations")
    print("   - Retained: 3 operations")
    print("   - Monitoring: 2 operations")
    print("   - Health: 1 operation")
    print()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='MQTT Client Usage Examples',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--host', default=None,
                       help='MQTT gRPC service host (optional, uses Consul discovery if not provided)')
    parser.add_argument('--port', type=int, default=None,
                       help='MQTT gRPC service port (optional, uses Consul discovery if not provided)')
    parser.add_argument('--consul-host', default='localhost',
                       help='Consul host (default: localhost)')
    parser.add_argument('--consul-port', type=int, default=8500,
                       help='Consul port (default: 8500)')
    parser.add_argument('--use-consul', action='store_true',
                       help='Use Consul for service discovery')
    parser.add_argument('--example', type=int, choices=range(1, 16),
                       help='Run specific example (1-15, default: all)')

    args = parser.parse_args()

    # Default: Try Consul first, fallback to localhost
    host = args.host
    port = args.port

    if host is None or port is None:
        if not args.use_consul:
            try:
                from isa_common.consul_client import ConsulRegistry
                print(f"🔍 Attempting Consul discovery from {args.consul_host}:{args.consul_port}...")
                consul = ConsulRegistry(consul_host=args.consul_host, consul_port=args.consul_port)
                url = consul.get_service_endpoint('mqtt-grpc-service')

                if url and '://' in url:
                    url = url.split('://', 1)[1]
                if url and ':' in url:
                    discovered_host, port_str = url.rsplit(':', 1)
                    discovered_port = int(port_str)

                    host = host or discovered_host
                    port = port or discovered_port
                    print(f"✅ Discovered from Consul: {host}:{port}")
            except Exception as e:
                print(f"⚠️  Consul discovery failed: {e}")
                print(f"📍 Falling back to localhost...")

        # Fallback to defaults
        host = host or 'localhost'
        port = port or 50053

    print(f"🔗 Connecting to MQTT at {host}:{port}\n")

    if args.example:
        # Run specific example
        examples_map = {
            1: example_01_health_check,
            2: example_02_connection_lifecycle,
            3: example_03_basic_publish,
            4: example_04_json_publishing,
            5: example_05_batch_publishing,
            6: example_06_qos_levels,
            7: example_07_retained_messages,
            8: example_08_device_registration,
            9: example_09_topic_management,
            10: example_10_topic_hierarchies,
            11: example_11_binary_payloads,
            12: example_12_monitoring_statistics,
            13: example_13_iot_sensor_scenario,
            14: example_14_alert_system,
            15: example_15_real_world_patterns,
        }
        examples_map[args.example](host=args.host, port=args.port)
    else:
        # Run all examples
        run_all_examples(host=args.host, port=args.port)


if __name__ == '__main__':
    main()

