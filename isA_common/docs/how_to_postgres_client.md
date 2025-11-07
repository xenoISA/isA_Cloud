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

## Bottom Line

The PostgreSQL client gives you:
- **Connection pooling** built-in
- **Parameterized queries** by default
- **Query builder** for complex queries
- **Batch operations** for performance
- **Auto-cleanup** via context managers
- **Type-safe results** (dicts)

Just pip install and write business logic. No database plumbing needed! 🎯
