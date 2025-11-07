#!/usr/bin/env python3
"""
DuckDB Client Usage Examples
==============================

This example demonstrates how to use the DuckDBClient from isa_common package.
DuckDB is used as a computing engine with MinIO as the storage layer.

File: isA_common/examples/duck_client_examples.py

Design Pattern:
---------------
**Hot Data + Cold Storage Architecture**

MinIO (Cold Parquet) → DuckDB (Hot Data) → Compute → MinIO (Results)

- **Cold Data**: Parquet files in MinIO (long-term storage)
- **Hot Data**: Frequently accessed data in DuckDB (fast analytics)
- **Zero-Copy**: DuckDB can query MinIO directly without importing
- **Computing**: DuckDB for selection, Polars for computation
- **Data Flow**: Import from MinIO → Compute → Export back to MinIO

Prerequisites:
--------------
1. DuckDB gRPC service must be running (default: localhost:50052)
2. MinIO gRPC service must be running (default: localhost:50051)
3. Install isa_common package:
   ```bash
   pip install -e /path/to/isA_Cloud/isA_common
   ```

Usage:
------
```bash
# Run all examples
python isA_common/examples/duck_client_examples.py

# Run with custom host/port
python isA_common/examples/duck_client_examples.py --host 192.168.1.100 --port 50052

# Run specific example
python isA_common/examples/duck_client_examples.py --example 5
```

Features Demonstrated:
----------------------
✅ Health Check
✅ Database Management (Create, List, Delete with UUID tracking)
✅ Table Operations (Create, Schema, Stats, Drop)
✅ SQL Query Execution (SELECT, Aggregation, Window Functions)
✅ Batch SQL Operations (Transactions)
✅ Import from MinIO (Cold → Hot data flow)
✅ Query MinIO Directly (Zero-copy analytics)
✅ Export to MinIO (Hot → Cold data flow, save results as Parquet)
✅ Advanced Analytics (Window functions, CTEs, OLAP queries)
✅ Hot Data Lifecycle Management
✅ Polars + DuckDB Integration Pattern

Note: DuckDB is optimized for OLAP (analytical) queries, not OLTP (transactional).
"""

import sys
import argparse
import random
from datetime import datetime
from typing import Dict, List
from isa_common.consul_client import ConsulRegistry

# Import the DuckDBClient from isa_common
try:
    from isa_common.duckdb_client import DuckDBClient
    from isa_common.minio_client import MinIOClient
except ImportError:
    print("=" * 80)
    print("ERROR: Failed to import isa_common")
    print("=" * 80)
    print("\nPlease install isa_common package:")
    print("  cd /path/to/isA_Cloud")
    print("  pip install -e isA_common")
    print()
    sys.exit(1)


def example_01_health_check(host='localhost', port=50052):
    """
    Example 1: Health Check
    
    Check if the DuckDB gRPC service is healthy and operational.
    File: duckdb_client.py, Method: health_check()
    """
    print("\n" + "=" * 80)
    print("Example 1: Service Health Check")
    print("=" * 80)
    
    with DuckDBClient(host=host, port=port, user_id='example_user') as client:
        health = client.health_check()
        
        if health:
            print(f"✅ DuckDB service is healthy!")
            print(f"   Ready for analytical computing")
            print(f"   MinIO integration enabled for cold storage")
        else:
            print("❌ Service is not healthy")


def example_02_database_management(host='localhost', port=50052):
    """
    Example 2: Database Management
    
    Create, list, and manage databases. Each database has a UUID for tracking.
    File: duckdb_client.py, Methods: create_database(), list_databases(), delete_database()
    """
    print("\n" + "=" * 80)
    print("Example 2: Database Management (UUID Tracking)")
    print("=" * 80)
    
    with DuckDBClient(host=host, port=port, user_id='example_user') as client:
        print("\n📦 Creating database for analytics...")
        
        # Create database with MinIO bucket for cold storage
        db_info = client.create_database(
            db_name='analytics_db',
            minio_bucket='duckdb-data',
            metadata={'purpose': 'hot-data-analytics', 'team': 'data-science'}
        )
        
        if db_info:
            database_id = db_info.get('database_id')
            print(f"✅ Database created!")
            print(f"   Database ID: {database_id}")
            print(f"   Name: {db_info.get('name')}")
            print(f"   MinIO Bucket: {db_info.get('minio_bucket')}")
            
            # List all databases
            print(f"\n📋 Listing all databases:")
            databases = client.list_databases()
            for db in databases:
                print(f"   - {db['name']} (ID: {db['database_id'][:8]}...)")
            
            # Cleanup
            print(f"\n🗑️  Cleaning up...")
            client.delete_database(database_id, delete_from_minio=True, force=True)
            print(f"   Database deleted (including MinIO files)")


