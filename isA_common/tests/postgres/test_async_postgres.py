#!/usr/bin/env python3
"""
Async PostgreSQL Client - Comprehensive Functional Tests

Tests all async PostgreSQL operations including:
- Health check
- Query operations (SELECT)
- Execute operations (INSERT/UPDATE/DELETE)
- Batch operations
- Query builder style operations
- Table operations
- Concurrent query execution
- Statistics

Usage:
    python test_async_postgres.py
    HOST=postgres-service PORT=50061 python test_async_postgres.py
"""

import os
import sys
import asyncio
import time

# Add parent path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from isa_common import AsyncPostgresClient

# Configuration
HOST = os.environ.get('HOST', 'localhost')
PORT = int(os.environ.get('PORT', '50061'))
USER_ID = os.environ.get('USER_ID', 'test_user')

# Test results
PASSED = 0
FAILED = 0
TOTAL = 0


def test_result(success: bool, test_name: str):
    """Record test result."""
    global PASSED, FAILED, TOTAL
    TOTAL += 1
    if success:
        PASSED += 1
        print(f"  ✓ PASSED: {test_name}")
    else:
        FAILED += 1
        print(f"  ✗ FAILED: {test_name}")


async def test_health_check(client: AsyncPostgresClient) -> bool:
    """Test 1: Service Health Check"""
    try:
        health = await client.health_check()
        success = health is not None and health.get('healthy', False)
        test_result(success, "Health check")
        return success
    except Exception as e:
        test_result(False, f"Health check - {e}")
        return False


async def test_simple_query(client: AsyncPostgresClient):
    """Test 2: Simple Query"""
    try:
        result = await client.query("SELECT 1 as num, 'hello' as msg")
        if result is None or len(result) == 0:
            test_result(False, "Simple query - no results")
            return

        if result[0].get('num') != 1:
            test_result(False, f"Simple query - unexpected value: {result[0]}")
            return

        test_result(True, "Simple query")
    except Exception as e:
        test_result(False, f"Simple query - {e}")


async def test_query_with_params(client: AsyncPostgresClient):
    """Test 3: Query with Parameters"""
    try:
        result = await client.query(
            "SELECT $1::int as num, $2::text as msg",
            params=[42, 'world']
        )
        if result is None or len(result) == 0:
            test_result(False, "Query with params - no results")
            return

        if result[0].get('num') != 42 or result[0].get('msg') != 'world':
            test_result(False, f"Query with params - unexpected: {result[0]}")
            return

        test_result(True, "Query with parameters")
    except Exception as e:
        test_result(False, f"Query with params - {e}")


async def test_query_row(client: AsyncPostgresClient):
    """Test 4: Query Single Row"""
    try:
        result = await client.query_row("SELECT 1 as id, 'test' as name")
        if result is None:
            test_result(False, "Query row - no result")
            return

        if result.get('id') != 1:
            test_result(False, f"Query row - unexpected: {result}")
            return

        test_result(True, "Query single row")
    except Exception as e:
        test_result(False, f"Query row - {e}")


async def test_list_tables(client: AsyncPostgresClient):
    """Test 5: List Tables"""
    try:
        tables = await client.list_tables()
        # Tables list could be empty, that's ok
        if tables is None:
            test_result(False, "List tables - returned None")
            return

        test_result(True, f"List tables (found {len(tables)} tables)")
    except Exception as e:
        test_result(False, f"List tables - {e}")


async def test_table_exists(client: AsyncPostgresClient):
    """Test 6: Table Exists Check"""
    try:
        # Check a common system table
        exists = await client.table_exists('pg_catalog.pg_tables', schema='pg_catalog')
        # Note: This might fail depending on how the proto is configured
        # Fall back to checking public schema
        if not exists:
            exists = await client.table_exists('users', schema='public')

        # Just verify we can call it without error
        test_result(True, "Table exists check")
    except Exception as e:
        test_result(False, f"Table exists - {e}")


