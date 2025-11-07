# 🦆 DuckDB Client - Analytical Computing Made Simple

## Installation

```bash
pip install -e /path/to/isA_Cloud/isA_common
```

## Architecture Pattern

**Hot Data + Cold Storage = Zero-Copy Analytics**

```
MinIO (Cold Parquet) → DuckDB (Hot Data) → Compute → MinIO (Results)
```

- **Cold Storage**: Parquet files in MinIO (long-term, compressed)
- **Hot Storage**: DuckDB tables (fast analytics, temporary)
- **Zero-Copy**: Query MinIO directly without importing
- **Data Flow**: Import → Analyze → Export

## Simple Usage Pattern

```python
from isa_common.duckdb_client import DuckDBClient
from isa_common.minio_client import MinIOClient

# Connect and use (auto-discovers via Consul or use direct host)
with DuckDBClient(host='localhost', port=50052, user_id='your-service') as client:

    # 1. Create analytical database
    db_info = client.create_database('analytics_db', minio_bucket='duckdb-data')
    database_id = db_info['database_id']

    # 2. Create table for hot data
    schema = {'user_id': 'INTEGER', 'revenue': 'DOUBLE', 'date': 'DATE'}
    client.create_table(database_id, 'sales', schema)

    # 3. Execute analytical queries
    result = client.execute_query(database_id, """
        SELECT user_id, SUM(revenue) as total
        FROM sales
        GROUP BY user_id
        ORDER BY total DESC
    """)

    # 4. Import from MinIO (cold → hot)
    client.import_from_minio(database_id, 'sales', 'bucket', 'data.parquet', 'parquet')

    # 5. Query MinIO directly (zero-copy)
    data = client.query_minio_file(database_id, 'bucket', 'data.csv', 'csv')

    # 6. Export results to MinIO (hot → cold)
    client.export_to_minio(database_id, 'SELECT * FROM sales', 'bucket', 'results.parquet', 'parquet')
```

---

## Real Service Example: Analytics Service

```python
from isa_common.duckdb_client import DuckDBClient
from isa_common.minio_client import MinIOClient
from datetime import datetime

class AnalyticsService:
    def __init__(self):
        self.duckdb = DuckDBClient(user_id='analytics-service')
        self.minio = MinIOClient(user_id='analytics-service')
        self.bucket = 'analytics-data'
        self.database_id = None

    def initialize(self):
        # Setup hot database for analytics
        with self.duckdb:
            db_info = self.duckdb.create_database(
                'analytics_workspace',
                minio_bucket=self.bucket
            )
            self.database_id = db_info['database_id']

    def ingest_daily_data(self, date):
        # Import cold data from MinIO into hot storage
        with self.duckdb:
            # ONE CALL to import from MinIO
            return self.duckdb.import_from_minio(
                self.database_id,
                f'events_{date}',
                self.bucket,
                f'raw/{date}/events.parquet',
                file_format='parquet'
            )

    def run_analytics(self, query_template):
        # Run OLAP analytics on hot data - ONE CALL
        with self.duckdb:
            return self.duckdb.execute_query(
                self.database_id,
                query_template
            )

    def compute_user_metrics(self):
        # Complex analytical query (DuckDB's strength)
        with self.duckdb:
            sql = """
            WITH user_activity AS (
                SELECT
                    user_id,
                    COUNT(*) as event_count,
                    SUM(revenue) as total_revenue,
                    AVG(session_duration) as avg_session
                FROM events
                GROUP BY user_id
            )
            SELECT
                user_id,
                event_count,
                total_revenue,
                avg_session,
                ROW_NUMBER() OVER (ORDER BY total_revenue DESC) as revenue_rank
            FROM user_activity
            WHERE total_revenue > 0
            """
            
            return self.duckdb.execute_query(self.database_id, sql)

    def save_results(self, query, output_path):
        # Export computed results back to MinIO cold storage
        with self.duckdb, self.minio:
            return self.duckdb.export_to_minio(
                self.database_id,
                query,
                self.bucket,
                output_path,
                file_format='parquet',
                overwrite=True
            )

    def ad_hoc_query_cold_data(self, file_path):
        # Query cold data directly without importing (zero-copy!)
        with self.duckdb:
            return self.duckdb.query_minio_file(
                self.database_id,
                self.bucket,
                file_path,
                file_format='parquet',
                limit=1000
            )

    def cleanup(self):
        # Clean up hot storage after analysis
        with self.duckdb:
            self.duckdb.delete_database(
                self.database_id,
                delete_from_minio=False,  # Keep cold data
                force=True
            )
```