def example_03_table_operations(host='localhost', port=50052):
    """
    Example 3: Table Operations
    
    Create tables, define schemas, get statistics, and manage hot data tables.
    File: duckdb_client.py, Methods: create_table(), get_table_schema(), get_table_stats()
    """
    print("\n" + "=" * 80)
    print("Example 3: Table Operations (Hot Data Schema)")
    print("=" * 80)
    
    with DuckDBClient(host=host, port=port, user_id='example_user') as client:
        # Create database
        db_info = client.create_database('temp_analytics', minio_bucket='duckdb-data')
        database_id = db_info['database_id']
        
        try:
            print("\n📊 Creating table for hot data...")
            
            # Define schema for user events
            schema = {
                'user_id': 'INTEGER',
                'event_type': 'VARCHAR',
                'timestamp': 'TIMESTAMP',
                'revenue': 'DOUBLE',
                'session_id': 'VARCHAR'
            }
            
            success = client.create_table(database_id, 'user_events', schema)
            
            if success:
                print(f"✅ Table 'user_events' created")
                
                # Insert sample data
                print(f"\n📝 Inserting sample hot data...")
                insert_sql = """
                INSERT INTO user_events VALUES
                (1, 'page_view', '2024-01-01 10:00:00', 0, 'sess_001'),
                (1, 'purchase', '2024-01-01 10:05:00', 99.99, 'sess_001'),
                (2, 'page_view', '2024-01-01 10:10:00', 0, 'sess_002'),
                (2, 'purchase', '2024-01-01 10:15:00', 149.99, 'sess_002'),
                (3, 'page_view', '2024-01-01 10:20:00', 0, 'sess_003')
                """
                client.execute_statement(database_id, insert_sql)
                print(f"   5 events inserted")
                
                # Get table schema
                print(f"\n📋 Table schema:")
                table_schema = client.get_table_schema(database_id, 'user_events')
                for col in table_schema['columns']:
                    print(f"   - {col['name']}: {col['data_type']}")
                
                # Get table statistics
                print(f"\n📈 Table statistics:")
                stats = client.get_table_stats(database_id, 'user_events', include_columns=True)
                print(f"   Rows: {stats['row_count']}")
                print(f"   Columns: {len(stats.get('column_stats', []))}")
                print(f"   Estimated size: {stats['size_bytes'] / 1024:.2f} KB")
                
        finally:
            # Cleanup
            client.delete_database(database_id, delete_from_minio=True, force=True)


def example_04_query_operations(host='localhost', port=50052):
    """
    Example 4: Query Operations
    
    Execute SELECT queries and analytical aggregations.
    File: duckdb_client.py, Methods: execute_query(), execute_statement()
    """
    print("\n" + "=" * 80)
    print("Example 4: Query Operations (OLAP Queries)")
    print("=" * 80)
    
    with DuckDBClient(host=host, port=port, user_id='example_user') as client:
        # Setup
        db_info = client.create_database('query_demo', minio_bucket='duckdb-data')
        database_id = db_info['database_id']
        
        try:
            # Create and populate table
            schema = {'user_id': 'INTEGER', 'event_type': 'VARCHAR', 'revenue': 'DOUBLE'}
            client.create_table(database_id, 'events', schema)
            
            insert_sql = """
            INSERT INTO events VALUES
            (1, 'purchase', 99.99),
            (2, 'purchase', 149.99),
            (1, 'purchase', 79.99),
            (3, 'view', 0),
            (2, 'purchase', 199.99)
            """
            client.execute_statement(database_id, insert_sql)
            
            print("\n🔍 Query 1: Simple SELECT")
            result = client.execute_query(database_id, "SELECT * FROM events ORDER BY user_id")
            print(f"   Retrieved {len(result)} rows")
            for row in result[:3]:
                print(f"   - User {row['user_id']}: {row['event_type']} (${row['revenue']})")
            
            print("\n📊 Query 2: Analytical Aggregation (DuckDB strength)")
            sql = """
            SELECT
                event_type,
                COUNT(*) as event_count,
                SUM(revenue) as total_revenue,
                AVG(revenue) as avg_revenue,
                MAX(revenue) as max_revenue
            FROM events
            GROUP BY event_type
            ORDER BY total_revenue DESC
            """
            result = client.execute_query(database_id, sql)
            
            for row in result:
                print(f"   {row['event_type']}:")
                print(f"      Count: {row['event_count']}")
                print(f"      Total: ${row['total_revenue']:.2f}")
                print(f"      Average: ${row['avg_revenue']:.2f}")
            
        finally:
            client.delete_database(database_id, delete_from_minio=True, force=True)


def example_05_batch_operations(host='localhost', port=50052):
    """
    Example 5: Batch SQL Operations
    
    Execute multiple SQL statements efficiently in a transaction.
    File: duckdb_client.py, Method: execute_batch()
    """
    print("\n" + "=" * 80)
    print("Example 5: Batch SQL Operations (Transactions)")
    print("=" * 80)
    
    with DuckDBClient(host=host, port=port, user_id='example_user') as client:
        db_info = client.create_database('batch_demo', minio_bucket='duckdb-data')
        database_id = db_info['database_id']
        
        try:
            # Create table
            schema = {'id': 'INTEGER', 'value': 'VARCHAR', 'amount': 'DOUBLE'}
            client.create_table(database_id, 'batch_test', schema)
            
            print("\n⚡ Executing batch operations in transaction...")
            
            # Batch statements
            statements = [
                "INSERT INTO batch_test VALUES (1, 'initial', 100.0)",
                "INSERT INTO batch_test VALUES (2, 'initial', 200.0)",
                "INSERT INTO batch_test VALUES (3, 'initial', 300.0)",
                "UPDATE batch_test SET value = 'updated' WHERE id > 1",
                "UPDATE batch_test SET amount = amount * 1.1 WHERE value = 'updated'"
            ]
            
            result = client.execute_batch(database_id, statements, use_transaction=True)
            
            if result['success']:
                print(f"✅ Batch executed successfully")
                print(f"   Statements executed: {len(result['results'])}")
                print(f"   All changes committed atomically")
                
                # Verify results
                rows = client.execute_query(database_id, "SELECT * FROM batch_test ORDER BY id")
                print(f"\n📊 Final state:")
                for row in rows:
                    print(f"   ID {row['id']}: {row['value']} = ${row['amount']:.2f}")
            
        finally:
            client.delete_database(database_id, delete_from_minio=True, force=True)


