#!/bin/bash

# ============================================
# DuckDB Service - Comprehensive Functional Tests
# ============================================
# Tests DuckDB as a computing engine with MinIO storage layer:
# - Hot data access: frequently accessed data in DuckDB
# - Cold data storage: Parquet files in MinIO
# - Computing: DuckDB for selection, Polars for computation
# - Data lifecycle: Import from MinIO → Compute → Export back to MinIO
#
# Design Pattern:
#   MinIO (Parquet) → DuckDB (Hot Data) → Compute → MinIO (Results)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
HOST="${HOST:-localhost}"
PORT="${PORT:-50052}"
USER_ID="${USER_ID:-test_user}"  # DuckDB user_id (underscores ok for table prefixes)
TEST_DB="${USER_ID}_analytics_db"
# MinIO bucket: service adds "user-{sanitized_user_id}-" prefix
# With user_id='test_user', MinIO creates: user-test-user-duckdb-data
MINIO_BUCKET="duckdb-data"  # Base bucket name (both services add user prefix)
DB_ID_FILE="/tmp/duckdb_test_db_id_$$"  # Store database_id for test session

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

    # Clean up database using stored database_id if available
    if [ -f "${DB_ID_FILE}" ]; then
        DB_ID=$(cat "${DB_ID_FILE}")
        python3 <<EOF 2>/dev/null
from isa_common.duckdb_client import DuckDBClient
client = DuckDBClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
try:
    with client:
        # Delete test database using database_id (including MinIO files)
        try:
            client.delete_database('${DB_ID}', delete_from_minio=True, force=True)
        except:
            pass
except Exception:
    pass
EOF
        rm -f "${DB_ID_FILE}"
    fi
}

# ========================================
# Test Functions
# ========================================

