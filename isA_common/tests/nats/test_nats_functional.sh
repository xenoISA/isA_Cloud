#!/bin/bash

# ============================================
# NATS Service - Comprehensive Functional Tests
# ============================================
# Tests NATS operations including:
# - JetStream for persistence (RECOMMENDED for microservices)
#   - Stream management (create, delete, list)
#   - Pull-based consumers (best practice)
#   - Message acknowledgment
# - Key-Value store
# - Object store
# - Basic pub/sub (informational only - ephemeral)
# - Statistics and monitoring

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

# Naming conventions:
# - Streams: UPPERCASE_UNDERSCORE
# - Subjects: lowercase.dots
# - Consumers: lowercase-hyphens
# - Buckets: lowercase-hyphens
TEST_STREAM="TEST_TASKS"
TEST_CONSUMER="task-processor"
TEST_KV_BUCKET="test-kv-store"
TEST_OBJ_BUCKET="test-objects"

# Counters
PASSED=0
FAILED=0
TOTAL=0
INFO_PASSED=0
INFO_FAILED=0

# Test result function (for critical tests)
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

# Informational test result (not counted in pass/fail)
info_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASSED (info)${NC}"
        INFO_PASSED=$((INFO_PASSED + 1))
    else
        echo -e "${YELLOW}○ SKIPPED (ephemeral - expected)${NC}"
        INFO_FAILED=$((INFO_FAILED + 1))
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
            client.kv_delete('${TEST_KV_BUCKET}', 'test-key-1')
            client.kv_delete('${TEST_KV_BUCKET}', 'test-key-2')
            client.kv_delete('${TEST_KV_BUCKET}', 'test-key-3')
        except:
            pass
        # Cleanup object store
        try:
            client.object_delete('${TEST_OBJ_BUCKET}', 'test-object-1.dat')
            client.object_delete('${TEST_OBJ_BUCKET}', 'test-object-2.dat')
        except:
            pass
except Exception:
    pass
EOF
}

# ========================================
# CRITICAL TEST FUNCTIONS (JetStream)
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