def example_06_import_from_minio(host='localhost', port=50052):
    """
    Example 6: Import from MinIO (Cold → Hot Data Flow)
    
    Import cold data from MinIO Parquet files into DuckDB hot storage.
    File: duckdb_client.py, Method: import_from_minio()
    """
    print("\n" + "=" * 80)
    print("Example 6: Import from MinIO (Cold → Hot Data Flow)")
    print("=" * 80)
    
    with DuckDBClient(host=host, port=port, user_id='example_user') as duckdb, \
         MinIOClient(host='localhost', port=50051, user_id='example_user') as minio:
        
        # Create database
        db_info = duckdb.create_database('import_demo', minio_bucket='duckdb-data')
        database_id = db_info['database_id']
        
        try:
            # Step 1: Create cold data in MinIO
            print("\n❄️  Step 1: Creating cold data in MinIO (CSV file)...")
            
            if not minio.bucket_exists('duckdb-data'):
                minio.create_bucket('duckdb-data')
            
            csv_data = """user_id,product_id,quantity,price,date
1,PROD-001,2,29.99,2024-01-01
2,PROD-002,1,49.99,2024-01-01
3,PROD-001,3,29.99,2024-01-02
4,PROD-003,1,79.99,2024-01-02
5,PROD-002,2,49.99,2024-01-03
"""
            
            import io
            minio.put_object(
                'duckdb-data',
                'cold-data/orders.csv',
                io.BytesIO(csv_data.encode()),
                len(csv_data.encode())
            )
            print(f"   ✅ Cold data stored in MinIO: duckdb-data/cold-data/orders.csv")
            
            # Step 2: Import into DuckDB (hot storage)
            print(f"\n🔥 Step 2: Importing into DuckDB hot storage...")
            
            success = duckdb.import_from_minio(
                database_id,
                'orders',  # Table name
                'duckdb-data',  # Bucket
                'cold-data/orders.csv',  # Object key
                file_format='csv'
            )
            
            if success:
                print(f"   ✅ Data imported successfully")
                
                # Step 3: Query hot data (fast analytics)
                print(f"\n⚡ Step 3: Running analytics on hot data...")
                
                sql = """
                SELECT
                    product_id,
                    SUM(quantity) as total_quantity,
                    SUM(quantity * price) as total_revenue
                FROM orders
                GROUP BY product_id
                ORDER BY total_revenue DESC
                """
                
                results = duckdb.execute_query(database_id, sql)
                print(f"   Product analytics:")
                for row in results:
                    print(f"      {row['product_id']}: {row['total_quantity']} units, ${row['total_revenue']:.2f} revenue")

        finally:
            duckdb.delete_database(database_id, delete_from_minio=True, force=True)


def example_07_query_minio_direct(host='localhost', port=50052):
    """
    Example 7: Query MinIO Directly (Zero-Copy Analytics)
    
    Query MinIO files directly without importing (DuckDB's superpower).
    File: duckdb_client.py, Method: query_minio_file()
    """
    print("\n" + "=" * 80)
    print("Example 7: Query MinIO Directly (Zero-Copy Analytics)")
    print("=" * 80)
    
    with DuckDBClient(host=host, port=port, user_id='example_user') as duckdb, \
         MinIOClient(host='localhost', port=50051, user_id='example_user') as minio:
        
        db_info = duckdb.create_database('zerocopy_demo', minio_bucket='duckdb-data')
        database_id = db_info['database_id']
        
        try:
            # Create cold data in MinIO
            print("\n❄️  Creating cold data in MinIO...")
            
            if not minio.bucket_exists('duckdb-data'):
                minio.create_bucket('duckdb-data')
            
            csv_data = """log_id,level,message,timestamp
1,INFO,Application started,2024-01-01 00:00:00
2,ERROR,Database connection failed,2024-01-01 00:01:00
3,INFO,Request processed,2024-01-01 00:02:00
4,ERROR,Timeout occurred,2024-01-01 00:03:00
5,INFO,User logged in,2024-01-01 00:04:00
"""
            
            import io
            minio.put_object(
                'duckdb-data',
                'logs/app.csv',
                io.BytesIO(csv_data.encode()),
                len(csv_data.encode())
            )
            
            print(f"\n⚡ Zero-Copy Query: Analyzing cold data directly from MinIO...")
            print(f"   (No data import required!)")
            
            # Query MinIO file directly - no import needed!
            result = duckdb.query_minio_file(
                database_id,
                'duckdb-data',
                'logs/app.csv',
                file_format='csv',
                limit=100
            )
            
            if result:
                print(f"\n✅ Query successful! Retrieved {len(result)} rows")
                print(f"   (Data never left MinIO - true zero-copy analytics)")
                
                # Analyze results
                error_count = sum(1 for row in result if row['level'] == 'ERROR')
                info_count = sum(1 for row in result if row['level'] == 'INFO')
                
                print(f"\n📊 Log analysis:")
                print(f"   INFO logs: {info_count}")
                print(f"   ERROR logs: {error_count}")
                print(f"\n💡 Use case: Analyzing cold data without loading into hot storage")
            
        finally:
            duckdb.delete_database(database_id, delete_from_minio=True, force=True)


