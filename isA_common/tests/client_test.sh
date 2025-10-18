#!/bin/bash

# ============================================
# isA Platform - gRPC Client Test Script
# ============================================
# Tests all Python gRPC clients for proper functionality
#
# File: isa_common/tests/client_test.sh
# Usage: ./isa_common/tests/client_test.sh [--host HOST] [--user-id USER]
#
# Tests:
#   - MinIO Client (port 50051)
#   - DuckDB Client (port 50052)
#   - MQTT Client (port 50053)
#   - Loki Client (port 50054)
#   - Redis Client (port 50055)
#   - NATS Client (port 50056)
#   - Supabase Client (port 50057)

# Don't exit on error - we want to see all test failures
# set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HOST="${GRPC_HOST:-localhost}"
USER_ID="${GRPC_USER_ID:-test_user}"
ORG_ID="${GRPC_ORG_ID:-test_org}"

# Test results tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
SKIPPED_TESTS=0
VERBOSE=""

# Function to print colored messages
print_header() {
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}========================================${NC}"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[ PASS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ FAIL]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[� SKIP]${NC} $1"
}

print_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

# Function to check if service is available
check_service_available() {
    local port=$1
    local service_name=$2

    if nc -z ${HOST} ${port} 2>/dev/null; then
        return 0
    else
        print_warning "${service_name} not available on ${HOST}:${port}"
        return 1
    fi
}

# Function to run Python test and capture result
run_python_test() {
    local test_name=$1
    local python_code=$2

    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    print_test "${test_name}"

    # Run test and capture both stdout/stderr and exit code
    local exit_code=0
    python3 -c "${python_code}" > /tmp/test_output_$$.log 2>&1 || exit_code=$?

    # Check for common error patterns in output
    if grep -q "Traceback\|ModuleNotFoundError\|ImportError\|Error:" /tmp/test_output_$$.log 2>/dev/null; then
        FAILED_TESTS=$((FAILED_TESTS + 1))
        print_error "${test_name}"
        echo "Error details:"
        cat /tmp/test_output_$$.log | sed 's/^/  /'
        rm -f /tmp/test_output_$$.log
        return 1
    fi

    # Check exit code
    if [ $exit_code -ne 0 ]; then
        FAILED_TESTS=$((FAILED_TESTS + 1))
        print_error "${test_name}"
        echo "Exit code: $exit_code"
        echo "Output:"
        cat /tmp/test_output_$$.log | sed 's/^/  /'
        rm -f /tmp/test_output_$$.log
        return 1
    fi

    # Test passed
    PASSED_TESTS=$((PASSED_TESTS + 1))
    print_success "${test_name}"

    # Show output if verbose
    if [ -n "$VERBOSE" ]; then
        cat /tmp/test_output_$$.log | sed 's/^/  /'
    fi

    rm -f /tmp/test_output_$$.log
    return 0
}

# Function to skip test
skip_test() {
    local test_name=$1
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    SKIPPED_TESTS=$((SKIPPED_TESTS + 1))
    print_warning "${test_name}"
}

# ============================================
# Test MinIO Client
# ============================================
test_minio_client() {
    print_header "Testing MinIO Client (port 50051)"

    if ! check_service_available 50051 "MinIO gRPC Service"; then
        skip_test "MinIO Client - Service unavailable"
        return
    fi

    # Test 1: Health check
    run_python_test "MinIO - Health Check" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.minio_client import MinIOClient

try:
    with MinIOClient(host='${HOST}', port=50051, user_id='${USER_ID}') as client:
        result = client.health_check()
        if result and result.get('healthy'):
            print(' MinIO health check passed')
            sys.exit(0)
        else:
            print(' MinIO not healthy')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"

    # Test 2: List buckets
    run_python_test "MinIO - List Buckets" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.minio_client import MinIOClient

try:
    with MinIOClient(host='${HOST}', port=50051, user_id='${USER_ID}') as client:
        buckets = client.list_buckets()
        print(f' Listed {len(buckets)} buckets')
        sys.exit(0)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"

    # Test 3: Create and delete bucket
    run_python_test "MinIO - Create/Delete Bucket" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.minio_client import MinIOClient

try:
    with MinIOClient(host='${HOST}', port=50051, user_id='${USER_ID}') as client:
        bucket_name = 'test-bucket-001'

        # Create bucket
        if client.create_bucket(bucket_name):
            print(f' Created bucket: {bucket_name}')
        else:
            print(f'� Bucket may already exist')

        # Delete bucket
        if client.delete_bucket(bucket_name):
            print(f' Deleted bucket: {bucket_name}')

        sys.exit(0)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"
}

