#!/usr/bin/env python3
"""
PostgreSQL Client Usage Examples
=================================

This example demonstrates how to use the PostgresClient from isa_common package.

File: isA_common/examples/postgres_client_examples.py

Prerequisites:
--------------
1. PostgreSQL gRPC service must be running (default: localhost:50061)
2. Install isa_common package:
   ```bash
   pip install -e /path/to/isA_Cloud/isA_common
   ```

Usage:
------
```bash
# Run all examples
python isA_common/examples/postgres_client_examples.py

# Run with custom host/port
python isA_common/examples/postgres_client_examples.py --host 192.168.1.100 --port 50061
```

Features Demonstrated:
----------------------
✓ Health Check
✓ Table Management (create, list, exists)
✓ Query Operations (SELECT, INSERT, UPDATE, DELETE)
✓ Query Builder (select_from, insert_into)
✓ Parameterized Queries
✓ Batch Operations
✓ Single Row Queries
✓ Database Statistics
✓ Connection Pooling

Note: All operations include proper error handling and use context managers for resource cleanup.
"""

import sys
import argparse
from datetime import datetime

# Import the PostgresClient from isa_common
try:
    from isa_common.postgres_client import PostgresClient
except ImportError:
    print("=" * 80)
    print("ERROR: Failed to import isa_common.postgres_client")
    print("=" * 80)
    print("\nPlease install isa_common package:")
    print("  cd /path/to/isA_Cloud")
    print("  pip install -e isA_common")
    print()
    sys.exit(1)


def example_01_health_check(host='localhost', port=50061):
    """
    Example 1: Health Check

    Check if the PostgreSQL gRPC service is healthy and operational.
    """
    print("\n" + "=" * 80)
    print("Example 1: Service Health Check")
    print("=" * 80)

    with PostgresClient(host=host, port=port, user_id='example-user') as client:
        health = client.health_check(detailed=True)

        if health and health.get('healthy'):
            print(f"✅ Service is healthy!")
            print(f"   Status: {health.get('status')}")
            print(f"   Version: {health.get('version')}")
            if health.get('details'):
                print(f"   Details: {health.get('details')}")
        else:
            print("❌ Service is not healthy")


