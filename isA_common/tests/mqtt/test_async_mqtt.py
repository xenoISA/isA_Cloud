#!/usr/bin/env python3
"""
Async MQTT Client - Comprehensive Functional Tests

Tests all async MQTT operations including:
- Health check
- Connection management
- Publishing (single, batch, JSON)
- Device management
- Topic management
- Retained messages
- Statistics
- Concurrent operations
"""

import asyncio
import os
import sys
import time
import uuid

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from isa_common import AsyncMQTTClient

# Configuration
HOST = os.environ.get('HOST', 'localhost')
PORT = int(os.environ.get('PORT', '50053'))
USER_ID = os.environ.get('USER_ID', 'test-user')
ORG_ID = os.environ.get('ORG_ID', 'test-org')

# Test results
PASSED = 0
FAILED = 0


def test_result(success: bool, test_name: str):
    """Record test result."""
    global PASSED, FAILED
    if success:
        PASSED += 1
        print(f"  \u2713 PASSED: {test_name}")
    else:
        FAILED += 1
        print(f"  \u2717 FAILED: {test_name}")


async def test_health_check(client: AsyncMQTTClient) -> bool:
    """Test 1: Service Health Check"""
    try:
        health = await client.health_check()
        success = health is not None and health.get('healthy', False)
        test_result(success, f"Health check (broker: {health.get('broker_status', 'unknown')})")
        return success
    except Exception as e:
        test_result(False, f"Health check - {e}")
        return False


async def test_connect(client: AsyncMQTTClient, client_id: str) -> str:
    """Test 2: Connect to MQTT"""
    try:
        result = await client.mqtt_connect(client_id)
        if result and result.get('success'):
            test_result(True, f"Connect (session: {result['session_id'][:8]}...)")
            return result['session_id']
        test_result(False, "Connect - no session")
        return ''
    except Exception as e:
        test_result(False, f"Connect - {e}")
        return ''


async def test_connection_status(client: AsyncMQTTClient, session_id: str):
    """Test 3: Get Connection Status"""
    try:
        status = await client.get_connection_status(session_id)
        success = status is not None
        test_result(success, f"Connection status (connected: {status.get('connected') if status else False})")
    except Exception as e:
        test_result(False, f"Connection status - {e}")


async def test_publish(client: AsyncMQTTClient, session_id: str):
    """Test 4: Publish Message"""
    try:
        result = await client.publish(session_id, 'test/async/topic', b'Hello from async client', qos=1)
        success = result is not None and result.get('success')
        test_result(success, f"Publish message")
    except Exception as e:
        test_result(False, f"Publish - {e}")


async def test_publish_batch(client: AsyncMQTTClient, session_id: str):
    """Test 5: Publish Batch"""
    try:
        messages = [
            {'topic': 'test/async/batch/1', 'payload': b'Message 1', 'qos': 1},
            {'topic': 'test/async/batch/2', 'payload': b'Message 2', 'qos': 1},
            {'topic': 'test/async/batch/3', 'payload': b'Message 3', 'qos': 1},
        ]
        result = await client.publish_batch(session_id, messages)
        success = result is not None and result.get('published_count', 0) == 3
        test_result(success, f"Publish batch ({result.get('published_count', 0)} messages)")
    except Exception as e:
        test_result(False, f"Publish batch - {e}")


async def test_publish_json(client: AsyncMQTTClient, session_id: str):
    """Test 6: Publish JSON"""
    try:
        data = {
            'temperature': 25.5,
            'humidity': 60,
            'timestamp': time.time()
        }
        result = await client.publish_json(session_id, 'test/async/json', data)
        success = result is not None and result.get('success')
        test_result(success, "Publish JSON message")
    except Exception as e:
        test_result(False, f"Publish JSON - {e}")


async def test_validate_topic(client: AsyncMQTTClient):
    """Test 7: Validate Topic"""
    try:
        result = await client.validate_topic('sensors/temperature')
        success = result is not None and result.get('valid', False)
        test_result(success, "Validate topic")
    except Exception as e:
        test_result(False, f"Validate topic - {e}")


async def test_register_device(client: AsyncMQTTClient, device_id: str):
    """Test 8: Register Device"""
    try:
        result = await client.register_device(
            device_id=device_id,
            device_name='Async Test Device',
            device_type='sensor',
            metadata={'location': 'test-lab', 'version': '1.0'}
        )
        success = result is not None and result.get('success')
        test_result(success, f"Register device '{device_id}'")
    except Exception as e:
        test_result(False, f"Register device - {e}")


async def test_list_devices(client: AsyncMQTTClient):
    """Test 9: List Devices"""
    try:
        result = await client.list_devices()
        success = result is not None and 'devices' in result
        test_result(success, f"List devices ({len(result.get('devices', []))} found)")
    except Exception as e:
        test_result(False, f"List devices - {e}")


async def test_get_device_info(client: AsyncMQTTClient, device_id: str):
    """Test 10: Get Device Info"""
    try:
        info = await client.get_device_info(device_id)
        success = info is not None and info.get('device_id') == device_id
        test_result(success, f"Get device info")
    except Exception as e:
        test_result(False, f"Get device info - {e}")


async def test_update_device_status(client: AsyncMQTTClient, device_id: str):
    """Test 11: Update Device Status"""
    try:
        result = await client.update_device_status(device_id, status=1, metadata={'updated': 'true'})
        success = result is not None and result.get('success')
        test_result(success, "Update device status")
    except Exception as e:
        test_result(False, f"Update device status - {e}")


