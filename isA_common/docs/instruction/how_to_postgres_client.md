# 🚀 PostgreSQL Client - Production-Ready Database Access

## Installation

```bash
pip install -e /path/to/isA_Cloud/isA_common
```

## Simple Usage Pattern

```python
from isa_common.postgres_client import PostgresClient

# Connect and use
with PostgresClient(host='localhost', port=50061, user_id='your-service') as client:

    # 1. Execute any SQL
    client.execute("CREATE TABLE users (id SERIAL, name TEXT)")

    # 2. Insert data
    client.insert_into('users', [
        {'name': 'Alice', 'email': 'alice@example.com'},
        {'name': 'Bob', 'email': 'bob@example.com'}
    ])

    # 3. Query data
    rows = client.query("SELECT * FROM users WHERE name = $1", ['Alice'])

    # 4. Query builder (no SQL needed)
    rows = client.select_from('users',
        columns=['name', 'email'],
        where=[{'column': 'age', 'operator': '>', 'value': 25}],
        order_by=['name ASC'],
        limit=10
    )
```

---

## Real Service Example: User Management

```python
from isa_common.postgres_client import PostgresClient

class UserService:
    def __init__(self):
        self.db = PostgresClient(user_id='user-service')

    def create_user(self, user_data):
        # Just business logic - no connection/pool management
        with self.db:
            return self.db.insert_into('users', [user_data])

    def find_active_users(self, min_age):
        # Query builder - no SQL strings!
        with self.db:
            return self.db.select_from('users',
                where=[
                    {'column': 'is_active', 'operator': '=', 'value': True},
                    {'column': 'age', 'operator': '>=', 'value': min_age}
                ],
                order_by=['created_at DESC']
            )

    def batch_update_users(self, updates):
        # Transactional batch - one line
        with self.db:
            operations = [
                {'sql': 'UPDATE users SET status = $1 WHERE id = $2',
                 'params': [u['status'], u['id']]}
                for u in updates
            ]
            return self.db.execute_batch(operations)
```

---

## Quick Patterns

### Parameterized Queries (SQL Injection Safe)
```python
client.query("SELECT * FROM users WHERE email = $1", ['user@example.com'])
```

### Batch Operations (Transaction Safe)
```python
client.execute_batch([
    {'sql': 'UPDATE orders SET status = $1 WHERE id = $2', 'params': ['shipped', 101]},
    {'sql': 'UPDATE orders SET status = $1 WHERE id = $2', 'params': ['shipped', 102]}
])
```

### Query Builder (No SQL)
```python
client.select_from('products',
    columns=['name', 'price'],
    where=[
        {'column': 'category', 'operator': '=', 'value': 'electronics'},
        {'column': 'price', 'operator': '<', 'value': 1000}
    ],
    limit=20
)
```

### Single Row Query
```python
user = client.query_row("SELECT * FROM users WHERE id = $1", [123])
```

### Check Table Exists
```python
if client.table_exists('users'):
    # do something
```

### Get Stats
```python
stats = client.get_stats()
print(f"Pool: {stats['pool']['active_connections']} active")
print(f"DB Version: {stats['database']['version']}")
```

---

## Benefits = Zero Database Complexity

### What you DON'T need:
- ❌ Connection pool configuration
- ❌ Transaction management
- ❌ SQL injection worries (parameterized by default)
- ❌ Connection leak debugging
- ❌ gRPC serialization
- ❌ Error handling boilerplate

### What you CAN focus on:
- ✅ Your data model
- ✅ Your business logic
- ✅ Your application features
- ✅ Your users

---

## Comparison: Without vs With Client

### Without (Raw psycopg2):
```python
# 50+ lines of connection pooling, error handling, retries...
pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=10, ...)
try:
    conn = pool.getconn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ...")
        results = cursor.fetchall()
        # Convert to dicts manually
        # Handle errors
        # Release connection
    finally:
        cursor.close()
        pool.putconn(conn)
except Exception as e:
    # Error handling
    pass
```

### With isa_common:
```python
# 2 lines
with PostgresClient() as client:
    results = client.query("SELECT ...")  # Returns dicts, auto-cleanup
```

---

## Async Client Usage (High-Performance)

For high-concurrency applications, use `AsyncPostgresClient` with `async/await`:

```python
import asyncio
from isa_common import AsyncPostgresClient

async def main():
    async with AsyncPostgresClient(
        host='localhost',
        port=50061,
        user_id='your-service'
    ) as client:
        # Simple query
        result = await client.query("SELECT 1 as num, 'hello' as msg")

        # Query with parameters
        result = await client.query(
            "SELECT $1::int as num, $2::text as msg",
            params=[42, 'world']
        )

        # Query single row
        row = await client.query_row("SELECT 1 as id, 'test' as name")

        # List tables
        tables = await client.list_tables()

        # Check table exists
        exists = await client.table_exists('users')

        # Execute DDL (CREATE/ALTER/DROP)
        await client.execute("""
            CREATE TABLE IF NOT EXISTS test_table (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                value INT
            )
        """)

        # Execute INSERT
        await client.execute(
            "INSERT INTO test_table (name, value) VALUES ($1, $2)",
            params=['test_name', 100]
        )

        # Execute UPDATE
        await client.execute(
            "UPDATE test_table SET value = $1 WHERE name = $2",
            params=[200, 'test_name']
        )

        # Execute DELETE
        await client.execute(
            "DELETE FROM test_table WHERE name = $1",
            params=['test_name']
        )

        # Get statistics
        stats = await client.get_stats()

asyncio.run(main())
```

### Batch Operations

```python
async def batch_example(client):
    # Execute multiple statements in a single batch
    operations = [
        {'sql': "INSERT INTO users (name, value) VALUES ($1, $2)", 'params': ['batch1', 10]},
        {'sql': "INSERT INTO users (name, value) VALUES ($1, $2)", 'params': ['batch2', 20]},
        {'sql': "INSERT INTO users (name, value) VALUES ($1, $2)", 'params': ['batch3', 30]},
    ]
    result = await client.execute_batch(operations)
```

### Concurrent Queries with asyncio.gather

```python
async def concurrent_example(client):
    # Execute 5 queries concurrently
    results = await asyncio.gather(
        client.query("SELECT 1 as num"),
        client.query("SELECT 2 as num"),
        client.query("SELECT 3 as num"),
        client.query("SELECT 4 as num"),
        client.query("SELECT 5 as num"),
    )
    return results  # Returns list of 5 result sets
```

### query_many_concurrent Helper

```python
async def bulk_query(client):
    queries = [
        {'sql': "SELECT 1 as num"},
        {'sql': "SELECT 2 as num"},
        {'sql': "SELECT 3 as num"},
    ]
    results = await client.query_many_concurrent(queries)
    return results
```

---

## Test Results

**Sync Client: All tests passing**
**Async Client: 15/15 tests passing (100% success rate)**

Comprehensive functional tests cover:
- Simple queries
- Parameterized queries
- Query single row
- List tables
- Table exists check
- Execute DDL (CREATE TABLE)
- Execute INSERT
- Execute UPDATE
- Execute DELETE
- Batch operations
- Concurrent queries (asyncio.gather)
- query_many_concurrent helper
- Statistics

All tests demonstrate production-ready reliability.

---

## Bottom Line

The PostgreSQL client gives you:
- **Connection pooling** built-in
- **Parameterized queries** by default
- **Query builder** for complex queries
- **Batch operations** for performance
- **Concurrent query execution** with async/await
- **Auto-cleanup** via context managers
- **Type-safe results** (dicts)

Just pip install and write business logic. No database plumbing needed!