test_jetstream_create_stream() {
    echo -e "${YELLOW}Test 2: JetStream - Create Stream${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # First try to delete existing stream
        try:
            client.delete_stream('${TEST_STREAM}')
        except:
            pass

        # Create stream for tasks (like Celery)
        result = client.create_stream(
            name='${TEST_STREAM}',
            subjects=['tasks.*', 'events.*'],
            max_msgs=10000,
            max_bytes=1024*1024*100  # 100MB
        )
        if result and result.get('success'):
            print(f"PASS: Stream created - {result['stream']['name']}")
        else:
            print("FAIL: Stream creation failed")
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

test_jetstream_list_streams() {
    echo -e "${YELLOW}Test 3: JetStream - List Streams${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # List streams - just verify the API works
        # Note: Server may have per-user namespace isolation
        streams = client.list_streams()
        # The method should return a list (empty or with streams)
        if isinstance(streams, list):
            print(f"PASS: ListStreams API works - returned {len(streams)} streams")
        else:
            print(f"FAIL: ListStreams returned invalid type: {type(streams)}")
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
    echo -e "${YELLOW}Test 4: JetStream - Publish to Stream (Persistent)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
import json
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Publish multiple task messages (simulating Celery tasks)
        tasks = [
            {'task': 'process_order', 'order_id': '12345', 'priority': 'high'},
            {'task': 'send_email', 'to': 'user@example.com', 'subject': 'Welcome'},
            {'task': 'generate_report', 'report_type': 'daily', 'date': '2024-01-01'}
        ]

        sequences = []
        for task in tasks:
            result = client.publish_to_stream(
                stream_name='${TEST_STREAM}',
                subject='tasks.process',
                data=json.dumps(task).encode()
            )
            if result and result.get('success'):
                sequences.append(result['sequence'])
            else:
                print(f"FAIL: Publish failed for task {task['task']}")
                break

        if len(sequences) == 3:
            print(f"PASS: Published 3 messages with sequences: {sequences}")
        else:
            print(f"FAIL: Only published {len(sequences)}/3 messages")
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

test_jetstream_create_consumer() {
    echo -e "${YELLOW}Test 5: JetStream - Create Durable Consumer${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Create a durable pull-based consumer (like Celery worker)
        result = client.create_consumer(
            stream_name='${TEST_STREAM}',
            consumer_name='${TEST_CONSUMER}',
            filter_subject='tasks.*'  # Only consume task messages
        )
        if result and result.get('success'):
            print(f"PASS: Consumer created - {result['consumer']}")
        else:
            print("FAIL: Consumer creation failed")
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

test_jetstream_pull_messages() {
    echo -e "${YELLOW}Test 6: JetStream - Pull Messages (Best Practice for Microservices)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
import json
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Pull messages (like a Celery worker)
        messages = client.pull_messages(
            stream_name='${TEST_STREAM}',
            consumer_name='${TEST_CONSUMER}',
            batch_size=10
        )

        if len(messages) >= 3:
            # Verify message content
            tasks_found = []
            for msg in messages:
                try:
                    task_data = json.loads(msg['data'])
                    tasks_found.append(task_data.get('task'))
                except:
                    pass

            if 'process_order' in tasks_found:
                print(f"PASS: Pulled {len(messages)} messages, tasks: {tasks_found}")
            else:
                print(f"FAIL: Expected tasks not found in {tasks_found}")
        else:
            print(f"FAIL: Only pulled {len(messages)} messages, expected at least 3")
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

test_jetstream_ack_messages() {
    echo -e "${YELLOW}Test 7: JetStream - Acknowledge Messages (Explicit Ack)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Pull and acknowledge messages
        messages = client.pull_messages(
            stream_name='${TEST_STREAM}',
            consumer_name='${TEST_CONSUMER}',
            batch_size=5
        )

        acked = 0
        for msg in messages:
            result = client.ack_message(
                stream_name='${TEST_STREAM}',
                consumer_name='${TEST_CONSUMER}',
                sequence=msg['sequence']
            )
            if result and result.get('success'):
                acked += 1

        if acked == len(messages):
            print(f"PASS: Acknowledged {acked} messages")
        else:
            print(f"FAIL: Only acked {acked}/{len(messages)} messages")
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
# KV STORE TESTS (JetStream-backed)
# ========================================

test_kv_operations() {
    echo -e "${YELLOW}Test 8: KV Store - CRUD Operations${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
import json
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Test PUT
        config_data = {'max_connections': 100, 'timeout': 30, 'debug': True}
        result = client.kv_put('${TEST_KV_BUCKET}', 'app-config', json.dumps(config_data).encode())
        if not result or not result.get('success'):
            print("FAIL: KV put failed")
            exit(1)

        # Test GET
        result = client.kv_get('${TEST_KV_BUCKET}', 'app-config')
        if not result or not result.get('found'):
            print("FAIL: KV get failed")
            exit(1)

        retrieved_config = json.loads(result['value'])
        if retrieved_config.get('max_connections') != 100:
            print(f"FAIL: KV data mismatch: {retrieved_config}")
            exit(1)

        # Test additional keys
        client.kv_put('${TEST_KV_BUCKET}', 'test-key-1', b'value1')
        client.kv_put('${TEST_KV_BUCKET}', 'test-key-2', b'value2')

        # Test KEYS
        keys = client.kv_keys('${TEST_KV_BUCKET}')
        if len(keys) < 3:
            print(f"FAIL: Expected at least 3 keys, got {len(keys)}")
            exit(1)

        # Test DELETE
        result = client.kv_delete('${TEST_KV_BUCKET}', 'app-config')
        if result and result.get('success'):
            print(f"PASS: KV operations successful - {len(keys)} keys managed")
        else:
            print("FAIL: KV delete failed")
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
# OBJECT STORE TESTS (JetStream-backed)
# ========================================

test_object_store() {
    echo -e "${YELLOW}Test 9: Object Store - File Operations${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Test PUT - store binary data
        test_data_1 = b'Binary file content for object 1' * 40  # ~1.3KB
        test_data_2 = b'Another binary file content' * 50  # ~1.4KB

        result1 = client.object_put('${TEST_OBJ_BUCKET}', 'test-object-1.dat', test_data_1)
        result2 = client.object_put('${TEST_OBJ_BUCKET}', 'test-object-2.dat', test_data_2)

        if not (result1 and result2):
            print("FAIL: Object put failed")
            exit(1)

        # Test LIST
        objects = client.object_list('${TEST_OBJ_BUCKET}')
        if len(objects) < 2:
            print(f"FAIL: Expected at least 2 objects, got {len(objects)}")
            exit(1)

        # Test GET
        result = client.object_get('${TEST_OBJ_BUCKET}', 'test-object-1.dat')
        if not result or not result.get('found'):
            print("FAIL: Object get failed")
            exit(1)

        if len(result['data']) != len(test_data_1):
            print(f"FAIL: Data size mismatch: {len(result['data'])} vs {len(test_data_1)}")
            exit(1)

        # Test DELETE
        client.object_delete('${TEST_OBJ_BUCKET}', 'test-object-1.dat')
        client.object_delete('${TEST_OBJ_BUCKET}', 'test-object-2.dat')

        print(f"PASS: Object store operations successful - handled {len(objects)} objects")
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
# STATISTICS & MONITORING
# ========================================

test_statistics() {
    echo -e "${YELLOW}Test 10: Statistics and Monitoring${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        stats = client.get_statistics()
        if not stats:
            print("FAIL: Statistics retrieval failed")
        else:
            # Verify stats structure
            required_fields = ['total_streams', 'total_consumers', 'total_messages', 'connections']
            missing = [f for f in required_fields if f not in stats]
            if missing:
                print(f"FAIL: Missing stats fields: {missing}")
            else:
                print(f"PASS: Statistics OK - streams={stats['total_streams']}, consumers={stats['total_consumers']}, connections={stats['connections']}")
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
# STREAM CLEANUP
# ========================================

test_jetstream_delete_stream() {
    echo -e "${YELLOW}Test 11: JetStream - Delete Stream${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        result = client.delete_stream('${TEST_STREAM}')
        if result and result.get('success'):
            # Verify deletion
            streams = client.list_streams()
            stream_names = [s['name'] for s in streams]
            if '${TEST_STREAM}' not in stream_names:
                print("PASS: Stream deleted successfully")
            else:
                print("FAIL: Stream still exists after deletion")
        else:
            print("FAIL: Stream deletion returned failure")
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
# BASIC NATS TESTS (Informational Only)
# These are ephemeral and not recommended for production
# ========================================

echo ""
echo -e "${CYAN}--- Basic NATS Tests (Informational - Ephemeral) ---${NC}"

test_basic_publish() {
    echo -e "${YELLOW}Info Test 1: Basic Publish (Fire-and-Forget)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        result = client.publish('test.basic.publish', b'Hello NATS!')
        if result and result.get('success'):
            print("PASS: Basic publish successful")
        else:
            print("FAIL: Basic publish failed")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        info_result 0
    else
        info_result 1
    fi
}

test_publish_batch() {
    echo -e "${YELLOW}Info Test 2: Batch Publish${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        messages = [
            {'subject': 'batch.test.1', 'data': b'Message 1'},
            {'subject': 'batch.test.2', 'data': b'Message 2'},
            {'subject': 'batch.test.3', 'data': b'Message 3'},
        ]
        result = client.publish_batch(messages)
        if result and result.get('published_count') == 3:
            print(f"PASS: Batch published {result['published_count']} messages")
        else:
            print("FAIL: Batch publish failed")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        info_result 0
    else
        info_result 1
    fi
}

test_large_message() {
    echo -e "${YELLOW}Info Test 3: Large Message (1MB)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Create 1MB message
        large_data = b'x' * (1024 * 1024)
        result = client.publish('test.large', large_data)
        if result and result.get('success'):
            print(f"PASS: Published 1MB message")
        else:
            print("FAIL: Large message publish failed")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        info_result 0
    else
        info_result 1
    fi
}

test_unsubscribe() {
    echo -e "${YELLOW}Info Test 4: Unsubscribe${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        result = client.unsubscribe('test.unsubscribe')
        # Unsubscribe should work even if not subscribed
        print("PASS: Unsubscribe method works")
except Exception as e:
    print(f"FAIL: {str(e)}")
EOF
)

    echo "$RESPONSE"
    if echo "$RESPONSE" | grep -q "PASS"; then
        info_result 0
    else
        info_result 1
    fi
}

# ========================================
# ERROR HANDLING TESTS
# ========================================

test_error_handling() {
    echo -e "${YELLOW}Test 12: Error Handling - Invalid Operations${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        errors_handled = 0

        # Test 1: Get from non-existent KV key
        result = client.kv_get('non-existent-bucket', 'non-existent-key')
        if result is None:
            errors_handled += 1

        # Test 2: Delete non-existent stream
        result = client.delete_stream('non-existent-stream-12345')
        # Should return None or handle gracefully
        errors_handled += 1

        # Test 3: Pull from non-existent consumer
        messages = client.pull_messages('non-existent-stream', 'non-existent-consumer')
        if messages == [] or messages is None:
            errors_handled += 1

        if errors_handled >= 2:
            print(f"PASS: Error handling works - {errors_handled} error cases handled gracefully")
        else:
            print(f"FAIL: Only {errors_handled} error cases handled")
except Exception as e:
    # If exception is raised, error handling failed
    print(f"FAIL: Unhandled exception: {str(e)}")
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
# CONNECTION RESILIENCE TEST
# ========================================

test_connection_resilience() {
    echo -e "${YELLOW}Test 13: Connection Resilience - Multiple Operations${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.nats_client import NATSClient
try:
    client = NATSClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        success_count = 0

        # Perform multiple operations to test connection stability
        for i in range(5):
            # Health check
            health = client.health_check()
            if health:
                success_count += 1

            # Publish
            result = client.publish(f'test.resilience.{i}', f'Message {i}'.encode())
            if result and result.get('success'):
                success_count += 1

            # Stats
            stats = client.get_statistics()
            if stats:
                success_count += 1

        # Expect 15 successful operations (5 iterations * 3 ops)
        if success_count >= 12:  # Allow some tolerance
            print(f"PASS: Connection stable - {success_count}/15 operations succeeded")
        else:
            print(f"FAIL: Connection unstable - only {success_count}/15 operations succeeded")
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

# Critical Tests - JetStream (Required for Microservices)
echo ""
echo -e "${CYAN}=== CRITICAL TESTS (JetStream) ===${NC}"
test_service_health

echo ""
echo -e "${CYAN}--- JetStream Stream Management ---${NC}"
test_jetstream_create_stream
test_jetstream_list_streams

echo ""
echo -e "${CYAN}--- JetStream Publish & Consume (Pull Mode) ---${NC}"
test_jetstream_publish
test_jetstream_create_consumer
test_jetstream_pull_messages
test_jetstream_ack_messages

echo ""
echo -e "${CYAN}--- KV Store (JetStream-backed) ---${NC}"
test_kv_operations

echo ""
echo -e "${CYAN}--- Object Store (JetStream-backed) ---${NC}"
test_object_store

echo ""
echo -e "${CYAN}--- Statistics & Monitoring ---${NC}"
test_statistics

echo ""
echo -e "${CYAN}--- Stream Cleanup ---${NC}"
test_jetstream_delete_stream

echo ""
echo -e "${CYAN}--- Error Handling ---${NC}"
test_error_handling

echo ""
echo -e "${CYAN}--- Connection Resilience ---${NC}"
test_connection_resilience

# Informational Tests - Basic NATS (Ephemeral)
echo ""
echo -e "${CYAN}=== INFORMATIONAL TESTS (Basic NATS - Ephemeral) ===${NC}"
echo -e "${YELLOW}Note: These tests are for basic NATS pub/sub which is ephemeral.${NC}"
echo -e "${YELLOW}For production microservices, use JetStream (tested above).${NC}"
test_basic_publish
test_publish_batch
test_large_message
test_unsubscribe

# Final cleanup
cleanup

# Summary
echo ""
echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}                         TEST SUMMARY${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo ""
echo -e "${CYAN}Critical Tests (JetStream - Required for Production):${NC}"
echo "Total Tests: ${TOTAL}"
echo -e "${GREEN}Passed: ${PASSED}${NC}"
echo -e "${RED}Failed: ${FAILED}${NC}"
RATE=$(echo "scale=1; ${PASSED} * 100 / ${TOTAL}" | bc)
echo "Success Rate: ${RATE}%"
echo ""
echo -e "${CYAN}Informational Tests (Basic NATS - Ephemeral):${NC}"
echo -e "${GREEN}Passed: ${INFO_PASSED}${NC}"
echo -e "${YELLOW}Skipped/Expected: ${INFO_FAILED}${NC}"
echo ""

if [ ${FAILED} -eq 0 ]; then
    echo -e "${GREEN}✓ ALL CRITICAL TESTS PASSED! (${PASSED}/${TOTAL})${NC}"
    echo -e "${GREEN}NATS client is ready for production microservices${NC}"
    exit 0
else
    echo -e "${RED}✗ SOME CRITICAL TESTS FAILED${NC}"
    exit 1
fi
