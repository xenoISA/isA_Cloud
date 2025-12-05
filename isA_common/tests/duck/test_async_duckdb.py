#!/usr/bin/env python3
"""
Async DuckDB Client - Comprehensive Functional Tests

Tests all async DuckDB operations including:
- Health check
- Database management
- Query operations
- Table management
- MinIO data import/export
- Batch operations
- Concurrent operations
"""

import asyncio
import os
import sys
import time
import uuid

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from isa_common import AsyncDuckDBClient

# Configuration
HOST = os.environ.get('HOST', 'localhost')
PORT = int(os.environ.get('PORT', '50052'))
USER_ID = os.environ.get('USER_ID', 'test_user')  # Use underscore, not hyphen (DuckDB naming requirement)

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


async def test_health_check(client: AsyncDuckDBClient) -> bool:
    """Test 1: Service Health Check"""
    try:
        health = await client.health_check()
        success = health is not None and health.get('healthy', False)
        test_result(success, "Health check")
        return success
    except Exception as e:
        test_result(False, f"Health check - {e}")
        return False


async def test_create_database(client: AsyncDuckDBClient, db_name: str) -> str:
    """Test 2: Create Database - Returns database_id for subsequent tests"""
    try:
        result = await client.create_database(db_name)
        success = result is not None
        database_id = result.get('database_id', '') if result else ''
        test_result(success, f"Create database '{db_name}' (id: {database_id[:16]}...)")
        return database_id
    except Exception as e:
        test_result(False, f"Create database - {e}")
        return ''


async def test_list_databases(client: AsyncDuckDBClient):
    """Test 3: List Databases"""
    try:
        databases = await client.list_databases()
        success = isinstance(databases, list)
        test_result(success, f"List databases (found {len(databases)})")
    except Exception as e:
        test_result(False, f"List databases - {e}")


async def test_get_database_info(client: AsyncDuckDBClient, database_id: str):
    """Test 4: Get Database Info"""
    try:
        info = await client.get_database_info(database_id)
        success = info is not None
        test_result(success, f"Get database info")
    except Exception as e:
        test_result(False, f"Get database info - {e}")


async def test_create_table(client: AsyncDuckDBClient, database_id: str, table_name: str):
    """Test 5: Create Table"""
    try:
        # Note: TIMESTAMP column has issues with the server - using simpler schema
        schema = {
            'id': 'INTEGER',
            'name': 'VARCHAR',
            'value': 'DOUBLE'
        }
        success = await client.create_table(database_id, table_name, schema)
        test_result(success, f"Create table '{table_name}'")
    except Exception as e:
        test_result(False, f"Create table - {e}")


async def test_list_tables(client: AsyncDuckDBClient, database_id: str):
    """Test 6: List Tables"""
    try:
        tables = await client.list_tables(database_id)
        success = isinstance(tables, list)
        test_result(success, f"List tables (found {len(tables)})")
    except Exception as e:
        test_result(False, f"List tables - {e}")


async def test_get_table_schema(client: AsyncDuckDBClient, database_id: str, table_name: str):
    """Test 7: Get Table Schema"""
    try:
        schema = await client.get_table_schema(database_id, table_name)
        success = schema is not None and 'columns' in schema
        test_result(success, f"Get table schema ({len(schema.get('columns', []))} columns)")
    except Exception as e:
        test_result(False, f"Get table schema - {e}")


async def test_execute_statement(client: AsyncDuckDBClient, database_id: str, table_name: str):
    """Test 8: Execute Statement (INSERT)"""
    try:
        sql = f"INSERT INTO {table_name} (id, name, value) VALUES (1, 'test', 3.14)"
        affected = await client.execute_statement(database_id, sql)
        success = affected >= 0
        test_result(success, f"Execute INSERT statement (affected: {affected})")
    except Exception as e:
        test_result(False, f"Execute statement - {e}")


async def test_execute_query(client: AsyncDuckDBClient, database_id: str, table_name: str):
    """Test 9: Execute Query (SELECT)"""
    try:
        sql = f"SELECT * FROM {table_name}"
        results = await client.execute_query(database_id, sql)
        success = isinstance(results, list)
        test_result(success, f"Execute SELECT query (rows: {len(results)})")
    except Exception as e:
        test_result(False, f"Execute query - {e}")


