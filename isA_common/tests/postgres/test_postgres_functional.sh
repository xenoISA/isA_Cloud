#!/bin/bash

# ============================================
# PostgreSQL Service - Comprehensive Functional Tests
# ============================================
# Tests all PostgreSQL operations including:
# - Health check
# - Query operations (SELECT, INSERT, UPDATE, DELETE)
# - Batch operations
# - Query builder operations
# - Table management
# - Statistics

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
HOST="${HOST:-localhost}"
PORT="${PORT:-50061}"
USER_ID="${USER_ID:-test-user}"
TEST_SCHEMA="public"
TEST_TABLE="test_users"

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
from isa_common.postgres_client import PostgresClient
client = PostgresClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
try:
    with client:
        client.execute("DROP TABLE IF EXISTS ${TEST_TABLE}", schema='${TEST_SCHEMA}')
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
from isa_common.postgres_client import PostgresClient
try:
    client = PostgresClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
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

test_table_management() {
    echo -e "${YELLOW}Test 2: Table Creation and Management${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.postgres_client import PostgresClient
try:
    client = PostgresClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Drop table if exists
        client.execute("DROP TABLE IF EXISTS ${TEST_TABLE}", schema='${TEST_SCHEMA}')

        # Create table
        create_sql = """
        CREATE TABLE ${TEST_TABLE} (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE,
            age INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        client.execute(create_sql, schema='${TEST_SCHEMA}')

        # Check if table exists
        if not client.table_exists('${TEST_TABLE}', schema='${TEST_SCHEMA}'):
            print("FAIL: Table not created")
        else:
            tables = client.list_tables(schema='${TEST_SCHEMA}')
            if '${TEST_TABLE}' not in tables:
                print("FAIL: Table not in list")
            else:
                print("PASS: Table management successful")
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

test_insert_operations() {
    echo -e "${YELLOW}Test 3: Insert Operations${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.postgres_client import PostgresClient
try:
    client = PostgresClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Single row insert using execute
        sql = "INSERT INTO ${TEST_TABLE} (name, email, age) VALUES (\$1, \$2, \$3)"
        result = client.execute(sql, ['Alice', 'alice@example.com', 30], schema='${TEST_SCHEMA}')

        if result != 1:
            print("FAIL: Insert returned wrong count")
        else:
            # Batch insert using insert_into
            rows = [
                {'name': 'Bob', 'email': 'bob@example.com', 'age': 25},
                {'name': 'Charlie', 'email': 'charlie@example.com', 'age': 35},
                {'name': 'Diana', 'email': 'diana@example.com', 'age': 28}
            ]
            count = client.insert_into('${TEST_TABLE}', rows, schema='${TEST_SCHEMA}')

            if count != 3:
                print("FAIL: Batch insert failed")
            else:
                print("PASS: Insert operations successful")
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

test_query_operations() {
    echo -e "${YELLOW}Test 4: Query Operations${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.postgres_client import PostgresClient
try:
    client = PostgresClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Query all rows
        rows = client.query("SELECT * FROM ${TEST_TABLE}", schema='${TEST_SCHEMA}')
        if not rows or len(rows) != 4:
            print(f"FAIL: Expected 4 rows, got {len(rows) if rows else 0}")
        else:
            # Query with parameters
            row = client.query_row(
                "SELECT * FROM ${TEST_TABLE} WHERE email = \$1",
                ['alice@example.com'],
                schema='${TEST_SCHEMA}'
            )
            if not row or row.get('name') != 'Alice':
                print("FAIL: Query with parameters failed")
            else:
                print("PASS: Query operations successful")
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

test_query_builder() {
    echo -e "${YELLOW}Test 5: Query Builder Operations${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.postgres_client import PostgresClient
try:
    client = PostgresClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # SELECT with WHERE clause
        rows = client.select_from(
            '${TEST_TABLE}',
            columns=['name', 'email', 'age'],
            where=[{'column': 'age', 'operator': '>', 'value': 25}],
            order_by=['age DESC'],
            limit=10,
            schema='${TEST_SCHEMA}'
        )

        if not rows or len(rows) != 3:
            print(f"FAIL: Expected 3 rows with age > 25, got {len(rows) if rows else 0}")
        else:
            # Check ordering
            ages = [row.get('age') for row in rows]
            if ages != sorted(ages, reverse=True):
                print("FAIL: Results not properly ordered")
            else:
                print("PASS: Query builder successful")
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

test_update_operations() {
    echo -e "${YELLOW}Test 6: Update Operations${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.postgres_client import PostgresClient
try:
    client = PostgresClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Update single row
        sql = "UPDATE ${TEST_TABLE} SET age = \$1 WHERE name = \$2"
        result = client.execute(sql, [31, 'Alice'], schema='${TEST_SCHEMA}')

        if result != 1:
            print("FAIL: Update returned wrong count")
        else:
            # Verify update
            row = client.query_row(
                "SELECT age FROM ${TEST_TABLE} WHERE name = \$1",
                ['Alice'],
                schema='${TEST_SCHEMA}'
            )
            if not row or row.get('age') != 31:
                print("FAIL: Update verification failed")
            else:
                print("PASS: Update operations successful")
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

test_batch_operations() {
    echo -e "${YELLOW}Test 7: Batch Operations${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.postgres_client import PostgresClient
try:
    client = PostgresClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        operations = [
            {'sql': "UPDATE ${TEST_TABLE} SET age = \$1 WHERE name = \$2", 'params': [26, 'Bob']},
            {'sql': "UPDATE ${TEST_TABLE} SET age = \$1 WHERE name = \$2", 'params': [36, 'Charlie']},
            {'sql': "UPDATE ${TEST_TABLE} SET age = \$1 WHERE name = \$2", 'params': [29, 'Diana']}
        ]

        result = client.execute_batch(operations, schema='${TEST_SCHEMA}')

        if not result or result.get('total_rows_affected') != 3:
            print("FAIL: Batch update failed")
        else:
            print("PASS: Batch operations successful")
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

test_delete_operations() {
    echo -e "${YELLOW}Test 8: Delete Operations${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.postgres_client import PostgresClient
try:
    client = PostgresClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Delete single row
        sql = "DELETE FROM ${TEST_TABLE} WHERE name = \$1"
        result = client.execute(sql, ['Diana'], schema='${TEST_SCHEMA}')

        if result != 1:
            print("FAIL: Delete returned wrong count")
        else:
            # Verify deletion
            rows = client.query("SELECT * FROM ${TEST_TABLE}", schema='${TEST_SCHEMA}')
            if len(rows) != 3:
                print(f"FAIL: Expected 3 rows after delete, got {len(rows)}")
            else:
                print("PASS: Delete operations successful")
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

test_statistics() {
    echo -e "${YELLOW}Test 9: Database Statistics${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.postgres_client import PostgresClient
try:
    client = PostgresClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        stats = client.get_stats()

        if not stats:
            print("FAIL: Could not retrieve stats")
        elif 'pool' not in stats or 'database' not in stats:
            print("FAIL: Stats missing required fields")
        elif stats['pool']['max_connections'] <= 0:
            print("FAIL: Invalid pool stats")
        else:
            print("PASS: Statistics retrieval successful")
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
echo -e "${CYAN}       POSTGRESQL SERVICE COMPREHENSIVE FUNCTIONAL TESTS${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo ""
echo "Configuration:"
echo "  Host: ${HOST}"
echo "  Port: ${PORT}"
echo "  User: ${USER_ID}"
echo "  Schema: ${TEST_SCHEMA}"
echo "  Table: ${TEST_TABLE}"
echo ""

# Initial cleanup
echo -e "${CYAN}Performing initial cleanup...${NC}"
cleanup

# Health check
test_service_health
echo ""

# Table Management
echo -e "${CYAN}--- Table Management Tests ---${NC}"
test_table_management
echo ""

# Data Operations
echo -e "${CYAN}--- Data Operations Tests ---${NC}"
test_insert_operations
echo ""
test_query_operations
echo ""
test_query_builder
echo ""
test_update_operations
echo ""
test_batch_operations
echo ""
test_delete_operations
echo ""

# Advanced Features
echo -e "${CYAN}--- Advanced Features Tests ---${NC}"
test_statistics
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