---

## Quick Patterns for Common Use Cases

### Database Management
```python
# Create database (with MinIO bucket for cold storage)
db_info = client.create_database(
    'my_analytics',
    minio_bucket='analytics-bucket',
    metadata={'project': 'sales-analysis', 'team': 'data'}
)
database_id = db_info['database_id']

# List databases
databases = client.list_databases()
for db in databases:
    print(f"{db['name']}: {db['database_id']}")

# Delete database (with cleanup)
client.delete_database(database_id, delete_from_minio=True, force=True)
```

### Table Operations
```python
# Create table with schema
schema = {
    'user_id': 'INTEGER',
    'name': 'VARCHAR',
    'email': 'VARCHAR',
    'signup_date': 'DATE',
    'revenue': 'DOUBLE'
}
client.create_table(database_id, 'users', schema)

# Get table schema
table_schema = client.get_table_schema(database_id, 'users')
for col in table_schema['columns']:
    print(f"{col['name']}: {col['type']}")

# Get table statistics
stats = client.get_table_stats(database_id, 'users', include_columns=True)
print(f"Rows: {stats['row_count']}")
print(f"Size: {stats['estimated_size_bytes']/1024:.2f}KB")

# List tables
tables = client.list_tables(database_id)

# Drop table
client.drop_table(database_id, 'users', if_exists=True)
```

### SQL Query Execution
```python
# Simple SELECT
rows = client.execute_query(database_id, "SELECT * FROM users LIMIT 10")

# Aggregation (DuckDB is optimized for this!)
result = client.execute_query(database_id, """
    SELECT
        DATE_TRUNC('month', signup_date) as month,
        COUNT(*) as new_users,
        SUM(revenue) as total_revenue
    FROM users
    GROUP BY month
    ORDER BY month DESC
""")

# Window functions
result = client.execute_query(database_id, """
    SELECT
        user_id,
        revenue,
        AVG(revenue) OVER (PARTITION BY DATE_TRUNC('month', signup_date)) as monthly_avg,
        RANK() OVER (ORDER BY revenue DESC) as revenue_rank
    FROM users
""")

# CTEs (Common Table Expressions)
result = client.execute_query(database_id, """
    WITH high_value_users AS (
        SELECT * FROM users WHERE revenue > 1000
    )
    SELECT COUNT(*) as count, AVG(revenue) as avg_revenue
    FROM high_value_users
""")
```

### Batch Operations (Transactions)
```python
# Execute multiple statements in transaction
statements = [
    "INSERT INTO users VALUES (1, 'Alice', 'alice@example.com', '2024-01-01', 100.0)",
    "INSERT INTO users VALUES (2, 'Bob', 'bob@example.com', '2024-01-02', 200.0)",
    "UPDATE users SET revenue = revenue * 1.1 WHERE user_id = 2"
]

result = client.execute_batch(database_id, statements, use_transaction=True)
if result['success']:
    print(f"Executed {len(result['results'])} statements")
```

### Import from MinIO (Cold → Hot)
```python
# Import Parquet file
client.import_from_minio(
    database_id,
    'sales_data',  # Table name
    'analytics-bucket',
    'raw/2024/sales.parquet',
    file_format='parquet'
)

# Import CSV file
client.import_from_minio(
    database_id,
    'events',
    'analytics-bucket',
    'logs/events.csv',
    file_format='csv'
)

# Now query hot data
result = client.execute_query(database_id, """
    SELECT product_id, SUM(quantity) as total_sold
    FROM sales_data
    GROUP BY product_id
""")
```