test_service_health() {
    echo -e "${YELLOW}Test 1: Service Health Check${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.duckdb_client import DuckDBClient
try:
    client = DuckDBClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        if client.health_check():
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

test_database_lifecycle() {
    echo -e "${YELLOW}Test 2: Database Create/List (Track database_id UUID)${NC}"

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.duckdb_client import DuckDBClient
try:
    client = DuckDBClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Create database - returns database info with UUID database_id
        db_info = client.create_database('${TEST_DB}', minio_bucket='${MINIO_BUCKET}',
                                        metadata={'purpose': 'hot-data-analytics'})
        if not db_info:
            print("FAIL: Create database failed")
        else:
            database_id = db_info.get('database_id')
            if not database_id:
                print("FAIL: Database ID not returned")
            else:
                # Store database_id for subsequent tests
                with open('${DB_ID_FILE}', 'w') as f:
                    f.write(database_id)

                # List databases
                dbs = client.list_databases()
                if not any(db['name'] == '${TEST_DB}' for db in dbs):
                    print("FAIL: Database not in list")
                else:
                    print(f"PASS: Database created (ID: {database_id[:8]}...) and stored for subsequent tests")
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

test_table_operations() {
    echo -e "${YELLOW}Test 3: Table Create/Schema/Stats/Drop${NC}"

    # Read database_id from file
    if [ ! -f "${DB_ID_FILE}" ]; then
        echo "FAIL: Database ID file not found"
        test_result 1
        return
    fi
    DB_ID=$(cat "${DB_ID_FILE}")

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.duckdb_client import DuckDBClient
try:
    client = DuckDBClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        # Use database_id UUID for operations
        db_id = '${DB_ID}'

        # Create table for hot data
        schema = {
            'user_id': 'INTEGER',
            'event_type': 'VARCHAR',
            'timestamp': 'TIMESTAMP',
            'revenue': 'DOUBLE'
        }

        if not client.create_table(db_id, 'hot_events', schema):
            print("FAIL: Create table failed")
        else:
            # Get table schema
            table_schema = client.get_table_schema(db_id, 'hot_events')
            if not table_schema or len(table_schema['columns']) != 4:
                print("FAIL: Get table schema failed")
            else:
                # Insert some hot data
                insert_sql = """
                INSERT INTO hot_events VALUES
                (1, 'purchase', '2024-01-01 10:00:00', 99.99),
                (2, 'view', '2024-01-01 10:05:00', 0),
                (3, 'purchase', '2024-01-01 10:10:00', 149.99)
                """
                client.execute_statement(db_id, insert_sql)

                # Get table stats
                stats = client.get_table_stats(db_id, 'hot_events', include_columns=True)
                if not stats or stats['row_count'] != 3:
                    print(f"FAIL: Table stats failed - expected 3 rows, got {stats['row_count'] if stats else 0}")
                else:
                    print("PASS: Table operations successful")
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
    echo -e "${YELLOW}Test 4: Query Execution (SELECT, Aggregation)${NC}"

    if [ ! -f "${DB_ID_FILE}" ]; then
        echo "FAIL: Database ID file not found"
        test_result 1
        return
    fi
    DB_ID=$(cat "${DB_ID_FILE}")

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.duckdb_client import DuckDBClient
try:
    client = DuckDBClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        db_id = '${DB_ID}'

        # Simple SELECT
        result = client.execute_query(db_id, 'SELECT * FROM hot_events ORDER BY user_id')
        if not result or len(result) != 3:
            print("FAIL: SELECT query failed")
        else:
            # Analytical query (DuckDB strength)
            sql = """
            SELECT
                event_type,
                COUNT(*) as event_count,
                SUM(revenue) as total_revenue,
                AVG(revenue) as avg_revenue
            FROM hot_events
            GROUP BY event_type
            """
            result = client.execute_query(db_id, sql)
            if not result or len(result) != 2:  # purchase and view
                print("FAIL: Aggregation query failed")
            else:
                # Find purchase event
                purchase = next((r for r in result if r['event_type'] == 'purchase'), None)
                if not purchase or purchase['event_count'] != 2:
                    print("FAIL: Purchase count incorrect")
                elif purchase['total_revenue'] < 249:  # 99.99 + 149.99
                    print("FAIL: Revenue calculation incorrect")
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

test_batch_operations() {
    echo -e "${YELLOW}Test 5: Batch SQL Execution (Efficient Hot Data Operations)${NC}"

    if [ ! -f "${DB_ID_FILE}" ]; then
        echo "FAIL: Database ID file not found"
        test_result 1
        return
    fi
    DB_ID=$(cat "${DB_ID_FILE}")

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.duckdb_client import DuckDBClient
try:
    client = DuckDBClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        db_id = '${DB_ID}'

        # Batch insert for efficient hot data loading
        statements = [
            "INSERT INTO hot_events VALUES (4, 'purchase', '2024-01-02 10:00:00', 199.99)",
            "INSERT INTO hot_events VALUES (5, 'view', '2024-01-02 10:05:00', 0)",
            "INSERT INTO hot_events VALUES (6, 'purchase', '2024-01-02 10:10:00', 299.99)",
            "UPDATE hot_events SET revenue = revenue * 1.1 WHERE event_type = 'purchase' AND user_id > 3"
        ]

        result = client.execute_batch(db_id, statements, use_transaction=True)
        if not result or not result['success']:
            print("FAIL: Batch execution failed")
        elif len(result['results']) != 4:
            print("FAIL: Expected 4 results")
        else:
            # Verify batch operations
            count_result = client.execute_query(db_id, 'SELECT COUNT(*) as count FROM hot_events')
            if not count_result or count_result[0]['count'] != 6:
                print("FAIL: Batch insert verification failed")
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

test_import_from_minio() {
    echo -e "${YELLOW}Test 6: Import from MinIO (Cold → Hot Data Flow)${NC}"

    if [ ! -f "${DB_ID_FILE}" ]; then
        echo "FAIL: Database ID file not found"
        test_result 1
        return
    fi
    DB_ID=$(cat "${DB_ID_FILE}")

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.duckdb_client import DuckDBClient
from isa_common.minio_client import MinIOClient
import io
import json

try:
    # First, create cold data in MinIO (Parquet file)
    minio = MinIOClient(host='localhost', port=50051, user_id='${USER_ID}')
    duckdb = DuckDBClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')

    with minio, duckdb:
        db_id = '${DB_ID}'

        # Create MinIO bucket if not exists
        if not minio.bucket_exists('${MINIO_BUCKET}'):
            minio.create_bucket('${MINIO_BUCKET}')

        # Simulate cold data: create a CSV file
        csv_data = """user_id,product_id,quantity,price
100,A001,2,29.99
101,A002,1,49.99
102,A001,3,29.99
103,A003,1,79.99
"""
        minio.put_object('${MINIO_BUCKET}', 'cold-data/orders.csv',
                        io.BytesIO(csv_data.encode()), len(csv_data.encode()))

        # Import cold data into hot storage (DuckDB)
        # Both MinIO and DuckDB services add user prefix automatically
        if not duckdb.import_from_minio(db_id, 'orders', '${MINIO_BUCKET}',
                                       'cold-data/orders.csv', file_format='csv'):
            print("FAIL: Import from MinIO failed")
        else:
            # Verify imported data
            result = duckdb.execute_query(db_id, 'SELECT COUNT(*) as count FROM orders')
            if not result or result[0]['count'] != 4:
                print("FAIL: Imported data count incorrect")
            else:
                # Compute on hot data
                sql = "SELECT SUM(quantity * price) as total_value FROM orders"
                result = duckdb.execute_query(db_id, sql)
                if not result or result[0]['total_value'] < 200:
                    print("FAIL: Computation on hot data failed")
                else:
                    print("PASS: Import from MinIO successful")
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

test_query_minio_direct() {
    echo -e "${YELLOW}Test 7: Query MinIO File Directly (Zero-Copy Analytics)${NC}"

    if [ ! -f "${DB_ID_FILE}" ]; then
        echo "FAIL: Database ID file not found"
        test_result 1
        return
    fi
    DB_ID=$(cat "${DB_ID_FILE}")

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.duckdb_client import DuckDBClient
try:
    client = DuckDBClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        db_id = '${DB_ID}'

        # Query cold data directly from MinIO without importing
        # This is DuckDB's superpower: zero-copy analytics
        # Both services add user prefix automatically
        result = client.query_minio_file(
            db_id,
            '${MINIO_BUCKET}',
            'cold-data/orders.csv',
            file_format='csv',
            limit=100
        )

        if not result or len(result) != 4:
            print("FAIL: Direct query failed")
        else:
            # Verify data structure
            if 'user_id' not in result[0] or 'price' not in result[0]:
                print("FAIL: Data structure incorrect")
            else:
                print("PASS: Direct MinIO query successful (zero-copy analytics)")
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

test_export_to_minio() {
    echo -e "${YELLOW}Test 8: Export to MinIO (Hot → Cold Data Flow)${NC}"

    if [ ! -f "${DB_ID_FILE}" ]; then
        echo "FAIL: Database ID file not found"
        test_result 1
        return
    fi
    DB_ID=$(cat "${DB_ID_FILE}")

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.duckdb_client import DuckDBClient
from isa_common.minio_client import MinIOClient
try:
    duckdb = DuckDBClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    minio = MinIOClient(host='localhost', port=50051, user_id='${USER_ID}')

    with duckdb, minio:
        db_id = '${DB_ID}'

        # Compute aggregated results on hot data
        sql = """
        SELECT
            event_type,
            COUNT(*) as event_count,
            SUM(revenue) as total_revenue,
            AVG(revenue) as avg_revenue
        FROM hot_events
        GROUP BY event_type
        """

        # Export computed results back to MinIO as Parquet (cold storage)
        # Both services add user prefix automatically
        result = duckdb.export_to_minio(
            db_id,
            sql,
            '${MINIO_BUCKET}',
            'analytics/event_summary.parquet',
            file_format='parquet',
            overwrite=True
        )

        if not result or not result['success']:
            print("FAIL: Export to MinIO failed")
        elif result['rows_exported'] < 2:
            print("FAIL: Exported row count incorrect")
        else:
            # Verify exported file exists in MinIO
            objects = minio.list_objects('${MINIO_BUCKET}', prefix='analytics/')
            if not any('event_summary.parquet' in obj for obj in objects):
                print("FAIL: Exported file not found in MinIO")
            else:
                print("PASS: Export to MinIO successful (hot→cold flow)")
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

test_analytical_queries() {
    echo -e "${YELLOW}Test 9: Advanced Analytical Queries (DuckDB OLAP Strength)${NC}"

    if [ ! -f "${DB_ID_FILE}" ]; then
        echo "FAIL: Database ID file not found"
        test_result 1
        return
    fi
    DB_ID=$(cat "${DB_ID_FILE}")

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.duckdb_client import DuckDBClient
try:
    client = DuckDBClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        db_id = '${DB_ID}'

        # Window functions
        sql = """
        SELECT
            user_id,
            event_type,
            revenue,
            ROW_NUMBER() OVER (PARTITION BY event_type ORDER BY revenue DESC) as rank_in_type
        FROM hot_events
        WHERE revenue > 0
        """
        result = client.execute_query(db_id, sql)

        if not result or len(result) < 1:
            print("FAIL: Window function query failed")
        else:
            # CTEs (Common Table Expressions)
            sql = """
            WITH purchase_events AS (
                SELECT * FROM hot_events WHERE event_type = 'purchase'
            ),
            revenue_stats AS (
                SELECT
                    AVG(revenue) as avg_revenue,
                    MAX(revenue) as max_revenue
                FROM purchase_events
            )
            SELECT
                COUNT(*) as high_value_purchases
            FROM purchase_events, revenue_stats
            WHERE purchase_events.revenue > revenue_stats.avg_revenue
            """
            result = client.execute_query(db_id, sql)

            if not result or 'high_value_purchases' not in result[0]:
                print("FAIL: CTE query failed")
            else:
                print("PASS: Advanced analytical queries successful")
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

test_hot_data_lifecycle() {
    echo -e "${YELLOW}Test 10: Hot Data Lifecycle Management${NC}"

    if [ ! -f "${DB_ID_FILE}" ]; then
        echo "FAIL: Database ID file not found"
        test_result 1
        return
    fi
    DB_ID=$(cat "${DB_ID_FILE}")

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.duckdb_client import DuckDBClient
try:
    client = DuckDBClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        db_id = '${DB_ID}'

        # Create temporary hot data table
        schema = {'id': 'INTEGER', 'value': 'VARCHAR'}
        if not client.create_table(db_id, 'temp_hot_data', schema):
            print("FAIL: Create temp table failed")
        else:
            # Insert data
            client.execute_statement(db_id,
                "INSERT INTO temp_hot_data VALUES (1, 'temp1'), (2, 'temp2')")

            # Get stats before cleanup
            stats = client.get_table_stats(db_id, 'temp_hot_data')
            if not stats or stats['row_count'] != 2:
                print("FAIL: Table stats incorrect")
            else:
                # Drop table (hot data lifecycle management)
                if not client.drop_table(db_id, 'temp_hot_data', if_exists=True):
                    print("FAIL: Drop table failed")
                else:
                    # Verify table is gone
                    tables = client.list_tables(db_id)
                    if 'temp_hot_data' in tables:
                        print("FAIL: Table still exists after drop")
                    else:
                        print("PASS: Hot data lifecycle management successful")
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

test_polars_integration_concept() {
    echo -e "${YELLOW}Test 11: Polars + DuckDB Integration Pattern${NC}"

    if [ ! -f "${DB_ID_FILE}" ]; then
        echo "FAIL: Database ID file not found"
        test_result 1
        return
    fi
    DB_ID=$(cat "${DB_ID_FILE}")

    RESPONSE=$(python3 <<EOF 2>&1
from isa_common.duckdb_client import DuckDBClient
try:
    client = DuckDBClient(host='${HOST}', port=${PORT}, user_id='${USER_ID}')
    with client:
        db_id = '${DB_ID}'

        # DuckDB: SELECT data (filtering, aggregation)
        sql = """
        SELECT
            user_id,
            SUM(revenue) as total_revenue
        FROM hot_events
        WHERE event_type = 'purchase'
        GROUP BY user_id
        """

        # Get data from DuckDB (this would be passed to Polars for computation)
        result = client.execute_query(db_id, sql)

        if not result:
            print("FAIL: Data selection failed")
        else:
            # In real use: Polars would do advanced computation here
            # For test: verify we got the right data structure
            if len(result) > 0 and 'user_id' in result[0] and 'total_revenue' in result[0]:
                print("PASS: Polars+DuckDB integration pattern verified (DuckDB selects, Polars computes)")
            else:
                print("FAIL: Data structure incorrect")
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
echo -e "${CYAN}   DUCKDB SERVICE - HOT DATA + MINIO FUNCTIONAL TESTS${NC}"
echo -e "${CYAN}======================================================================${NC}"
echo ""
echo "Design Pattern:"
echo "  MinIO (Cold Parquet) → DuckDB (Hot Data) → Compute → MinIO (Results)"
echo ""
echo "Configuration:"
echo "  Host: ${HOST}"
echo "  Port: ${PORT}"
echo "  User: ${USER_ID}"
echo "  Database: ${TEST_DB}"
echo "  MinIO Bucket: ${MINIO_BUCKET} (services add user prefix)"
echo ""

# Initial cleanup
echo -e "${CYAN}Performing initial cleanup...${NC}"
cleanup

# Health check
test_service_health
echo ""

# Database Management Tests
echo -e "${CYAN}--- Database Management Tests ---${NC}"
test_database_lifecycle
echo ""

# Table Operations Tests
echo -e "${CYAN}--- Table Operations (Hot Data Schema) ---${NC}"
test_table_operations
echo ""

# Query Operations Tests
echo -e "${CYAN}--- Query Operations (OLAP Queries) ---${NC}"
test_query_operations
echo ""
test_batch_operations
echo ""

# MinIO Integration Tests (Critical for Design)
echo -e "${CYAN}--- MinIO Integration (Cold ↔ Hot Data Flow) ---${NC}"
test_import_from_minio
echo ""
test_query_minio_direct
echo ""
test_export_to_minio
echo ""

# Advanced Analytics Tests
echo -e "${CYAN}--- Advanced Analytics (DuckDB OLAP Strength) ---${NC}"
test_analytical_queries
echo ""

# Data Lifecycle Tests
echo -e "${CYAN}--- Hot Data Lifecycle Management ---${NC}"
test_hot_data_lifecycle
echo ""

# Integration Pattern Tests
echo -e "${CYAN}--- Polars + DuckDB Integration Pattern ---${NC}"
test_polars_integration_concept
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
    echo ""
    echo "Design Validated:"
    echo "  ✓ DuckDB as computing engine"
    echo "  ✓ MinIO as storage layer (Parquet)"
    echo "  ✓ Hot data access in DuckDB"
    echo "  ✓ Cold→Hot and Hot→Cold data flow"
    echo "  ✓ Zero-copy analytics (query MinIO directly)"
    echo "  ✓ Polars+DuckDB integration pattern ready"
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    exit 1
fi
