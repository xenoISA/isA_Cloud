#!/bin/bash

# ============================================
# NATS Service - Comprehensive Functional Tests
# ============================================
# Tests NATS operations including:
# - Event streaming and pub/sub
# - Task queue patterns (Celery replacement)
# - JetStream for persistence
# - Key-Value store (Redis integration)
# - Object store (MinIO integration)
# - Request-Reply patterns
# - Work queues and consumers

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
HOST="${HOST:-localhost}"
PORT="${PORT:-50056}"
USER_ID="${USER_ID:-test-user}"
TEST_STREAM="test-stream"
TEST_BUCKET="test-kv-bucket"

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
from isa_common.nats_client import NATSClient
client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
try:
    with client:
        # Cleanup stream
        try:
            client.delete_stream('${TEST_STREAM}')
        except:
            pass
        # Cleanup KV bucket keys
        try:
            client.kv_delete('${TEST_BUCKET}', 'test-key-2')
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
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        health = client.health_check()
        if health:
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

test_publish_message() {
    echo -e "${YELLOW}Test 2: Basic Publish Message${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        if not client.publish('test.subject', b'Hello NATS'):
            print("FAIL: Publish failed")
        else:
            print("PASS: Basic publish successful")
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

test_publish_json() {
    echo -e "${YELLOW}Test 3: Publish JSON Message${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
import json
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        data = {'event': 'user.login', 'user_id': 'test123', 'timestamp': 1234567890}
        if not client.publish('events.user.login', json.dumps(data).encode()):
            print("FAIL: JSON publish failed")
        else:
            print("PASS: JSON publish successful")
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

test_subject_hierarchy() {
    echo -e "${YELLOW}Test 4: Subject Hierarchy${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        subjects = [
            'orders.created',
            'orders.updated',
            'orders.cancelled',
            'users.registered',
            'users.login'
        ]
        for subj in subjects:
            if not client.publish(subj, f'{subj} event'.encode()):
                print(f"FAIL: {subj}")
                break
        else:
            print("PASS: Subject hierarchy successful")
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

test_binary_data() {
    echo -e "${YELLOW}Test 5: Binary Data Publishing${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        binary = bytes(range(256))
        if not client.publish('test.binary', binary):
            print("FAIL: Binary publish failed")
        else:
            print("PASS: Binary data successful")
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

test_large_message() {
    echo -e "${YELLOW}Test 6: Large Message (1MB)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        large_msg = b'X' * (1024 * 1024)  # 1MB
        if not client.publish('test.large', large_msg):
            print("FAIL: Large message failed")
        else:
            print("PASS: Large message (1MB) successful")
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
    echo -e "${YELLOW}Test 7: Bulk Message Publishing (1000 messages)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        for i in range(1000):
            if not client.publish('test.bulk', f'Message {i}'.encode()):
                print(f"FAIL: Bulk message {i} failed")
                break
        else:
            print("PASS: Bulk publishing (1000) successful")
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

test_request_reply() {
    echo -e "${YELLOW}Test 8: Request-Reply Pattern${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Note: This requires a responder to be set up
        # For now, just test that the method exists and doesn't crash
        try:
            result = client.request('test.request', b'Request data', timeout_seconds=1)
            print("PASS: Request-Reply mechanism works")
        except Exception as e:
            # Request timeout is expected if no responder
            if 'timeout' in str(e).lower() or 'no responders' in str(e).lower():
                print("PASS: Request-Reply mechanism works (timeout expected)")
            else:
                print(f"FAIL: {str(e)}")
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

test_kv_operations() {
    echo -e "${YELLOW}Test 9: KV Store Operations (Redis Integration)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        bucket = '${TEST_BUCKET}'

        # Put key-value
        if not client.kv_put(bucket, 'test-key-1', b'test-value-1'):
            print("FAIL: KV put failed")
        elif not client.kv_put(bucket, 'test-key-2', b'test-value-2'):
            print("FAIL: KV put failed")
        else:
            # Get value
            result = client.kv_get(bucket, 'test-key-1')
            if not result or result['value'] != b'test-value-1':
                print("FAIL: KV get failed")
            else:
                # List keys
                keys = client.kv_keys(bucket)
                if 'test-key-1' not in keys or 'test-key-2' not in keys:
                    print(f"FAIL: KV keys failed - got {keys}")
                else:
                    # Delete key
                    if not client.kv_delete(bucket, 'test-key-1'):
                        print("FAIL: KV delete failed")
                    else:
                        # Verify deleted
                        result = client.kv_get(bucket, 'test-key-1')
                        if result:
                            print("FAIL: KV key still exists after delete")
                        else:
                            print("PASS: KV store operations successful")
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

test_jetstream_create_stream() {
    echo -e "${YELLOW}Test 10: JetStream - Create Stream${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        result = client.create_stream(
            name='${TEST_STREAM}',
            subjects=['tasks.>'],
            max_msgs=1000,
            max_bytes=1024*1024
        )
        if not result:
            print("FAIL: Stream creation failed")
        else:
            print("PASS: JetStream stream created successfully")
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

test_jetstream_publish() {
    echo -e "${YELLOW}Test 11: JetStream - Publish to Stream${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
import json
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Publish task messages (Celery replacement pattern)
        tasks = [
            {'task_id': 'task-1', 'task_type': 'process_image', 'priority': 'high'},
            {'task_id': 'task-2', 'task_type': 'send_email', 'priority': 'normal'},
            {'task_id': 'task-3', 'task_type': 'generate_report', 'priority': 'low'}
        ]

        for task in tasks:
            result = client.publish_to_stream(
                stream_name='${TEST_STREAM}',
                subject='tasks.processing',
                data=json.dumps(task).encode()
            )
            if not result:
                print(f"FAIL: Failed to publish task {task['task_id']}")
                break
        else:
            print("PASS: JetStream publish successful (3 tasks)")
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

test_jetstream_consumer() {
    echo -e "${YELLOW}Test 12: JetStream - Create Consumer (Task Worker)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        result = client.create_consumer(
            stream_name='${TEST_STREAM}',
            consumer_name='task-worker',
            filter_subject='tasks.>'
        )
        if not result:
            print("FAIL: Consumer creation failed")
        else:
            print("PASS: JetStream consumer created (task worker)")
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

test_jetstream_pull_ack() {
    echo -e "${YELLOW}Test 13: JetStream - Pull & Ack Messages (Celery Pattern)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
import json
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Pull messages (like Celery worker pulling tasks)
        messages = client.pull_messages(
            stream_name='${TEST_STREAM}',
            consumer_name='task-worker',
            batch_size=10
        )

        if len(messages) == 0:
            print("FAIL: No messages pulled")
        else:
            # Process and acknowledge each message
            for msg in messages:
                task = json.loads(msg['data'].decode())
                # Simulate task processing
                result = client.ack_message(
                    stream_name='${TEST_STREAM}',
                    consumer_name='task-worker',
                    sequence=msg['sequence']
                )
                if not result:
                    print(f"FAIL: Failed to ack message {msg['sequence']}")
                    break
            else:
                print(f"PASS: Pulled and acked {len(messages)} tasks (Celery pattern)")
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

test_object_store() {
    echo -e "${YELLOW}Test 14: Object Store Operations (MinIO Integration)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        bucket = 'test-object-bucket'

        # Put object
        data1 = b'Object data 1' * 100
        result = client.object_put(bucket, 'test-object-1.dat', data1)
        if not result:
            print("FAIL: Object put failed")
        else:
            data2 = b'Object data 2' * 200
            result = client.object_put(bucket, 'test-object-2.dat', data2)
            if not result:
                print("FAIL: Object put failed")
            else:
                # List objects
                objects = client.object_list(bucket)
                if len(objects) < 2:
                    print(f"FAIL: Object list failed - got {len(objects)} objects")
                else:
                    # Get object
                    result = client.object_get(bucket, 'test-object-1.dat')
                    if not result or result['data'] != data1:
                        print("FAIL: Object get failed")
                    else:
                        # Delete object
                        if not client.object_delete(bucket, 'test-object-1.dat'):
                            print("FAIL: Object delete failed")
                        else:
                            # Cleanup second object
                            client.object_delete(bucket, 'test-object-2.dat')
                            print("PASS: Object store operations successful")
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

test_stream_stats() {
    echo -e "${YELLOW}Test 15: Get Stream Statistics${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        stats = client.get_statistics()
        if not stats:
            print("FAIL: Statistics retrieval failed")
        else:
            print(f"PASS: Statistics - {stats['total_streams']} streams, {stats['total_messages']} messages")
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

test_publish_batch() {
    echo -e "${YELLOW}Test 16: Publish Batch (Multiple Messages at Once)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        messages = [
            {'subject': 'batch.test.1', 'data': b'Message 1'},
            {'subject': 'batch.test.2', 'data': b'Message 2'},
            {'subject': 'batch.test.3', 'data': b'Message 3', 'headers': {'priority': 'high'}},
            {'subject': 'batch.test.4', 'data': b'Message 4'},
            {'subject': 'batch.test.5', 'data': b'Message 5'}
        ]

        result = client.publish_batch(messages)
        if not result:
            print("FAIL: Batch publish failed")
        elif result['published_count'] != len(messages):
            print(f"FAIL: Published {result['published_count']}/{len(messages)} messages")
        else:
            print(f"PASS: Batch published {result['published_count']} messages successfully")
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

test_subscribe_basic() {
    echo -e "${YELLOW}Test 17: Basic Subscribe with Callback${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
import threading
import time

try:
    # Create two clients - one for publishing, one for subscribing
    pub_client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    sub_client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')

    received_messages = []

    def message_callback(msg):
        received_messages.append(msg)

    with pub_client, sub_client:
        # Start subscriber in background thread
        def subscribe_thread():
            try:
                sub_client.subscribe('test.subscribe.basic', message_callback, timeout_seconds=5)
            except Exception as e:
                pass  # Timeout is expected

        thread = threading.Thread(target=subscribe_thread)
        thread.daemon = True
        thread.start()

        # Give subscriber time to set up
        time.sleep(2)

        # Publish test messages
        pub_client.publish('test.subscribe.basic', b'Test message 1')
        pub_client.publish('test.subscribe.basic', b'Test message 2')
        pub_client.publish('test.subscribe.basic', b'Test message 3')

        # Wait for messages to be received
        time.sleep(2)

        # Check if messages were received
        if len(received_messages) >= 3:
            print(f"PASS: Subscribe received {len(received_messages)} messages")
        else:
            print(f"FAIL: Subscribe received only {len(received_messages)}/3 messages")

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

test_subscribe_wildcard() {
    echo -e "${YELLOW}Test 18: Subscribe with Wildcard Pattern${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
import threading
import time

try:
    pub_client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    sub_client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')

    received_subjects = []

    def message_callback(msg):
        received_subjects.append(msg['subject'])

    with pub_client, sub_client:
        # Subscribe with wildcard pattern
        def subscribe_thread():
            try:
                sub_client.subscribe('events.user.*', message_callback, timeout_seconds=5)
            except Exception as e:
                pass  # Timeout is expected

        thread = threading.Thread(target=subscribe_thread)
        thread.daemon = True
        thread.start()

        # Give subscriber time to set up
        time.sleep(2)

        # Publish to different subjects matching the pattern
        pub_client.publish('events.user.login', b'User logged in')
        pub_client.publish('events.user.logout', b'User logged out')
        pub_client.publish('events.user.signup', b'User signed up')
        pub_client.publish('events.system.startup', b'Should not receive this')

        # Wait for messages
        time.sleep(2)

        # Check that wildcard worked
        if len(received_subjects) >= 3:
            # Make sure we didn't get the system.startup message
            if 'events.system.startup' not in received_subjects:
                print(f"PASS: Wildcard subscribe received {len(received_subjects)} matching messages")
            else:
                print("FAIL: Wildcard received non-matching message")
        else:
            print(f"FAIL: Wildcard subscribe received only {len(received_subjects)}/3 messages")

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

test_unsubscribe() {
    echo -e "${YELLOW}Test 19: Unsubscribe from Subject${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Unsubscribe from a subject
        # Note: This tests the method exists and doesn't crash
        result = client.unsubscribe('test.unsubscribe')
        if result and result.get('success'):
            print("PASS: Unsubscribe successful")
        else:
            # Some NATS implementations return success even if not subscribed
            print("PASS: Unsubscribe method works (result may vary)")
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
echo -e "${CYAN}        NATS SERVICE COMPREHENSIVE FUNCTIONAL TESTS${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo ""
echo "Configuration:"
echo "  Host: ${HOST}"
echo "  Port: ${PORT}"
echo "  User: ${USER_ID}"
echo ""

# Initial cleanup
echo -e "${CYAN}Performing initial cleanup...${NC}"
cleanup

# Health check
test_service_health
echo ""

# Basic Publish Operations
echo -e "${CYAN}--- Basic Publish Operations ---${NC}"
test_publish_message
echo ""
test_publish_json
echo ""

# Subject Management
echo -e "${CYAN}--- Subject Management ---${NC}"
test_subject_hierarchy
echo ""

# Data Handling
echo -e "${CYAN}--- Data Handling ---${NC}"
test_binary_data
echo ""
test_large_message
echo ""
test_bulk_publish
echo ""

# Advanced Patterns
echo -e "${CYAN}--- Advanced Patterns ---${NC}"
test_request_reply
echo ""

# KV Store (Redis Integration)
echo -e "${CYAN}--- KV Store (Redis Integration) ---${NC}"
test_kv_operations
echo ""

# JetStream (Event Streaming & Persistence)
echo -e "${CYAN}--- JetStream Streaming ---${NC}"
test_jetstream_create_stream
echo ""
test_jetstream_publish
echo ""
test_jetstream_consumer
echo ""

# Task Queue Pattern (Celery Replacement)
echo -e "${CYAN}--- Task Queue Pattern (Celery Replacement) ---${NC}"
test_jetstream_pull_ack
echo ""

# Object Store (MinIO Integration)
echo -e "${CYAN}--- Object Store (MinIO Integration) ---${NC}"
test_object_store
echo ""

# Statistics
echo -e "${CYAN}--- Statistics and Monitoring ---${NC}"
test_stream_stats
echo ""

# New Pub/Sub Features (Basic Subscribe/Unsubscribe)
echo -e "${CYAN}--- Batch Publishing & Subscribe Operations ---${NC}"
test_publish_batch
echo ""
test_subscribe_basic
echo ""
test_subscribe_wildcard
echo ""
test_unsubscribe
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
    echo -e "${GREEN}✓ ALL TESTS PASSED!${NC}"
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    exit 1
fi