# ============================================
# Test DuckDB Client
# ============================================
test_duckdb_client() {
    print_header "Testing DuckDB Client (port 50052)"

    if ! check_service_available 50052 "DuckDB gRPC Service"; then
        skip_test "DuckDB Client - Service unavailable"
        return
    fi

    # Test 1: Health check
    run_python_test "DuckDB - Health Check" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.duckdb_client import DuckDBClient

try:
    with DuckDBClient(host='${HOST}', port=50052, user_id='${USER_ID}') as client:
        result = client.health_check()
        if result:
            print(' DuckDB health check passed')
            sys.exit(0)
        else:
            print(' DuckDB not healthy')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"

    # Test 2: Execute query
    run_python_test "DuckDB - Execute Query" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.duckdb_client import DuckDBClient

try:
    with DuckDBClient(host='${HOST}', port=50052, user_id='${USER_ID}') as client:
        # Use correct database_id format: {user_id}-{database_name}
        result = client.execute_query('${USER_ID}-testdb', 'SELECT 1 as test')
        if result:
            print(f' Query executed successfully')
            sys.exit(0)
        else:
            print(' Query failed')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"
}

# ============================================
# Test MQTT Client
# ============================================
test_mqtt_client() {
    print_header "Testing MQTT Client (port 50053)"

    if ! check_service_available 50053 "MQTT gRPC Service"; then
        skip_test "MQTT Client - Service unavailable"
        return
    fi

    # Test 1: Health check
    run_python_test "MQTT - Health Check" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.mqtt_client import MQTTClient

try:
    with MQTTClient(host='${HOST}', port=50053, user_id='${USER_ID}') as client:
        result = client.health_check()
        if result:
            print(' MQTT health check passed')
            sys.exit(0)
        else:
            print(' MQTT not healthy')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"

    # Test 2: Publish message
    run_python_test "MQTT - Publish Message" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.mqtt_client import MQTTClient

try:
    with MQTTClient(host='${HOST}', port=50053, user_id='${USER_ID}') as client:
        result = client.publish('test-session-001', 'test/topic', b'Hello from test script')
        if result:
            print(' Published message successfully')
            sys.exit(0)
        else:
            print(' Publish failed')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"
}

# ============================================
# Test Loki Client
# ============================================
test_loki_client() {
    print_header "Testing Loki Client (port 50054)"

    if ! check_service_available 50054 "Loki gRPC Service"; then
        skip_test "Loki Client - Service unavailable"
        return
    fi

    # Test 1: Health check
    run_python_test "Loki - Health Check" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.loki_client import LokiClient

try:
    with LokiClient(host='${HOST}', port=50054, user_id='${USER_ID}', organization_id='${ORG_ID}') as client:
        result = client.health_check()
        if result and result.get('healthy'):
            print(' Loki health check passed')
            sys.exit(0)
        else:
            print(' Loki not healthy')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"

    # Test 2: Push simple log
    run_python_test "Loki - Push Simple Log" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.loki_client import LokiClient

try:
    with LokiClient(host='${HOST}', port=50054, user_id='${USER_ID}', organization_id='${ORG_ID}') as client:
        result = client.push_simple_log(
            message='Test log from client test script',
            service='client-test',
            level='INFO'
        )
        if result and result.get('success'):
            print(' Log pushed successfully')
            sys.exit(0)
        else:
            print(' Log push failed')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"

    # Test 3: Query logs
    run_python_test "Loki - Query Logs" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.loki_client import LokiClient

try:
    with LokiClient(host='${HOST}', port=50054, user_id='${USER_ID}', organization_id='${ORG_ID}') as client:
        logs = client.query_logs(query='{service=\"client-test\"}', limit=10)
        print(f' Query returned {len(logs)} logs')
        sys.exit(0)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"

    # Test 4: Get user quota
    run_python_test "Loki - Get User Quota" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.loki_client import LokiClient

try:
    with LokiClient(host='${HOST}', port=50054, user_id='${USER_ID}', organization_id='${ORG_ID}') as client:
        quota = client.get_user_quota()
        if quota:
            print(f' Quota info retrieved: {quota.get(\"today_used\")}/{quota.get(\"daily_limit\")} logs today')
            sys.exit(0)
        else:
            print(' Failed to get quota')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"
}