def example_08_export_to_minio(host='localhost', port=50052):
    """
    Example 8: Export to MinIO (Hot → Cold Data Flow)
    
    Compute results in DuckDB and export to MinIO as Parquet for long-term storage.
    File: duckdb_client.py, Method: export_to_minio()
    """
    print("\n" + "=" * 80)
    print("Example 8: Export to MinIO (Hot → Cold Data Flow)")
    print("=" * 80)
    
    with DuckDBClient(host=host, port=port, user_id='example_user') as duckdb, \
         MinIOClient(host='localhost', port=50051, user_id='example_user') as minio:
        
        db_info = duckdb.create_database('export_demo', minio_bucket='duckdb-data')
        database_id = db_info['database_id']
        
        try:
            # Step 1: Create hot data
            print("\n🔥 Step 1: Creating hot data in DuckDB...")
            
            schema = {'date': 'DATE', 'product': 'VARCHAR', 'sales': 'DOUBLE'}
            duckdb.create_table(database_id, 'daily_sales', schema)
            
            insert_sql = """
            INSERT INTO daily_sales VALUES
            ('2024-01-01', 'Product A', 1250.50),
            ('2024-01-01', 'Product B', 890.25),
            ('2024-01-02', 'Product A', 1420.75),
            ('2024-01-02', 'Product B', 920.00),
            ('2024-01-03', 'Product A', 1380.25),
            ('2024-01-03', 'Product B', 950.50)
            """
            duckdb.execute_statement(database_id, insert_sql)
            print(f"   ✅ 6 days of sales data loaded")
            
            # Step 2: Compute analytics
            print(f"\n⚡ Step 2: Computing analytics...")
            
            analysis_sql = """
            SELECT
                product,
                COUNT(*) as days_sold,
                SUM(sales) as total_sales,
                AVG(sales) as avg_daily_sales,
                MIN(sales) as min_sales,
                MAX(sales) as max_sales
            FROM daily_sales
            GROUP BY product
            ORDER BY total_sales DESC
            """
            
            # Step 3: Export results to MinIO as Parquet
            print(f"\n❄️  Step 3: Exporting results to MinIO (cold storage as Parquet)...")
            
            if not minio.bucket_exists('duckdb-data'):
                minio.create_bucket('duckdb-data')
            
            result = duckdb.export_to_minio(
                database_id,
                analysis_sql,
                'duckdb-data',
                'analytics/sales_summary.parquet',
                file_format='parquet',
                overwrite=True
            )
            
            if result['success']:
                print(f"   ✅ Results exported to MinIO")
                print(f"      Rows exported: {result['rows_exported']}")
                print(f"      File: duckdb-data/analytics/sales_summary.parquet")
                
                # Verify in MinIO
                objects = minio.list_objects('duckdb-data', prefix='analytics/')
                if any('sales_summary.parquet' in obj for obj in objects):
                    print(f"      ✅ Verified: File exists in MinIO cold storage")
                
                print(f"\n💡 Use case: Save computed results for long-term analysis")
            
        finally:
            duckdb.delete_database(database_id, delete_from_minio=True, force=True)


def example_09_advanced_analytics(host='localhost', port=50052):
    """
    Example 9: Advanced Analytical Queries
    
    Window functions, CTEs, and complex OLAP queries (DuckDB's strength).
    File: duckdb_client.py, Method: execute_query()
    """
    print("\n" + "=" * 80)
    print("Example 9: Advanced Analytical Queries (DuckDB OLAP Strength)")
    print("=" * 80)
    
    with DuckDBClient(host=host, port=port, user_id='example_user') as client:
        db_info = client.create_database('analytics_demo', minio_bucket='duckdb-data')
        database_id = db_info['database_id']
        
        try:
            # Create sales data
            schema = {'sale_id': 'INTEGER', 'product': 'VARCHAR', 'amount': 'DOUBLE', 'date': 'DATE'}
            client.create_table(database_id, 'sales', schema)
            
            insert_sql = """
            INSERT INTO sales VALUES
            (1, 'Laptop', 1200, '2024-01-01'),
            (2, 'Phone', 800, '2024-01-01'),
            (3, 'Laptop', 1300, '2024-01-02'),
            (4, 'Tablet', 500, '2024-01-02'),
            (5, 'Phone', 900, '2024-01-03'),
            (6, 'Laptop', 1100, '2024-01-03'),
            (7, 'Tablet', 600, '2024-01-04'),
            (8, 'Phone', 850, '2024-01-04')
            """
            client.execute_statement(database_id, insert_sql)
            
            print("\n📊 Query 1: Window Functions (Ranking)")
            sql = """
            SELECT
                sale_id,
                product,
                amount,
                ROW_NUMBER() OVER (PARTITION BY product ORDER BY amount DESC) as rank_in_category,
                AVG(amount) OVER (PARTITION BY product) as category_avg
            FROM sales
            ORDER BY product, rank_in_category
            """
            
            result = client.execute_query(database_id, sql)
            print(f"   Top sales by product category:")
            for row in result[:4]:
                print(f"      {row['product']}: ${row['amount']} (rank #{row['rank_in_category']}, avg: ${row['category_avg']:.2f})")
            
            print("\n📈 Query 2: CTEs (Common Table Expressions)")
            sql = """
            WITH high_value_sales AS (
                SELECT product, amount
                FROM sales
                WHERE amount > 700
            ),
            product_stats AS (
                SELECT
                    product,
                    COUNT(*) as high_value_count,
                    AVG(amount) as avg_amount
                FROM high_value_sales
                GROUP BY product
            )
            SELECT *
            FROM product_stats
            ORDER BY avg_amount DESC
            """
            
            result = client.execute_query(database_id, sql)
            print(f"   High-value sales analysis:")
            for row in result:
                print(f"      {row['product']}: {row['high_value_count']} sales, avg ${row['avg_amount']:.2f}")
            
            print("\n💡 DuckDB excels at:")
            print(f"   - Window functions (ROW_NUMBER, RANK, LAG, LEAD)")
            print(f"   - CTEs for readable complex queries")
            print(f"   - OLAP operations (aggregations, analytics)")
            
        finally:
            client.delete_database(database_id, delete_from_minio=True, force=True)