def example_02_table_management(host='localhost', port=50061):
    """
    Example 2: Table Management

    Create a table, check if it exists, list tables, and drop it.
    """
    print("\n" + "=" * 80)
    print("Example 2: Table Management")
    print("=" * 80)

    with PostgresClient(host=host, port=port, user_id='example-user') as client:
        table_name = 'example_users'
        schema = 'public'

        # Drop table if exists
        client.execute(f"DROP TABLE IF EXISTS {table_name}", schema=schema)

        # Create table
        create_sql = f"""
        CREATE TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            full_name VARCHAR(100),
            age INTEGER,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        client.execute(create_sql, schema=schema)

        # Check if table exists
        exists = client.table_exists(table_name, schema=schema)
        print(f"\nTable '{table_name}' exists: {exists}")

        # List all tables
        tables = client.list_tables(schema=schema)
        print(f"\nTables in '{schema}' schema: {len(tables)} tables")
        print(f"  {', '.join(tables[:5])}{'...' if len(tables) > 5 else ''}")


def example_03_insert_operations(host='localhost', port=50061):
    """
    Example 3: Insert Operations

    Insert data using both raw SQL and the insert_into helper.
    """
    print("\n" + "=" * 80)
    print("Example 3: Insert Operations")
    print("=" * 80)

    with PostgresClient(host=host, port=port, user_id='example-user') as client:
        table_name = 'example_users'
        schema = 'public'

        # Insert using parameterized SQL
        sql = f"INSERT INTO {table_name} (username, email, full_name, age) VALUES ($1, $2, $3, $4)"
        result = client.execute(sql, ['john_doe', 'john@example.com', 'John Doe', 30], schema=schema)
        print(f"\n✅ Inserted {result} row using SQL")

        # Batch insert using insert_into
        users = [
            {'username': 'jane_smith', 'email': 'jane@example.com', 'full_name': 'Jane Smith', 'age': 28},
            {'username': 'bob_wilson', 'email': 'bob@example.com', 'full_name': 'Bob Wilson', 'age': 35},
            {'username': 'alice_jones', 'email': 'alice@example.com', 'full_name': 'Alice Jones', 'age': 32}
        ]
        count = client.insert_into(table_name, users, schema=schema)
        print(f"✅ Batch inserted {count} rows using insert_into")


def example_04_query_operations(host='localhost', port=50061):
    """
    Example 4: Query Operations

    Query data using raw SQL with parameters.
    """
    print("\n" + "=" * 80)
    print("Example 4: Query Operations")
    print("=" * 80)

    with PostgresClient(host=host, port=port, user_id='example-user') as client:
        table_name = 'example_users'
        schema = 'public'

        # Query all users
        rows = client.query(f"SELECT * FROM {table_name} ORDER BY username", schema=schema)
        print(f"\n✅ Total users: {len(rows)}")

        # Query with parameters
        rows = client.query(
            f"SELECT username, email, age FROM {table_name} WHERE age > $1 ORDER BY age DESC",
            [25],
            schema=schema
        )
        print(f"\n✅ Users over 25 years old:")
        for row in rows:
            print(f"   • {row.get('username')}: {row.get('age')} years old - {row.get('email')}")

        # Query single row
        row = client.query_row(
            f"SELECT * FROM {table_name} WHERE username = $1",
            ['john_doe'],
            schema=schema
        )
        if row:
            print(f"\n✅ Found user: {row.get('full_name')} ({row.get('email')})")


def example_05_query_builder(host='localhost', port=50061):
    """
    Example 5: Query Builder

    Use the query builder methods for cleaner code.
    """
    print("\n" + "=" * 80)
    print("Example 5: Query Builder Operations")
    print("=" * 80)

    with PostgresClient(host=host, port=port, user_id='example-user') as client:
        table_name = 'example_users'
        schema = 'public'

        # SELECT with WHERE, ORDER BY, LIMIT
        rows = client.select_from(
            table_name,
            columns=['username', 'email', 'age'],
            where=[
                {'column': 'age', 'operator': '>=', 'value': 30},
                {'column': 'is_active', 'operator': '=', 'value': True}
            ],
            order_by=['age DESC'],
            limit=5,
            schema=schema
        )

        print(f"\n✅ Active users 30+ years old:")
        for row in rows:
            print(f"   • {row.get('username')}: {row.get('age')} years")


def example_06_update_operations(host='localhost', port=50061):
    """
    Example 6: Update Operations

    Update records using parameterized SQL.
    """
    print("\n" + "=" * 80)
    print("Example 6: Update Operations")
    print("=" * 80)

    with PostgresClient(host=host, port=port, user_id='example-user') as client:
        table_name = 'example_users'
        schema = 'public'

        # Update single row
        sql = f"UPDATE {table_name} SET age = $1, full_name = $2 WHERE username = $3"
        result = client.execute(sql, [31, 'John M. Doe', 'john_doe'], schema=schema)
        print(f"\n✅ Updated {result} row")

        # Verify update
        row = client.query_row(
            f"SELECT full_name, age FROM {table_name} WHERE username = $1",
            ['john_doe'],
            schema=schema
        )
        print(f"   New values: {row.get('full_name')}, age {row.get('age')}")


def example_07_batch_operations(host='localhost', port=50061):
    """
    Example 7: Batch Operations

    Execute multiple operations in a batch.
    """
    print("\n" + "=" * 80)
    print("Example 7: Batch Operations")
    print("=" * 80)

    with PostgresClient(host=host, port=port, user_id='example-user') as client:
        table_name = 'example_users'
        schema = 'public'

        operations = [
            {'sql': f"UPDATE {table_name} SET age = $1 WHERE username = $2", 'params': [29, 'jane_smith']},
            {'sql': f"UPDATE {table_name} SET age = $1 WHERE username = $2", 'params': [36, 'bob_wilson']},
            {'sql': f"UPDATE {table_name} SET is_active = $1 WHERE username = $2", 'params': [False, 'alice_jones']}
        ]

        result = client.execute_batch(operations, schema=schema)

        if result:
            print(f"\n✅ Batch completed: {result.get('total_rows_affected')} total rows affected")
            for i, op_result in enumerate(result.get('results', [])):
                print(f"   Operation {i+1}: {op_result.get('rows_affected')} rows")


def example_08_delete_operations(host='localhost', port=50061):
    """
    Example 8: Delete Operations

    Delete records using SQL.
    """
    print("\n" + "=" * 80)
    print("Example 8: Delete Operations")
    print("=" * 80)

    with PostgresClient(host=host, port=port, user_id='example-user') as client:
        table_name = 'example_users'
        schema = 'public'

        # Delete inactive users
        sql = f"DELETE FROM {table_name} WHERE is_active = $1"
        result = client.execute(sql, [False], schema=schema)
        print(f"\n✅ Deleted {result} inactive user(s)")

        # Count remaining users
        rows = client.query(f"SELECT COUNT(*) as count FROM {table_name}", schema=schema)
        print(f"   Remaining users: {rows[0].get('count')}")


def example_09_statistics(host='localhost', port=50061):
    """
    Example 9: Database Statistics

    Get connection pool and database statistics.
    """
    print("\n" + "=" * 80)
    print("Example 9: Database Statistics")
    print("=" * 80)

    with PostgresClient(host=host, port=port, user_id='example-user') as client:
        stats = client.get_stats()

        if stats:
            pool = stats.get('pool', {})
            db = stats.get('database', {})

            print(f"\n✅ Connection Pool:")
            print(f"   • Max connections: {pool.get('max_connections')}")
            print(f"   • Active connections: {pool.get('active_connections')}")
            print(f"   • Idle connections: {pool.get('idle_connections')}")
            print(f"   • Total queries: {pool.get('total_queries')}")

            print(f"\n✅ Database:")
            print(f"   • Version: {db.get('version')}")


def example_10_cleanup(host='localhost', port=50061):
    """
    Example 10: Cleanup

    Drop the example table.
    """
    print("\n" + "=" * 80)
    print("Example 10: Cleanup")
    print("=" * 80)

    with PostgresClient(host=host, port=port, user_id='example-user') as client:
        table_name = 'example_users'
        schema = 'public'

        client.execute(f"DROP TABLE IF EXISTS {table_name}", schema=schema)
        print(f"\n✅ Dropped table '{table_name}'")


def main():
    """Run all examples"""
    parser = argparse.ArgumentParser(description='PostgreSQL Client Usage Examples')
    parser.add_argument('--host', default='localhost', help='PostgreSQL gRPC service host')
    parser.add_argument('--port', type=int, default=50061, help='PostgreSQL gRPC service port')
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("PostgreSQL Client Examples")
    print("=" * 80)
    print(f"Connecting to: {args.host}:{args.port}")

    try:
        example_01_health_check(args.host, args.port)
        example_02_table_management(args.host, args.port)
        example_03_insert_operations(args.host, args.port)
        example_04_query_operations(args.host, args.port)
        example_05_query_builder(args.host, args.port)
        example_06_update_operations(args.host, args.port)
        example_07_batch_operations(args.host, args.port)
        example_08_delete_operations(args.host, args.port)
        example_09_statistics(args.host, args.port)
        example_10_cleanup(args.host, args.port)

        print("\n" + "=" * 80)
        print("✅ All examples completed successfully!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