async def test_execute_ddl(client: AsyncPostgresClient):
    """Test 7: Execute DDL (Create/Drop Table)"""
    try:
        # Create test table
        await client.execute("""
            CREATE TABLE IF NOT EXISTS async_test_table (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                value INT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Verify table exists
        exists = await client.table_exists('async_test_table')
        if not exists:
            test_result(False, "Create table - table not found after create")
            return

        test_result(True, "Execute DDL (CREATE TABLE)")
    except Exception as e:
        test_result(False, f"Execute DDL - {e}")


async def test_execute_insert(client: AsyncPostgresClient):
    """Test 8: Execute INSERT"""
    try:
        # Insert data
        rows = await client.execute(
            "INSERT INTO async_test_table (name, value) VALUES ($1, $2)",
            params=['test_name', 100]
        )

        test_result(True, "Execute INSERT")
    except Exception as e:
        test_result(False, f"Execute INSERT - {e}")


async def test_execute_update(client: AsyncPostgresClient):
    """Test 9: Execute UPDATE"""
    try:
        rows = await client.execute(
            "UPDATE async_test_table SET value = $1 WHERE name = $2",
            params=[200, 'test_name']
        )

        test_result(True, "Execute UPDATE")
    except Exception as e:
        test_result(False, f"Execute UPDATE - {e}")


async def test_select_from_table(client: AsyncPostgresClient):
    """Test 10: Query Inserted Data"""
    try:
        result = await client.query(
            "SELECT * FROM async_test_table WHERE name = $1",
            params=['test_name']
        )

        if result is None or len(result) == 0:
            test_result(False, "Select from table - no results")
            return

        if result[0].get('value') != 200:  # Should be updated value
            test_result(False, f"Select from table - unexpected value: {result[0].get('value')}")
            return

        test_result(True, "Select from table")
    except Exception as e:
        test_result(False, f"Select from table - {e}")


async def test_execute_delete(client: AsyncPostgresClient):
    """Test 11: Execute DELETE"""
    try:
        rows = await client.execute(
            "DELETE FROM async_test_table WHERE name = $1",
            params=['test_name']
        )

        test_result(True, "Execute DELETE")
    except Exception as e:
        test_result(False, f"Execute DELETE - {e}")


async def test_execute_batch(client: AsyncPostgresClient):
    """Test 12: Execute Batch Operations"""
    try:
        operations = [
            {'sql': "INSERT INTO async_test_table (name, value) VALUES ($1, $2)", 'params': ['batch1', 10]},
            {'sql': "INSERT INTO async_test_table (name, value) VALUES ($1, $2)", 'params': ['batch2', 20]},
            {'sql': "INSERT INTO async_test_table (name, value) VALUES ($1, $2)", 'params': ['batch3', 30]},
        ]

        result = await client.execute_batch(operations)
        if result is None:
            test_result(False, "Execute batch - returned None")
            return

        test_result(True, "Execute batch operations")
    except Exception as e:
        test_result(False, f"Execute batch - {e}")


async def test_concurrent_queries(client: AsyncPostgresClient):
    """Test 13: Concurrent Query Execution"""
    try:
        start = time.time()

        # Execute multiple queries concurrently
        results = await asyncio.gather(
            client.query("SELECT 1 as num"),
            client.query("SELECT 2 as num"),
            client.query("SELECT 3 as num"),
            client.query("SELECT 4 as num"),
            client.query("SELECT 5 as num"),
        )

        elapsed = time.time() - start

        if len(results) != 5:
            test_result(False, f"Concurrent queries - got {len(results)} results")
            return

        # Verify all queries returned data
        for i, result in enumerate(results):
            if result is None or len(result) == 0:
                test_result(False, f"Concurrent queries - query {i+1} returned None")
                return

        test_result(True, f"Concurrent queries (5 queries in {elapsed*1000:.1f}ms)")
    except Exception as e:
        test_result(False, f"Concurrent queries - {e}")


async def test_query_many_concurrent(client: AsyncPostgresClient):
    """Test 14: query_many_concurrent Helper"""
    try:
        queries = [
            {'sql': "SELECT 1 as num"},
            {'sql': "SELECT 2 as num"},
            {'sql': "SELECT 3 as num"},
        ]

        start = time.time()
        results = await client.query_many_concurrent(queries)
        elapsed = time.time() - start

        if len(results) != 3:
            test_result(False, f"query_many_concurrent - got {len(results)} results")
            return

        test_result(True, f"query_many_concurrent helper ({elapsed*1000:.1f}ms)")
    except Exception as e:
        test_result(False, f"query_many_concurrent - {e}")


async def test_get_stats(client: AsyncPostgresClient):
    """Test 15: Get Statistics"""
    try:
        stats = await client.get_stats()
        if stats is None:
            test_result(False, "Get stats - returned None")
            return

        test_result(True, "Get statistics")
    except Exception as e:
        test_result(False, f"Get stats - {e}")


async def cleanup(client: AsyncPostgresClient):
    """Cleanup test table."""
    print("\nCleaning up test table...")
    try:
        await client.execute("DROP TABLE IF EXISTS async_test_table")
    except Exception:
        pass


async def main():
    """Run all async tests."""
    print("=" * 70)
    print("     ASYNC POSTGRESQL CLIENT - COMPREHENSIVE FUNCTIONAL TESTS")
    print("=" * 70)
    print(f"\nConfiguration:")
    print(f"  Host: {HOST}")
    print(f"  Port: {PORT}")
    print(f"  User: {USER_ID}")
    print()

    async with AsyncPostgresClient(
        host=HOST,
        port=PORT,
        user_id=USER_ID
    ) as client:
        # Initial cleanup
        await cleanup(client)

        # Health check (required)
        print("\n--- Health Check ---")
        healthy = await test_health_check(client)
        if not healthy:
            print("\n✗ Cannot proceed without healthy service")
            return 1

        # Query operations
        print("\n--- Query Operations ---")
        await test_simple_query(client)
        await test_query_with_params(client)
        await test_query_row(client)

        # Table operations
        print("\n--- Table Operations ---")
        await test_list_tables(client)
        await test_table_exists(client)

        # DDL/DML operations
        print("\n--- DDL/DML Operations ---")
        await test_execute_ddl(client)
        await test_execute_insert(client)
        await test_execute_update(client)
        await test_select_from_table(client)
        await test_execute_delete(client)

        # Batch operations
        print("\n--- Batch Operations ---")
        await test_execute_batch(client)

        # Concurrent operations
        print("\n--- Concurrent Operations ---")
        await test_concurrent_queries(client)
        await test_query_many_concurrent(client)

        # Statistics
        print("\n--- Statistics ---")
        await test_get_stats(client)

        # Cleanup
        await cleanup(client)

    # Summary
    print("\n" + "=" * 70)
    print("                         TEST SUMMARY")
    print("=" * 70)
    print(f"Total Tests: {TOTAL}")
    print(f"Passed: {PASSED}")
    print(f"Failed: {FAILED}")
    if TOTAL > 0:
        print(f"Success Rate: {PASSED/TOTAL*100:.1f}%")
    print()

    if FAILED == 0:
        print(f"✓ ALL TESTS PASSED! ({PASSED}/{TOTAL})")
        return 0
    else:
        print(f"✗ SOME TESTS FAILED ({PASSED}/{TOTAL})")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