def example_10_hot_data_lifecycle(host='localhost', port=50052):
    """
    Example 10: Hot Data Lifecycle Management
    
    Create, use, and cleanup temporary hot data tables.
    File: duckdb_client.py, Methods: create_table(), drop_table(), list_tables()
    """
    print("\n" + "=" * 80)
    print("Example 10: Hot Data Lifecycle Management")
    print("=" * 80)
    
    with DuckDBClient(host=host, port=port, user_id='example_user') as client:
        db_info = client.create_database('lifecycle_demo', minio_bucket='duckdb-data')
        database_id = db_info['database_id']
        
        try:
            print("\n🔥 Lifecycle: Create → Use → Archive → Drop")
            
            # Create temporary hot data
            print("\n   Step 1: CREATE hot data table")
            schema = {'session_id': 'VARCHAR', 'events': 'INTEGER', 'duration': 'INTEGER'}
            client.create_table(database_id, 'temp_sessions', schema)
            
            client.execute_statement(database_id, """
                INSERT INTO temp_sessions VALUES
                ('sess_001', 15, 300),
                ('sess_002', 8, 150),
                ('sess_003', 22, 450)
            """)
            print(f"      ✅ Created and populated temp_sessions")
            
            # Use hot data
            print("\n   Step 2: USE hot data for fast analytics")
            result = client.execute_query(database_id, "SELECT AVG(events) as avg_events FROM temp_sessions")
            print(f"      Average events per session: {result[0]['avg_events']:.1f}")
            
            # Check before cleanup
            tables = client.list_tables(database_id)
            print(f"\n   Step 3: Before cleanup - Tables: {', '.join(tables)}")
            
            # Drop hot data
            print(f"\n   Step 4: DROP hot data table")
            client.drop_table(database_id, 'temp_sessions', if_exists=True)
            print(f"      ✅ Table dropped")
            
            # Verify cleanup
            tables = client.list_tables(database_id)
            print(f"\n   Step 5: After cleanup - Tables: {', '.join(tables) if tables else 'none'}")
            
            print(f"\n💡 Use case: Manage temporary hot data for real-time analytics")
            
        finally:
            client.delete_database(database_id, delete_from_minio=True, force=True)


def example_11_polars_duckdb_pattern(host='localhost', port=50052):
    """
    Example 11: Polars + DuckDB Integration Pattern
    
    DuckDB for data selection, Polars for computation (complementary strengths).
    File: duckdb_client.py, Method: execute_query()
    """
    print("\n" + "=" * 80)
    print("Example 11: Polars + DuckDB Integration Pattern")
    print("=" * 80)
    
    with DuckDBClient(host=host, port=port, user_id='example_user') as client:
        db_info = client.create_database('polars_demo', minio_bucket='duckdb-data')
        database_id = db_info['database_id']
        
        try:
            # Setup data
            schema = {'user_id': 'INTEGER', 'category': 'VARCHAR', 'amount': 'DOUBLE'}
            client.create_table(database_id, 'transactions', schema)
            
            insert_sql = """
            INSERT INTO transactions VALUES
            (1, 'electronics', 1200),
            (1, 'books', 50),
            (2, 'electronics', 800),
            (2, 'clothing', 150),
            (3, 'electronics', 1500),
            (3, 'books', 75)
            """
            client.execute_statement(database_id, insert_sql)
            
            print("\n🔄 Integration Pattern:")
            print(f"\n   1️⃣  DuckDB: SELECT and FILTER data (SQL strength)")
            
            sql = """
            SELECT
                user_id,
                category,
                SUM(amount) as total_amount
            FROM transactions
            WHERE category = 'electronics'
            GROUP BY user_id, category
            """
            
            result = client.execute_query(database_id, sql)
            print(f"      DuckDB selected {len(result)} electronics purchases")
            
            print(f"\n   2️⃣  Polars: COMPUTE and TRANSFORM (DataFrame strength)")
            print(f"      # In production, pass result to Polars:")
            print(f"      import polars as pl")
            print(f"      df = pl.DataFrame(result)")
            print(f"      df = df.with_columns([")
            print(f"          (pl.col('total_amount') * 0.1).alias('commission'),")
            print(f"          (pl.col('total_amount') * 1.08).alias('with_tax')")
            print(f"      ])")
            
            # Simulate Polars computation
            for row in result:
                row['commission'] = row['total_amount'] * 0.1
                row['with_tax'] = row['total_amount'] * 1.08
            
            print(f"\n   📊 Results after Polars computation:")
            for row in result:
                print(f"      User {row['user_id']}: ${row['total_amount']:.2f} " +
                      f"(commission: ${row['commission']:.2f}, with tax: ${row['with_tax']:.2f})")
            
            print(f"\n💡 Best of both worlds:")
            print(f"   - DuckDB: SQL queries, filtering, aggregation")
            print(f"   - Polars: DataFrame operations, transformations, ML features")
            
        finally:
            client.delete_database(database_id, delete_from_minio=True, force=True)


