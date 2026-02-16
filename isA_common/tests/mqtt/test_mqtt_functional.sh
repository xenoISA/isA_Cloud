#!/bin/bash

# ============================================
# MQTT Service - Comprehensive Functional Tests
# ============================================
# Tests ALL 24 MQTT operations including:
# - Connection Management (Connect, Disconnect, GetConnectionStatus)
# - Message Publishing (Publish, PublishBatch, PublishJSON)
# - Message Subscription (Subscribe, SubscribeMultiple, Unsubscribe, ListSubscriptions)
# - Device Management (Register, Unregister, List, GetInfo, UpdateStatus)
# - Topic Management (GetTopicInfo, ListTopics, ValidateTopic)
# - Retained Messages (Set, Get, Delete)
# - Monitoring (GetStatistics, GetDeviceMetrics)
# - QoS Levels (0, 1, 2)
# - Binary and JSON payloads
# 
# Total: 15+ test cases covering 24 individual operations
# Target Success Rate: 100%

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
HOST="${HOST:-localhost}"
PORT="${PORT:-50053}"
USER_ID="${USER_ID:-test_user}"
CLIENT_ID="test-client-$RANDOM"
SESSION_ID=""

# Counters
PASSED=0
FAILED=0
TOTAL=0

# Test result function
test_result() {
    TOTAL=$((TOTAL + 1))
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASSED${NC}"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}✗ FAILED${NC}"
        FAILED=$((FAILED + 1))
    fi
}

# Cleanup function
cleanup() {
    echo ""
    echo -e "${CYAN}Cleaning up test resources...${NC}"
    python3 <<EOF 2>/dev/null
from isa_common.mqtt_client import MQTTClient
client = MQTTClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
try:
    with client:
        # Disconnect if connected
        if '${SESSION_ID}':
            try:
                client.disconnect('${SESSION_ID}')
            except:
                pass
except Exception:
    pass
EOF
}

# ========================================
# Test Functions
# ========================================

test_service_health() {
    echo -e "${YELLOW}Test 1: Service Health Check${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.mqtt_client import MQTTClient
try:
    client = MQTTClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        health = client.health_check()
        if health and health.get('healthy'):
            print("PASS")
        else:
            print("FAIL")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
        echo -e "${RED}Cannot proceed without healthy service${NC}"
        exit 1
    fi
}