async def test_list_topics(client: AsyncMQTTClient):
    """Test 12: List Topics"""
    try:
        result = await client.list_topics()
        success = result is not None and 'topics' in result
        test_result(success, f"List topics ({len(result.get('topics', []))} found)")
    except Exception as e:
        test_result(False, f"List topics - {e}")


async def test_set_retained_message(client: AsyncMQTTClient):
    """Test 13: Set Retained Message"""
    try:
        success = await client.set_retained_message('test/async/retained', b'Retained data', qos=1)
        test_result(success, "Set retained message")
    except Exception as e:
        test_result(False, f"Set retained message - {e}")


async def test_get_retained_message(client: AsyncMQTTClient):
    """Test 14: Get Retained Message"""
    try:
        result = await client.get_retained_message('test/async/retained')
        success = result is not None
        test_result(success, f"Get retained message (found: {result.get('found', False)})")
    except Exception as e:
        test_result(False, f"Get retained message - {e}")


async def test_delete_retained_message(client: AsyncMQTTClient):
    """Test 15: Delete Retained Message"""
    try:
        success = await client.delete_retained_message('test/async/retained')
        test_result(success, "Delete retained message")
    except Exception as e:
        test_result(False, f"Delete retained message - {e}")


async def test_get_statistics(client: AsyncMQTTClient):
    """Test 16: Get Statistics"""
    try:
        stats = await client.get_statistics()
        success = stats is not None
        test_result(success, f"Get statistics (devices: {stats.get('total_devices', 0) if stats else 0})")
    except Exception as e:
        test_result(False, f"Get statistics - {e}")


async def test_concurrent_publish(client: AsyncMQTTClient, session_id: str):
    """Test 17: Concurrent Publish"""
    try:
        messages = [
            {'topic': f'test/async/concurrent/{i}', 'payload': f'Message {i}'.encode(), 'qos': 1}
            for i in range(10)
        ]

        start = time.time()
        results = await client.publish_many_concurrent(session_id, messages)
        elapsed = (time.time() - start) * 1000

        success_count = sum(1 for r in results if r and r.get('success'))
        success = success_count == len(messages)
        test_result(success, f"Concurrent publish ({success_count}/{len(messages)} in {elapsed:.1f}ms)")
    except Exception as e:
        test_result(False, f"Concurrent publish - {e}")


async def test_unregister_device(client: AsyncMQTTClient, device_id: str):
    """Test 18: Unregister Device"""
    try:
        success = await client.unregister_device(device_id)
        test_result(success, f"Unregister device '{device_id}'")
    except Exception as e:
        test_result(False, f"Unregister device - {e}")


async def test_disconnect(client: AsyncMQTTClient, session_id: str):
    """Test 19: Disconnect"""
    try:
        result = await client.disconnect(session_id)
        success = result is not None and result.get('success')
        test_result(success, "Disconnect")
    except Exception as e:
        test_result(False, f"Disconnect - {e}")


async def run_tests():
    """Run all tests."""
    print("=" * 70)
    print("     ASYNC MQTT CLIENT - COMPREHENSIVE FUNCTIONAL TESTS")
    print("=" * 70)
    print()
    print(f"Configuration:")
    print(f"  Host: {HOST}")
    print(f"  Port: {PORT}")
    print(f"  User: {USER_ID}")
    print()

    # Test identifiers
    test_id = uuid.uuid4().hex[:8]
    client_id = f"async-test-client-{test_id}"
    device_id = f"async-device-{test_id}"

    async with AsyncMQTTClient(
        host=HOST,
        port=PORT,
        user_id=USER_ID,
        organization_id=ORG_ID
    ) as client:
        # Health check first
        print("--- Health Check ---")
        health_ok = await test_health_check(client)

        if not health_ok:
            print("\nHealth check failed - skipping remaining tests")
            print("Make sure the MQTT gRPC service is running and accessible")
            return

        # Connection Management
        print("\n--- Connection Management ---")
        session_id = await test_connect(client, client_id)

        if not session_id:
            print("\nConnection failed - skipping remaining tests")
            return

        await test_connection_status(client, session_id)

        # Publishing
        print("\n--- Publishing ---")
        await test_publish(client, session_id)
        await test_publish_batch(client, session_id)
        await test_publish_json(client, session_id)
        await test_validate_topic(client)

        # Device Management
        print("\n--- Device Management ---")
        await test_register_device(client, device_id)
        await test_list_devices(client)
        await test_get_device_info(client, device_id)
        await test_update_device_status(client, device_id)

        # Topic Management
        print("\n--- Topic Management ---")
        await test_list_topics(client)

        # Retained Messages
        print("\n--- Retained Messages ---")
        await test_set_retained_message(client)
        await test_get_retained_message(client)
        await test_delete_retained_message(client)

        # Statistics
        print("\n--- Statistics ---")
        await test_get_statistics(client)

        # Concurrent Operations
        print("\n--- Concurrent Operations ---")
        await test_concurrent_publish(client, session_id)

        # Cleanup
        print("\n--- Cleanup ---")
        await test_unregister_device(client, device_id)
        await test_disconnect(client, session_id)

    # Summary
    print()
    print("=" * 70)
    print("                         TEST SUMMARY")
    print("=" * 70)
    print(f"Total Tests: {PASSED + FAILED}")
    print(f"Passed: {PASSED}")
    print(f"Failed: {FAILED}")
    print(f"Success Rate: {PASSED/(PASSED+FAILED)*100:.1f}%")
    print()

    if FAILED == 0:
        print("\u2713 ALL TESTS PASSED! ({}/{})".format(PASSED, PASSED + FAILED))
    else:
        print("\u2717 SOME TESTS FAILED ({}/{})".format(PASSED, PASSED + FAILED))
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(run_tests())