### Query MinIO Directly (Zero-Copy)
```python
# Query cold data WITHOUT importing (DuckDB's superpower!)
result = client.query_minio_file(
    database_id,
    'analytics-bucket',
    'archive/2023/sales.parquet',
    file_format='parquet',
    limit=1000
)

# Analyze results
print(f"Found {len(result)} rows")
for row in result[:5]:
    print(row)

# Use for: Ad-hoc queries, data exploration, one-time analysis
```

### Export to MinIO (Hot → Cold)
```python
# Export query results as Parquet
result = client.export_to_minio(
    database_id,
    """
    SELECT
        user_id,
        SUM(revenue) as total_revenue,
        COUNT(*) as order_count
    FROM orders
    GROUP BY user_id
    """,
    'analytics-bucket',
    'processed/user_summary.parquet',
    file_format='parquet',
    overwrite=True
)

print(f"Exported {result['rows_exported']} rows")

# Export as CSV
client.export_to_minio(
    database_id,
    "SELECT * FROM users",
    'analytics-bucket',
    'exports/users.csv',
    file_format='csv'
)
```

### Advanced Analytics (Window Functions, Time Series)
```python
# Moving average
result = client.execute_query(database_id, """
    SELECT
        date,
        revenue,
        AVG(revenue) OVER (
            ORDER BY date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) as moving_avg_7d
    FROM daily_sales
    ORDER BY date
""")

# Lag/Lead for trends
result = client.execute_query(database_id, """
    SELECT
        date,
        revenue,
        LAG(revenue) OVER (ORDER BY date) as prev_day,
        revenue - LAG(revenue) OVER (ORDER BY date) as daily_change
    FROM daily_sales
""")

# Percentiles
result = client.execute_query(database_id, """
    SELECT
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY revenue) as median,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY revenue) as p95
    FROM users
""")
```

### Data Warehouse Pattern (Star Schema)
```python
# Create dimension table
client.create_table(database_id, 'dim_products', {
    'product_id': 'INTEGER',
    'product_name': 'VARCHAR',
    'category': 'VARCHAR'
})

# Create fact table
client.create_table(database_id, 'fact_sales', {
    'sale_id': 'INTEGER',
    'product_id': 'INTEGER',
    'quantity': 'INTEGER',
    'amount': 'DOUBLE',
    'sale_date': 'DATE'
})

# Analytical query with join
result = client.execute_query(database_id, """
    SELECT
        p.category,
        p.product_name,
        SUM(s.quantity) as units_sold,
        SUM(s.amount) as revenue
    FROM fact_sales s
    JOIN dim_products p ON s.product_id = p.product_id
    GROUP BY p.category, p.product_name
    ORDER BY revenue DESC
""")
```

### Complete Data Pipeline
```python
# Step 1: Import raw data from MinIO
client.import_from_minio(
    database_id, 'raw_orders',
    'data-bucket', 'raw/orders.csv', 'csv'
)

# Step 2: Transform and analyze
transform_sql = """
    SELECT
        DATE_TRUNC('day', order_date) as date,
        product_category,
        COUNT(*) as order_count,
        SUM(amount) as total_revenue,
        AVG(amount) as avg_order_value
    FROM raw_orders
    GROUP BY date, product_category
"""

results = client.execute_query(database_id, transform_sql)

# Step 3: Export processed results to MinIO
client.export_to_minio(
    database_id,
    transform_sql,
    'data-bucket',
    'processed/daily_summary.parquet',
    file_format='parquet'
)

# Pipeline complete: Raw → DuckDB → Compute → Parquet
```

---

## Benefits = Zero Analytical Complexity

### What you DON'T need to worry about:
- ❌ SQL engine setup
- ❌ Parquet file handling
- ❌ Connection management
- ❌ Schema inference
- ❌ Query optimization
- ❌ gRPC serialization
- ❌ Data type conversions
- ❌ Transaction management
- ❌ S3/MinIO protocol details