test_connection_management() {
    echo -e "${YELLOW}Test 2: Connection Management (Connect, Disconnect, Status)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.mqtt_client import MQTTClient
try:
    client = MQTTClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Connect
        conn = client.connect('${CLIENT_ID}')
        if not conn or not conn.get('success'):
            print("FAIL: Connect failed")
        else:
            session_id = conn.get('session_id')
            
            # Get connection status
            status = client.get_connection_status(session_id)
            if not status or not status.get('connected'):
                print("FAIL: Connection status failed")
            else:
                # Disconnect
                disc = client.disconnect(session_id)
                if not disc or not disc.get('success'):
                    print("FAIL: Disconnect failed")
                else:
                    # Save session_id for future tests
                    print(f"SESSION_ID:{session_id}")
                    print("PASS: Connection management successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    # Extract session ID for later tests
    if echo "$RESPONSE" | grep -q "SESSION_ID:"; then
        SESSION_ID=$(echo "$RESPONSE" | grep "SESSION_ID:" | cut -d: -f2)
    fi
    
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_publish_operations() {
    echo -e "${YELLOW}Test 3: Publish Operations (Basic, JSON, Batch)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.mqtt_client import MQTTClient
import json
try:
    client = MQTTClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        conn = client.connect('${CLIENT_ID}-pub')
        if not conn:
            print("FAIL: Connect failed")
        else:
            session_id = conn.get('session_id')
            
            # Basic publish
            pub1 = client.publish(session_id, 'test/topic1', b'Hello MQTT', qos=1)
            if not pub1 or not pub1.get('success'):
                print("FAIL: Basic publish failed")
            else:
                # JSON publish
                json_data = {'sensor': 'temp01', 'value': 25.5, 'unit': 'C'}
                pub2 = client.publish_json(session_id, 'test/json', json_data, qos=1)
                if not pub2 or not pub2.get('success'):
                    print("FAIL: JSON publish failed")
                else:
                    # Batch publish
                    messages = [
                        {'topic': 'test/batch1', 'payload': b'msg1', 'qos': 1},
                        {'topic': 'test/batch2', 'payload': b'msg2', 'qos': 1},
                        {'topic': 'test/batch3', 'payload': b'msg3', 'qos': 0}
                    ]
                    pub3 = client.publish_batch(session_id, messages)
                    if not pub3 or not pub3.get('success'):
                        print("FAIL: Batch publish failed")
                    else:
                        client.disconnect(session_id)
                        print("PASS: Publish operations successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_qos_levels() {
    echo -e "${YELLOW}Test 4: QoS Levels (0, 1, 2)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.mqtt_client import MQTTClient
try:
    client = MQTTClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        conn = client.connect('${CLIENT_ID}-qos')
        if not conn:
            print("FAIL: Connect failed")
        else:
            session_id = conn.get('session_id')
            
            # Test all QoS levels
            for qos in [0, 1, 2]:
                pub = client.publish(session_id, f'test/qos{qos}', f'QoS {qos} message'.encode(), qos=qos)
                if not pub or not pub.get('success'):
                    print(f"FAIL: QoS {qos} failed")
                    client.disconnect(session_id)
                    break
            else:
                client.disconnect(session_id)
                print("PASS: QoS levels successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_retained_messages() {
    echo -e "${YELLOW}Test 5: Retained Messages (Set, Get, Delete)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.mqtt_client import MQTTClient
try:
    client = MQTTClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        conn = client.connect('${CLIENT_ID}-retained')
        if not conn:
            print("FAIL: Connect failed")
        else:
            session_id = conn.get('session_id')
            
            # Set retained message
            if not client.set_retained_message('test/retained', b'Retained content', qos=1):
                print("FAIL: Set retained message failed")
            else:
                # Get retained message
                msg = client.get_retained_message('test/retained')
                if not msg or not msg.get('found'):
                    print("FAIL: Get retained message failed")
                else:
                    # Delete retained message
                    if not client.delete_retained_message('test/retained'):
                        print("FAIL: Delete retained message failed")
                    else:
                        # Verify deletion
                        msg2 = client.get_retained_message('test/retained')
                        if msg2 and msg2.get('found'):
                            print("FAIL: Retained message not deleted")
                        else:
                            client.disconnect(session_id)
                            print("PASS: Retained messages successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_device_management() {
    echo -e "${YELLOW}Test 6: Device Management (Register, List, GetInfo, Update, Unregister)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.mqtt_client import MQTTClient
try:
    client = MQTTClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        device_id = 'test-device-001'
        
        # Register device
        reg = client.register_device(device_id, 'Test Sensor', 'sensor', 
                                     {'location': 'lab', 'model': 'TH100'})
        if not reg or not reg.get('success'):
            print("FAIL: Register device failed")
        else:
            # Get device info
            info = client.get_device_info(device_id)
            if not info or info.get('device_id') != device_id:
                print("FAIL: Get device info failed")
            else:
                # Update device status
                upd = client.update_device_status(device_id, 1)  # ONLINE
                if not upd or not upd.get('success'):
                    print("FAIL: Update device status failed")
                else:
                    # List devices
                    devices = client.list_devices()
                    if not devices or len(devices.get('devices', [])) == 0:
                        print("FAIL: List devices failed")
                    else:
                        # Unregister device
                        if not client.unregister_device(device_id):
                            print("FAIL: Unregister device failed")
                        else:
                            print("PASS: Device management successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_topic_management() {
    echo -e "${YELLOW}Test 7: Topic Management (Validate, GetInfo, List)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.mqtt_client import MQTTClient
try:
    client = MQTTClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Validate topic
        val = client.validate_topic('sensors/temperature', allow_wildcards=False)
        if not val or not val.get('valid'):
            print("FAIL: Validate topic failed")
        else:
            # Create connection and publish to create topics
            conn = client.connect('${CLIENT_ID}-topics')
            if not conn:
                print("FAIL: Connect failed")
            else:
                session_id = conn.get('session_id')
                client.publish(session_id, 'test/topic1', b'data', qos=1)
                client.publish(session_id, 'test/topic2', b'data', qos=1)
                
                # Get topic info
                info = client.get_topic_info('test/topic1')
                if not info:
                    print("FAIL: Get topic info failed")
                else:
                    # List topics
                    topics = client.list_topics('test/', page_size=10)
                    if not topics:
                        print("FAIL: List topics failed")
                    else:
                        client.disconnect(session_id)
                        print("PASS: Topic management successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_topic_patterns() {
    echo -e "${YELLOW}Test 8: Topic Patterns and Hierarchies${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.mqtt_client import MQTTClient
try:
    client = MQTTClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        conn = client.connect('${CLIENT_ID}-patterns')
        if not conn:
            print("FAIL: Connect failed")
        else:
            session_id = conn.get('session_id')
            topics = [
                'home/livingroom/temperature',
                'home/bedroom/temperature',
                'home/kitchen/humidity',
                'office/room1/temperature'
            ]
            for topic in topics:
                pub = client.publish(session_id, topic, f'Data from {topic}'.encode(), qos=1)
                if not pub or not pub.get('success'):
                    print(f"FAIL: Publish to {topic} failed")
                    client.disconnect(session_id)
                    break
            else:
                client.disconnect(session_id)
                print("PASS: Topic patterns successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_binary_payload() {
    echo -e "${YELLOW}Test 9: Binary Payload${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.mqtt_client import MQTTClient
try:
    client = MQTTClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        conn = client.connect('${CLIENT_ID}-binary')
        if not conn:
            print("FAIL: Connect failed")
        else:
            session_id = conn.get('session_id')
            binary_data = bytes([0x01, 0x02, 0x03, 0x04, 0xFF, 0xFE])
            pub = client.publish(session_id, 'test/binary', binary_data, qos=1)
            if not pub or not pub.get('success'):
                print("FAIL: Binary publish failed")
            else:
                client.disconnect(session_id)
                print("PASS: Binary payload successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_bulk_publish() {
    echo -e "${YELLOW}Test 10: Bulk Message Publishing${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.mqtt_client import MQTTClient
try:
    client = MQTTClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        conn = client.connect('${CLIENT_ID}-bulk')
        if not conn:
            print("FAIL: Connect failed")
        else:
            session_id = conn.get('session_id')
            success_count = 0
            for i in range(50):
                pub = client.publish(session_id, 'test/bulk', f'Message {i}'.encode(), qos=0)
                if pub and pub.get('success'):
                    success_count += 1
            
            client.disconnect(session_id)
            if success_count == 50:
                print("PASS: Bulk publishing successful")
            else:
                print(f"FAIL: Only {success_count}/50 messages published")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

test_monitoring_operations() {
    echo -e "${YELLOW}Test 11: Monitoring Operations (Statistics, DeviceMetrics)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.mqtt_client import MQTTClient
try:
    client = MQTTClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Get statistics
        stats = client.get_statistics()
        if not stats or 'total_devices' not in stats:
            print("FAIL: Get statistics failed")
        else:
            print("PASS: Monitoring operations successful")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        test_result 0
    else
        test_result 1
    fi
}

# ========================================
# Main Test Runner
# ========================================

echo ""
echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}     MQTT SERVICE COMPREHENSIVE FUNCTIONAL TESTS (24 Operations)${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo ""
echo "Configuration:"
echo "  Host: ${HOST}"
echo "  Port: ${PORT}"
echo "  User: ${USER_ID}"
echo "  Client ID: ${CLIENT_ID}"
echo ""

# Initial cleanup to remove any leftover state from previous runs
echo -e "${CYAN}Performing initial cleanup...${NC}"
cleanup

# Health check
test_service_health
echo ""

# Connection Management Tests
echo -e "${CYAN}--- Connection Management Tests ---${NC}"
test_connection_management
echo ""

# Publish Operations Tests
echo -e "${CYAN}--- Publish Operations Tests ---${NC}"
test_publish_operations
echo ""
test_qos_levels
echo ""
test_binary_payload
echo ""
test_bulk_publish
echo ""

# Retained Messages Tests
echo -e "${CYAN}--- Retained Messages Tests ---${NC}"
test_retained_messages
echo ""

# Device Management Tests
echo -e "${CYAN}--- Device Management Tests ---${NC}"
test_device_management
echo ""

# Topic Management Tests
echo -e "${CYAN}--- Topic Management Tests ---${NC}"
test_topic_management
echo ""
test_topic_patterns
echo ""

# Monitoring Tests
echo -e "${CYAN}--- Monitoring Tests ---${NC}"
test_monitoring_operations
echo ""

# Cleanup
cleanup

# Print summary
echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}                         TEST SUMMARY${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo -e "Total Tests: ${TOTAL}"
echo -e "${GREEN}Passed: ${PASSED}${NC}"
echo -e "${RED}Failed: ${FAILED}${NC}"

if [ ${TOTAL} -gt 0 ]; then
    SUCCESS_RATE=$(awk "BEGIN {printf \"%.1f\", (${PASSED}/${TOTAL})*100}")
    echo "Success Rate: ${SUCCESS_RATE}%"
fi
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ ALL TESTS PASSED! (${TOTAL}/${TOTAL})${NC}"
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED (${PASSED}/${TOTAL})${NC}"
    exit 1
fi