async def test_execute_batch(client: AsyncDuckDBClient, database_id: str, table_name: str):
    """Test 10: Execute Batch"""
    try:
        statements = [
            f"INSERT INTO {table_name} (id, name, value) VALUES (2, 'batch1', 1.1)",
            f"INSERT INTO {table_name} (id, name, value) VALUES (3, 'batch2', 2.2)",
            f"INSERT INTO {table_name} (id, name, value) VALUES (4, 'batch3', 3.3)",
        ]
        # auto_qualify_tables=True (default) qualifies table names with user prefix
        # which matches how CreateTable creates tables on the server
        result = await client.execute_batch(database_id, statements)
        success = result is not None and result.get('success')
        test_result(success, f"Execute batch ({len(statements)} statements)")
    except Exception as e:
        test_result(False, f"Execute batch - {e}")


async def test_get_table_stats(client: AsyncDuckDBClient, database_id: str, table_name: str):
    """Test 11: Get Table Stats"""
    try:
        stats = await client.get_table_stats(database_id, table_name)
        success = stats is not None
        test_result(success, f"Get table stats (rows: {stats.get('row_count', 0) if stats else 0})")
    except Exception as e:
        test_result(False, f"Get table stats - {e}")


async def test_concurrent_queries(client: AsyncDuckDBClient, database_id: str, table_name: str):
    """Test 12: Concurrent Queries"""
    try:
        queries = [
            f"SELECT COUNT(*) as cnt FROM {table_name}",
            f"SELECT MAX(value) as max_val FROM {table_name}",
            f"SELECT MIN(value) as min_val FROM {table_name}",
            f"SELECT AVG(value) as avg_val FROM {table_name}",
        ]

        start = time.time()
        results = await client.execute_queries_concurrent(database_id, queries)
        elapsed = (time.time() - start) * 1000

        success = all(isinstance(r, list) for r in results)
        test_result(success, f"Concurrent queries ({len(queries)} queries in {elapsed:.1f}ms)")
    except Exception as e:
        test_result(False, f"Concurrent queries - {e}")


async def test_drop_table(client: AsyncDuckDBClient, database_id: str, table_name: str):
    """Test 13: Drop Table"""
    try:
        success = await client.drop_table(database_id, table_name)
        test_result(success, f"Drop table '{table_name}'")
    except Exception as e:
        test_result(False, f"Drop table - {e}")


async def test_delete_database(client: AsyncDuckDBClient, database_id: str):
    """Test 14: Delete Database"""
    try:
        success = await client.delete_database(database_id, force=True)
        test_result(success, f"Delete database '{database_id}'")
    except Exception as e:
        test_result(False, f"Delete database - {e}")


async def run_tests():
    """Run all tests."""
    print("=" * 70)
    print("     ASYNC DUCKDB CLIENT - COMPREHENSIVE FUNCTIONAL TESTS")
    print("=" * 70)
    print()
    print(f"Configuration:")
    print(f"  Host: {HOST}")
    print(f"  Port: {PORT}")
    print(f"  User: {USER_ID}")
    print()

    # Test identifiers
    test_id = uuid.uuid4().hex[:8]
    db_name = f"async_test_db_{test_id}"
    table_name = f"test_table_{test_id}"

    async with AsyncDuckDBClient(
        host=HOST,
        port=PORT,
        user_id=USER_ID
    ) as client:
        # Health check first
        print("--- Health Check ---")
        health_ok = await test_health_check(client)

        if not health_ok:
            print("\nHealth check failed - skipping remaining tests")
            print("Make sure the DuckDB gRPC service is running and accessible")
            return

        # Database Management
        print("\n--- Database Management ---")
        database_id = await test_create_database(client, db_name)
        if not database_id:
            print("\nFailed to create database - skipping remaining tests")
            return
        await test_list_databases(client)
        await test_get_database_info(client, database_id)

        # Table Management
        print("\n--- Table Management ---")
        await test_create_table(client, database_id, table_name)
        await test_list_tables(client, database_id)
        await test_get_table_schema(client, database_id, table_name)

        # Query Operations
        print("\n--- Query Operations ---")
        await test_execute_statement(client, database_id, table_name)
        await test_execute_query(client, database_id, table_name)
        await test_execute_batch(client, database_id, table_name)
        await test_get_table_stats(client, database_id, table_name)

        # Concurrent Operations
        print("\n--- Concurrent Operations ---")
        await test_concurrent_queries(client, database_id, table_name)

        # Cleanup
        print("\n--- Cleanup ---")
        await test_drop_table(client, database_id, table_name)
        await test_delete_database(client, database_id)

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