# ============================================
# Test Redis Client
# ============================================
test_redis_client() {
    print_header "Testing Redis Client (port 50055)"

    if ! check_service_available 50055 "Redis gRPC Service"; then
        skip_test "Redis Client - Service unavailable"
        return
    fi

    # Test 1: Health check
    run_python_test "Redis - Health Check" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.redis_client import RedisClient

try:
    with RedisClient(host='${HOST}', port=50055, user_id='${USER_ID}', organization_id='${ORG_ID}') as client:
        result = client.health_check()
        if result and result.get('healthy'):
            print(' Redis health check passed')
            sys.exit(0)
        else:
            print(' Redis not healthy')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"

    # Test 2: Set and Get
    run_python_test "Redis - Set/Get Operations" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.redis_client import RedisClient

try:
    with RedisClient(host='${HOST}', port=50055, user_id='${USER_ID}', organization_id='${ORG_ID}') as client:
        # Set value
        if not client.set('test:key', 'test_value'):
            print(' Set failed')
            sys.exit(1)

        # Get value
        value = client.get('test:key')
        if value == 'test_value':
            print(' Set/Get operations successful')

            # Clean up
            client.delete('test:key')
            sys.exit(0)
        else:
            print(f' Get returned wrong value: {value}')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"

    # Test 3: Counter operations
    run_python_test "Redis - Counter Operations" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.redis_client import RedisClient

try:
    with RedisClient(host='${HOST}', port=50055, user_id='${USER_ID}', organization_id='${ORG_ID}') as client:
        # Increment
        count1 = client.incr('test:counter')
        count2 = client.incr('test:counter')

        if count2 == count1 + 1:
            print(' Counter increment works')

            # Clean up
            client.delete('test:counter')
            sys.exit(0)
        else:
            print(f' Counter increment failed: {count1} -> {count2}')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"

    # Test 4: Hash operations
    run_python_test "Redis - Hash Operations" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.redis_client import RedisClient

try:
    with RedisClient(host='${HOST}', port=50055, user_id='${USER_ID}', organization_id='${ORG_ID}') as client:
        # Set hash fields
        client.hset('test:hash', 'field1', 'value1')
        client.hset('test:hash', 'field2', 'value2')

        # Get all hash fields
        hash_data = client.hgetall('test:hash')

        if hash_data.get('field1') == 'value1' and hash_data.get('field2') == 'value2':
            print(' Hash operations successful')

            # Clean up
            client.delete('test:hash')
            sys.exit(0)
        else:
            print(f' Hash operations failed: {hash_data}')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"

    # Test 5: List operations
    run_python_test "Redis - List Operations" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.redis_client import RedisClient

try:
    with RedisClient(host='${HOST}', port=50055, user_id='${USER_ID}', organization_id='${ORG_ID}') as client:
        # Clean up any leftover data first
        client.delete('test:list')

        # Push to list
        client.rpush('test:list', ['item1', 'item2', 'item3'])

        # Get list range
        items = client.lrange('test:list', 0, -1)

        if len(items) == 3 and items[0] == 'item1':
            print(' List operations successful')

            # Clean up
            client.delete('test:list')
            sys.exit(0)
        else:
            print(f' List operations failed: {items}')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"
}