### What you CAN focus on:
- ✅ Your analytical queries
- ✅ Your data pipelines
- ✅ Your business metrics
- ✅ Hot vs cold data strategy
- ✅ Query performance
- ✅ Data transformations

---

## Comparison: Without vs With Client

### Without (Raw DuckDB + MinIO + gRPC):
```python
# 200+ lines of setup, S3 config, query building...
import duckdb
import boto3
import grpc
from duckdb_pb2_grpc import DuckDBServiceStub

# Setup S3 for MinIO
s3_client = boto3.client(
    's3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin'
)

# Setup gRPC
channel = grpc.insecure_channel('localhost:50052')
stub = DuckDBServiceStub(channel)

# Setup DuckDB
conn = duckdb.connect(':memory:')
conn.execute("""
    INSTALL httpfs;
    LOAD httpfs;
    SET s3_endpoint='localhost:9000';
    SET s3_access_key_id='minioadmin';
    SET s3_secret_access_key='minioadmin';
""")

try:
    # Query Parquet from MinIO
    result = conn.execute("""
        SELECT * FROM read_parquet('s3://bucket/data.parquet')
    """).fetchall()
    
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
    channel.close()
```

### With isa_common:
```python
# 4 lines
with DuckDBClient() as client:
    db_id = client.create_database('analytics', 'bucket')['database_id']
    data = client.query_minio_file(db_id, 'bucket', 'data.parquet', 'parquet')
```

---

## Complete Feature List

| **Database Management**: create, list, delete with UUID tracking
| **Table Operations**: create, schema, stats, list, drop
| **Query Execution**: execute_query, execute_statement, execute_batch
| **MinIO Integration**: import_from_minio, query_minio_file, export_to_minio
| **Advanced Analytics**: Window functions, CTEs, aggregations
| **Transaction Support**: Atomic batch operations
| **Health Check**: Service monitoring
| **Zero-Copy Queries**: Direct MinIO file access
| **Parquet Support**: Native columnar format
| **CSV Support**: Text file import/export
| **Hot Data Lifecycle**: Create, analyze, export, cleanup
| **Multi-tenancy**: User-scoped databases
| **Schema Management**: Type-safe table definitions

---

## Test Results

**Comprehensive functional tests passing**

Tests cover:
- Database lifecycle operations
- Table creation and management
- SQL query execution (SELECT, aggregation)
- Batch operations with transactions
- MinIO import (cold → hot)
- Zero-copy MinIO queries
- MinIO export (hot → cold)
- Advanced analytics (window functions, CTEs)
- Data pipeline workflows

All tests demonstrate production-ready reliability.

---

## DuckDB vs Traditional Databases

### ❌ NOT designed for:
- OLTP (transactional workloads)
- Concurrent writes
- Real-time updates
- Multi-user write contention

### ✅ PERFECT for:
- OLAP (analytical workloads)
- Batch processing
- Data transformation
- Ad-hoc analytics
- Reporting and dashboards
- Data science workflows
- ETL pipelines

### 💡 Best Practice:
Use DuckDB WITH PostgreSQL/MySQL:
- PostgreSQL: OLTP (transactions, users, orders)
- DuckDB: OLAP (analytics, reports, aggregations)

---

## Bottom Line

Instead of wrestling with DuckDB setup, S3 configuration, Parquet handling, and query optimization...

**You write 4 lines and run analytics.** 🦆

The DuckDB client gives you:
- **Production-ready** analytical computing out of the box
- **Zero-copy analytics** query MinIO directly without import
- **Hot + Cold architecture** optimize storage and compute costs
- **Parquet native** columnar format for fast analytics
- **MinIO integration** seamless import/export workflows
- **Advanced SQL** window functions, CTEs, complex aggregations
- **Data pipelines** import → analyze → export automation
- **Transaction support** atomic batch operations
- **Multi-tenancy** user-scoped databases
- **Auto-cleanup** context managers and lifecycle management

Just pip install and focus on your analytical queries and data insights!