def example_12_data_warehouse_pattern(host='localhost', port=50052):
    """
    Example 12: Data Warehouse Pattern
    
    Build a simple data warehouse with fact and dimension tables.
    File: duckdb_client.py, Multiple methods
    """
    print("\n" + "=" * 80)
    print("Example 12: Data Warehouse Pattern (Star Schema)")
    print("=" * 80)
    
    with DuckDBClient(host=host, port=port, user_id='example_user') as client:
        db_info = client.create_database('warehouse_demo', minio_bucket='duckdb-data')
        database_id = db_info['database_id']
        
        try:
            print("\n⭐ Building star schema...")
            
            # Dimension table: Products
            print(f"\n   Creating dimension: products")
            product_schema = {'product_id': 'INTEGER', 'product_name': 'VARCHAR', 'category': 'VARCHAR'}
            client.create_table(database_id, 'dim_products', product_schema)
            client.execute_statement(database_id, """
                INSERT INTO dim_products VALUES
                (1, 'Laptop Pro', 'Electronics'),
                (2, 'Wireless Mouse', 'Electronics'),
                (3, 'Office Chair', 'Furniture')
            """)
            
            # Fact table: Sales
            print(f"   Creating fact table: sales")
            sales_schema = {
                'sale_id': 'INTEGER',
                'product_id': 'INTEGER',
                'quantity': 'INTEGER',
                'amount': 'DOUBLE',
                'sale_date': 'DATE'
            }
            client.create_table(database_id, 'fact_sales', sales_schema)
            client.execute_statement(database_id, """
                INSERT INTO fact_sales VALUES
                (1, 1, 2, 2400, '2024-01-01'),
                (2, 2, 5, 150, '2024-01-01'),
                (3, 1, 1, 1200, '2024-01-02'),
                (4, 3, 3, 900, '2024-01-02'),
                (5, 2, 10, 300, '2024-01-03')
            """)
            
            # Analytical query joining dimension and fact
            print(f"\n📊 Running analytical query (star schema join)...")
            sql = """
            SELECT
                p.category,
                p.product_name,
                SUM(s.quantity) as units_sold,
                SUM(s.amount) as revenue
            FROM fact_sales s
            JOIN dim_products p ON s.product_id = p.product_id
            GROUP BY p.category, p.product_name
            ORDER BY revenue DESC
            """
            
            result = client.execute_query(database_id, sql)
            print(f"\n   Sales by product:")
            for row in result:
                print(f"      [{row['category']}] {row['product_name']}: " +
                      f"{row['units_sold']} units, ${row['revenue']:.2f}")
            
            print(f"\n💡 Data warehouse pattern:")
            print(f"   - Dimension tables: Reference data (products, customers)")
            print(f"   - Fact tables: Transactional data (sales, orders)")
            print(f"   - DuckDB: Fast OLAP queries on star schema")
            
        finally:
            client.delete_database(database_id, delete_from_minio=True, force=True)


def example_13_time_series_analytics(host='localhost', port=50052):
    """
    Example 13: Time Series Analytics
    
    Analyze time-series data with window functions and date operations.
    File: duckdb_client.py, Method: execute_query()
    """
    print("\n" + "=" * 80)
    print("Example 13: Time Series Analytics")
    print("=" * 80)
    
    with DuckDBClient(host=host, port=port, user_id='example_user') as client:
        db_info = client.create_database('timeseries_demo', minio_bucket='duckdb-data')
        database_id = db_info['database_id']
        
        try:
            # Create time series data
            schema = {'timestamp': 'TIMESTAMP', 'metric': 'VARCHAR', 'value': 'DOUBLE'}
            client.create_table(database_id, 'metrics', schema)
            
            insert_sql = """
            INSERT INTO metrics VALUES
            ('2024-01-01 00:00:00', 'cpu_usage', 45.2),
            ('2024-01-01 01:00:00', 'cpu_usage', 52.1),
            ('2024-01-01 02:00:00', 'cpu_usage', 48.7),
            ('2024-01-01 03:00:00', 'cpu_usage', 55.3),
            ('2024-01-01 04:00:00', 'cpu_usage', 62.8),
            ('2024-01-01 00:00:00', 'memory_usage', 70.5),
            ('2024-01-01 01:00:00', 'memory_usage', 72.3),
            ('2024-01-01 02:00:00', 'memory_usage', 71.8),
            ('2024-01-01 03:00:00', 'memory_usage', 75.1),
            ('2024-01-01 04:00:00', 'memory_usage', 78.9)
            """
            client.execute_statement(database_id, insert_sql)
            
            print("\n📈 Time series query: Moving average and trend")
            sql = """
            SELECT
                metric,
                timestamp,
                value,
                AVG(value) OVER (
                    PARTITION BY metric
                    ORDER BY timestamp
                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                ) as moving_avg_3hr,
                value - LAG(value) OVER (
                    PARTITION BY metric
                    ORDER BY timestamp
                ) as change_from_prev
            FROM metrics
            ORDER BY metric, timestamp
            """
            
            result = client.execute_query(database_id, sql)
            
            current_metric = None
            for row in result:
                if row['metric'] != current_metric:
                    current_metric = row['metric']
                    print(f"\n   {current_metric}:")
                
                ts = row['timestamp'].strftime('%H:%M') if hasattr(row['timestamp'], 'strftime') else str(row['timestamp'])
                change = f"+{row['change_from_prev']:.1f}" if row['change_from_prev'] and row['change_from_prev'] > 0 else str(row['change_from_prev']) if row['change_from_prev'] else "N/A"
                print(f"      {ts}: {row['value']:.1f}% (MA: {row['moving_avg_3hr']:.1f}%, Change: {change})")
            
            print(f"\n💡 Time series features:")
            print(f"   - Moving averages (sliding window)")
            print(f"   - Lag/Lead for trend analysis")
            print(f"   - Date/time functions")
            
        finally:
            client.delete_database(database_id, delete_from_minio=True, force=True)