# ============================================
# Test NATS Client
# ============================================
test_nats_client() {
    print_header "Testing NATS Client (port 50056)"

    if ! check_service_available 50056 "NATS gRPC Service"; then
        skip_test "NATS Client - Service unavailable"
        return
    fi

    # Test 1: Health check
    run_python_test "NATS - Health Check" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.nats_client import NATSClient

try:
    with NATSClient(host='${HOST}', port=50056, user_id='${USER_ID}') as client:
        result = client.health_check()
        if result:
            print(' NATS health check passed')
            sys.exit(0)
        else:
            print(' NATS not healthy')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"

    # Test 2: Publish message
    run_python_test "NATS - Publish Message" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.nats_client import NATSClient

try:
    with NATSClient(host='${HOST}', port=50056, user_id='${USER_ID}') as client:
        result = client.publish('test.subject', b'Hello from test script')
        if result:
            print(' Published message successfully')
            sys.exit(0)
        else:
            print(' Publish failed')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"
}

# ============================================
# Test Supabase Client
# ============================================
test_supabase_client() {
    print_header "Testing Supabase Client (port 50057)"

    if ! check_service_available 50057 "Supabase gRPC Service"; then
        skip_test "Supabase Client - Service unavailable"
        return
    fi

    # Test 1: Health check
    run_python_test "Supabase - Health Check" "
import sys
sys.path.insert(0, '${PROJECT_ROOT}/isA_common')
from isa_common.supabase_client import SupabaseClient

try:
    with SupabaseClient(host='${HOST}', port=50057, user_id='${USER_ID}') as client:
        result = client.health_check()
        if result:
            print(' Supabase health check passed')
            sys.exit(0)
        else:
            print(' Supabase not healthy')
            sys.exit(1)
except Exception as e:
    print(f' Error: {e}')
    sys.exit(1)
"
}

# ============================================
# Print Test Summary
# ============================================
print_summary() {
    echo ""
    print_header "Test Summary"
    echo ""
    echo -e "Total Tests:   ${TOTAL_TESTS}"
    echo -e "${GREEN}Passed:        ${PASSED_TESTS}${NC}"
    echo -e "${RED}Failed:        ${FAILED_TESTS}${NC}"
    echo -e "${YELLOW}Skipped:       ${SKIPPED_TESTS}${NC}"
    echo ""

    local success_rate=0
    if [ ${TOTAL_TESTS} -gt 0 ]; then
        success_rate=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    fi

    echo -e "Success Rate:  ${success_rate}%"
    echo ""

    if [ ${FAILED_TESTS} -eq 0 ]; then
        print_success "All tests passed!"
        return 0
    else
        print_error "${FAILED_TESTS} test(s) failed"
        return 1
    fi
}

# ============================================
# Main Execution
# ============================================
main() {
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --host)
                HOST="$2"
                shift 2
                ;;
            --user-id)
                USER_ID="$2"
                shift 2
                ;;
            --org-id)
                ORG_ID="$2"
                shift 2
                ;;
            --verbose|-v)
                VERBOSE="true"
                shift
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --host HOST       gRPC service host (default: localhost)"
                echo "  --user-id USER    Test user ID (default: test_user)"
                echo "  --org-id ORG      Test organization ID (default: test_org)"
                echo "  --verbose, -v     Show detailed output from tests"
                echo "  --help            Show this help message"
                echo ""
                echo "Environment Variables:"
                echo "  GRPC_HOST         Same as --host"
                echo "  GRPC_USER_ID      Same as --user-id"
                echo "  GRPC_ORG_ID       Same as --org-id"
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done

    print_header "isA Platform - gRPC Client Test Suite"
    echo ""
    print_info "Configuration:"
    echo "  Host:            ${HOST}"
    echo "  User ID:         ${USER_ID}"
    echo "  Organization ID: ${ORG_ID}"
    echo ""

    # Check prerequisites
    if ! command -v python3 &> /dev/null; then
        print_error "python3 is required but not installed"
        exit 1
    fi

    if ! command -v nc &> /dev/null; then
        print_warning "netcat (nc) not found - service availability checks will be skipped"
    fi

    # Run all tests
    test_minio_client
    test_duckdb_client
    test_mqtt_client
    test_loki_client
    test_redis_client
    test_nats_client
    test_supabase_client

    # Print summary
    print_summary
}

# Run main function
main "$@"