def example_14_data_pipeline(host='localhost', port=50052):
    """
    Example 14: Complete Data Pipeline
    
    End-to-end: MinIO → DuckDB → Compute → MinIO
    File: duckdb_client.py, Multiple methods
    """
    print("\n" + "=" * 80)
    print("Example 14: Complete Data Pipeline (Cold → Hot → Compute → Cold)")
    print("=" * 80)
    
    with DuckDBClient(host=host, port=port, user_id='example_user') as duckdb, \
         MinIOClient(host='localhost', port=50051, user_id='example_user') as minio:
        
        db_info = duckdb.create_database('pipeline_demo', minio_bucket='duckdb-data')
        database_id = db_info['database_id']
        
        try:
            print("\n🔄 Data Pipeline:")
            
            # Step 1: Cold storage (MinIO)
            print(f"\n   1️⃣  INGEST: Raw data → MinIO cold storage")
            
            if not minio.bucket_exists('duckdb-data'):
                minio.create_bucket('duckdb-data')
            
            raw_data = """date,region,product,revenue
2024-01-01,US,Widget,1500
2024-01-01,EU,Widget,1200
2024-01-01,US,Gadget,2000
2024-01-02,EU,Widget,1300
2024-01-02,US,Gadget,2200
"""
            
            import io
            minio.put_object('duckdb-data', 'raw/sales.csv', io.BytesIO(raw_data.encode()), len(raw_data.encode()))
            print(f"      ✅ Raw data stored in MinIO")
            
            # Step 2: Import to hot storage (DuckDB)
            print(f"\n   2️⃣  LOAD: MinIO → DuckDB hot storage")
            duckdb.import_from_minio(database_id, 'raw_sales', 'duckdb-data', 'raw/sales.csv', file_format='csv')
            print(f"      ✅ Data loaded into DuckDB")
            
            # Step 3: Transform & Compute
            print(f"\n   3️⃣  TRANSFORM: Compute aggregations")
            transform_sql = """
            SELECT
                region,
                product,
                SUM(revenue) as total_revenue,
                COUNT(*) as num_sales,
                AVG(revenue) as avg_revenue
            FROM raw_sales
            GROUP BY region, product
            ORDER BY total_revenue DESC
            """
            
            results = duckdb.execute_query(database_id, transform_sql)
            print(f"      ✅ Computed {len(results)} aggregations")
            
            # Step 4: Export results
            print(f"\n   4️⃣  EXPORT: Results → MinIO cold storage (Parquet)")
            export_result = duckdb.export_to_minio(
                database_id,
                transform_sql,
                'duckdb-data',
                'processed/sales_summary.parquet',
                file_format='parquet',
                overwrite=True
            )
            print(f"      ✅ Exported {export_result['rows_exported']} rows to MinIO")
            
            # Verify
            print(f"\n   ✅ Pipeline complete!")
            print(f"\n   📊 Final results:")
            for row in results:
                # Convert to float in case CSV import returns strings
                total_revenue = float(row['total_revenue']) if isinstance(row['total_revenue'], str) else row['total_revenue']
                num_sales = int(row['num_sales']) if isinstance(row['num_sales'], str) else row['num_sales']
                print(f"      {row['region']} - {row['product']}: ${total_revenue:.2f} " +
                      f"({num_sales} sales)")
            
            print(f"\n💡 Data pipeline pattern:")
            print(f"   MinIO (raw) → DuckDB (hot) → Compute → MinIO (processed)")
            
        finally:
            duckdb.delete_database(database_id, delete_from_minio=True, force=True)


def example_15_performance_tips(host='localhost', port=50052):
    """
    Example 15: Performance Tips and Best Practices
    
    Demonstrate DuckDB performance optimization techniques.
    File: duckdb_client.py, Multiple methods
    """
    print("\n" + "=" * 80)
    print("Example 15: Performance Tips and Best Practices")
    print("=" * 80)
    
    print("\n💡 DuckDB Performance Best Practices:\n")
    
    print("1️⃣  **Use Parquet for Cold Storage**")
    print("   ✅ Columnar format → faster analytics")
    print("   ✅ Compression → smaller file sizes")
    print("   ✅ DuckDB native support → zero-copy reads\n")
    
    print("2️⃣  **Keep Hot Data Small**")
    print("   ✅ Only frequently accessed data in DuckDB")
    print("   ✅ Archive old data to MinIO Parquet")
    print("   ✅ Use time-based partitioning\n")
    
    print("3️⃣  **Leverage Zero-Copy Analytics**")
    print("   ✅ Query MinIO files directly when possible")
    print("   ✅ No import overhead")
    print("   ✅ Use query_minio_file() for ad-hoc queries\n")
    
    print("4️⃣  **Batch Operations**")
    print("   ✅ Use execute_batch() for multiple statements")
    print("   ✅ Enable transactions for atomicity")
    print("   ✅ Bulk inserts instead of row-by-row\n")
    
    print("5️⃣  **Optimize Queries**")
    print("   ✅ SELECT only needed columns")
    print("   ✅ Use WHERE clauses to filter early")
    print("   ✅ Leverage CTEs for readable complex queries")
    print("   ✅ Use appropriate data types\n")
    
    print("6️⃣  **Data Flow Architecture**")
    print("   ✅ Raw data → MinIO (cold)")
    print("   ✅ Active analysis → DuckDB (hot)")
    print("   ✅ Computed results → MinIO (cold)")
    print("   ✅ Temporary computations → Polars (in-memory)\n")
    
    print("7️⃣  **Cleanup Hot Data**")
    print("   ✅ Drop tables after use")
    print("   ✅ Export results before cleanup")
    print("   ✅ Use delete_database() with force=True\n")
    
    print("8️⃣  **DuckDB vs Traditional Databases**")
    print("   ❌ Not for: OLTP, concurrent writes, real-time updates")
    print("   ✅ Perfect for: OLAP, analytics, batch processing")
    print("   ✅ Complements: Use with PostgreSQL/MySQL for OLTP\n")


def run_all_examples(host='localhost', port=50052):
    """Run all examples in sequence"""
    print("\n" + "=" * 80)
    print("  DuckDB Client Usage Examples")
    print("  Hot Data + Cold Storage Architecture")
    print("=" * 80)
    print(f"\nConnecting to DuckDB: {host}:{port}")
    print(f"Connecting to MinIO: {host}:50051")
    print(f"Timestamp: {datetime.now()}\n")
    
    examples = [
        example_01_health_check,
        example_02_database_management,
        example_03_table_operations,
        example_04_query_operations,
        example_05_batch_operations,
        example_06_import_from_minio,
        example_07_query_minio_direct,
        example_08_export_to_minio,
        example_09_advanced_analytics,
        example_10_hot_data_lifecycle,
        example_11_polars_duckdb_pattern,
        example_12_data_warehouse_pattern,
        example_13_time_series_analytics,
        example_14_data_pipeline,
        example_15_performance_tips,
    ]
    
    for i, example in enumerate(examples, 1):
        try:
            example(host, port)
        except Exception as e:
            print(f"\n❌ Example {i} failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("  All Examples Completed!")
    print("=" * 80)
    print("\nArchitecture Summary:")
    print("  ❄️  MinIO: Cold storage (Parquet files)")
    print("  🔥 DuckDB: Hot storage (fast analytics)")
    print("  ⚡ Zero-copy: Query MinIO directly")
    print("  🔄 Data flow: Cold → Hot → Compute → Cold")
    print("\nFor more information:")
    print("  - Client: isA_common/isa_common/duckdb_client.py")
    print("  - Proto: api/proto/duckdb_service.proto")
    print("  - Tests: isA_common/tests/duck/test_duckdb_functional.sh")
    print()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='DuckDB Client Usage Examples',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--host', default=None,
                       help='DuckDB gRPC service host (optional, uses Consul discovery if not provided)')
    parser.add_argument('--port', type=int, default=None,
                       help='DuckDB gRPC service port (optional, uses Consul discovery if not provided)')
    parser.add_argument('--consul-host', default='localhost',
                       help='Consul host (default: localhost)')
    parser.add_argument('--consul-port', type=int, default=8500,
                       help='Consul port (default: 8500)')
    parser.add_argument('--use-consul', action='store_true',
                       help='Use Consul for service discovery')
    parser.add_argument('--example', type=int, choices=range(1, 16),
                       help='Run specific example (1-15, default: all)')

    args = parser.parse_args()

    # Default: Try Consul first, fallback to localhost
    host = args.host
    port = args.port

    if host is None or port is None:
        if not args.use_consul:
            try:
                print(f"🔍 Attempting Consul discovery from {args.consul_host}:{args.consul_port}...")
                consul = ConsulRegistry(consul_host=args.consul_host, consul_port=args.consul_port)
                url = consul.get_duckdb_url()

                if '://' in url:
                    url = url.split('://', 1)[1]
                discovered_host, port_str = url.rsplit(':', 1)
                discovered_port = int(port_str)

                host = host or discovered_host
                port = port or discovered_port
                print(f"✅ Discovered from Consul: {host}:{port}")
            except Exception as e:
                print(f"⚠️  Consul discovery failed: {e}")
                print(f"📍 Falling back to localhost...")

        # Fallback to defaults
        host = host or 'localhost'
        port = port or 50052

    print(f"🔗 Connecting to DuckDB at {host}:{port}\n")

    if args.example:
        # Run specific example
        examples_map = {
            1: example_01_health_check,
            2: example_02_database_management,
            3: example_03_table_operations,
            4: example_04_query_operations,
            5: example_05_batch_operations,
            6: example_06_import_from_minio,
            7: example_07_query_minio_direct,
            8: example_08_export_to_minio,
            9: example_09_advanced_analytics,
            10: example_10_hot_data_lifecycle,
            11: example_11_polars_duckdb_pattern,
            12: example_12_data_warehouse_pattern,
            13: example_13_time_series_analytics,
            14: example_14_data_pipeline,
            15: example_15_performance_tips,
        }
        examples_map[args.example](host=args.host, port=args.port)
    else:
        # Run all examples
        run_all_examples(host=args.host, port=args.port)


if __name__ == '__main__':
    main()
