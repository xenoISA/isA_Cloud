#!/usr/bin/env python3
"""
Async DuckDB Native Client
High-performance async DuckDB client for analytical workloads.

This client uses DuckDB's native Python API with async wrappers,
providing full support for analytical SQL operations including:
- SQL query execution
- Parquet/CSV file operations
- In-memory analytics
- Table management
- Data export
"""

import os
import asyncio
from typing import List, Dict, Optional, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import duckdb

from .async_base_client import AsyncBaseClient


class AsyncDuckDBClient(AsyncBaseClient):
    """
    Async DuckDB client using native duckdb driver.

    Provides async wrapper around DuckDB for high-performance analytical queries.
    Uses a thread pool executor for non-blocking operations.
    """

    # Class-level configuration
    SERVICE_NAME = "DuckDB"
    DEFAULT_HOST = ""  # File-based, not network
    DEFAULT_PORT = 0
    ENV_PREFIX = "DUCKDB"
    TENANT_SEPARATOR = "_"  # user_table

    def __init__(
        self,
        database: Optional[str] = None,
        read_only: bool = False,
        max_workers: int = 4,
        **kwargs
    ):
        """
        Initialize async DuckDB client with native driver.

        Args:
            database: Database file path (default: in-memory ':memory:')
            read_only: Open database in read-only mode (default: False)
            max_workers: Thread pool size (default: 4)
            **kwargs: Base client args (user_id, organization_id, lazy_connect)
        """
        super().__init__(**kwargs)

        self._database = database or os.getenv('DUCKDB_DATABASE', ':memory:')
        self._read_only = read_only
        self._max_workers = max_workers

        self._conn: Optional[duckdb.DuckDBPyConnection] = None
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def _get_schema_prefix(self) -> str:
        """Get schema prefix for multi-tenant isolation (DuckDB uses '_' separator)."""
        return f"{self.user_id}_"

    def _prefix_table(self, table: str) -> str:
        """Add prefix to table name for isolation."""
        prefix = self._get_schema_prefix()
        if table.startswith(prefix):
            return table
        return f"{prefix}{table}"

    async def _connect(self) -> None:
        """Establish DuckDB connection."""
        self._conn = duckdb.connect(
            self._database,
            read_only=self._read_only
        )
        self._logger.info(f"Connected to DuckDB: {self._database}")

    async def _disconnect(self) -> None:
        """Close DuckDB connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._executor.shutdown(wait=False)

    async def _run_in_executor(self, func, *args, **kwargs):
        """Run blocking DuckDB operation in thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: func(*args, **kwargs)
        )

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self, detailed: bool = True) -> Optional[Dict]:
        """Check DuckDB service health."""
        try:
            await self._ensure_connected()

            def _check():
                result = self._conn.execute("SELECT 1 as check").fetchone()
                version = self._conn.execute("SELECT version()").fetchone()[0]
                return result, version

            result, version = await self._run_in_executor(_check)

            return {
                'healthy': True,
                'version': version,
                'database': self._database
            }

        except Exception as e:
            return self.handle_error(e, "health check")

    # ============================================
    # Query Operations
    # ============================================

    async def query(self, sql: str, params: Optional[List[Any]] = None) -> Optional[List[Dict]]:
        """Execute SELECT query.

        Args:
            sql: SQL query statement
            params: Query parameters

        Returns:
            List of result rows as dictionaries
        """
        try:
            await self._ensure_connected()

            def _query():
                if params:
                    result = self._conn.execute(sql, params)
                else:
                    result = self._conn.execute(sql)

                columns = [desc[0] for desc in result.description]
                rows = result.fetchall()
                return [dict(zip(columns, row)) for row in rows]

            return await self._run_in_executor(_query)

        except Exception as e:
            return self.handle_error(e, "query")

    async def execute_query(self, db_name: str, sql: str, limit: int = 100,
                           auto_qualify_tables: bool = True) -> List[Dict]:
        """Execute SQL query (compatibility method).

        Args:
            db_name: Database name (ignored for native client)
            sql: SQL query statement
            limit: Maximum rows to return
            auto_qualify_tables: Auto-qualify table names

        Returns:
            List of result rows as dictionaries
        """
        if limit > 0 and 'LIMIT' not in sql.upper():
            sql = f"{sql} LIMIT {limit}"
        result = await self.query(sql)
        return result or []

    async def query_row(self, sql: str, params: Optional[List[Any]] = None) -> Optional[Dict]:
        """Execute single row query.

        Args:
            sql: SQL query statement
            params: Query parameters

        Returns:
            Single row as dictionary or None
        """
        try:
            await self._ensure_connected()

            def _query_row():
                if params:
                    result = self._conn.execute(sql, params)
                else:
                    result = self._conn.execute(sql)

                columns = [desc[0] for desc in result.description]
                row = result.fetchone()
                if row:
                    return dict(zip(columns, row))
                return None

            return await self._run_in_executor(_query_row)

        except Exception as e:
            return self.handle_error(e, "query row")

    async def execute(self, sql: str, params: Optional[List[Any]] = None) -> Optional[int]:
        """Execute INSERT/UPDATE/DELETE statement.

        Args:
            sql: SQL statement
            params: Statement parameters

        Returns:
            Number of rows affected (estimated)
        """
        try:
            await self._ensure_connected()

            def _execute():
                if params:
                    self._conn.execute(sql, params)
                else:
                    self._conn.execute(sql)
                # DuckDB doesn't return row count directly
                return 0

            return await self._run_in_executor(_execute)

        except Exception as e:
            return self.handle_error(e, "execute")

    async def execute_statement(self, db_name: str, sql: str,
                               auto_qualify_tables: bool = True) -> int:
        """Execute write operation (compatibility method).

        Args:
            db_name: Database name (ignored)
            sql: SQL statement
            auto_qualify_tables: Auto-qualify table names

        Returns:
            Number of rows affected
        """
        result = await self.execute(sql)
        return result or 0

    async def execute_batch(self, operations: List[Dict[str, Any]]) -> Optional[Dict]:
        """Execute batch operations.

        Args:
            operations: List of {'sql': str, 'params': List} dictionaries

        Returns:
            Batch execution results
        """
        try:
            await self._ensure_connected()

            def _execute_batch():
                results = []
                for op in operations:
                    sql = op.get('sql', '')
                    params = op.get('params', [])

                    try:
                        if params:
                            self._conn.execute(sql, params)
                        else:
                            self._conn.execute(sql)
                        results.append({'success': True, 'error': ''})
                    except Exception as e:
                        results.append({'success': False, 'error': str(e)})

                return results

            results = await self._run_in_executor(_execute_batch)

            return {
                'total_operations': len(operations),
                'successful': len([r for r in results if r['success']]),
                'results': results
            }

        except Exception as e:
            return self.handle_error(e, "execute batch")

    # ============================================
    # Table Operations
    # ============================================

    async def list_tables(self, db_name: str = '') -> List[str]:
        """List all tables in database.

        Args:
            db_name: Database name (ignored for native client)

        Returns:
            List of table names
        """
        try:
            await self._ensure_connected()

            def _list_tables():
                result = self._conn.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
                )
                return [row[0] for row in result.fetchall()]

            return await self._run_in_executor(_list_tables)

        except Exception as e:
            self.handle_error(e, "list tables")
            return []

    async def table_exists(self, table: str) -> bool:
        """Check if table exists.

        Args:
            table: Table name

        Returns:
            True if table exists, False otherwise
        """
        try:
            await self._ensure_connected()

            def _table_exists():
                result = self._conn.execute(
                    f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table}'"
                )
                return result.fetchone()[0] > 0

            return await self._run_in_executor(_table_exists)

        except Exception as e:
            self.handle_error(e, "table exists check")
            return False

    async def create_table(self, db_name: str, table_name: str,
                          schema: Dict[str, str]) -> bool:
        """Create table with schema.

        Args:
            db_name: Database name (ignored)
            table_name: Table name
            schema: Column definitions {'column_name': 'TYPE'}

        Returns:
            True if successful
        """
        try:
            await self._ensure_connected()

            def _create_table():
                columns = ', '.join([f"{col} {dtype}" for col, dtype in schema.items()])
                self._conn.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})")
                return True

            return await self._run_in_executor(_create_table)

        except Exception as e:
            self.handle_error(e, "create table")
            return False

    async def drop_table(self, db_name: str, table_name: str,
                        if_exists: bool = True, cascade: bool = False) -> bool:
        """Drop table.

        Args:
            db_name: Database name (ignored)
            table_name: Table name
            if_exists: Use IF EXISTS clause
            cascade: Use CASCADE clause

        Returns:
            True if successful
        """
        try:
            await self._ensure_connected()

            def _drop_table():
                if_clause = "IF EXISTS " if if_exists else ""
                cascade_clause = " CASCADE" if cascade else ""
                self._conn.execute(f"DROP TABLE {if_clause}{table_name}{cascade_clause}")
                return True

            return await self._run_in_executor(_drop_table)

        except Exception as e:
            self.handle_error(e, "drop table")
            return False

    async def get_table_schema(self, db_name: str, table_name: str) -> Optional[Dict]:
        """Get table schema.

        Args:
            db_name: Database name (ignored)
            table_name: Table name

        Returns:
            Schema dictionary with column info
        """
        try:
            await self._ensure_connected()

            def _get_schema():
                result = self._conn.execute(f"DESCRIBE {table_name}")
                columns = []
                for row in result.fetchall():
                    columns.append({
                        'name': row[0],
                        'data_type': row[1],
                        'nullable': row[2] == 'YES' if len(row) > 2 else True
                    })
                return {'table_name': table_name, 'columns': columns}

            return await self._run_in_executor(_get_schema)

        except Exception as e:
            return self.handle_error(e, "get table schema")

    async def get_table_stats(self, db_name: str, table_name: str,
                             include_columns: bool = True) -> Optional[Dict]:
        """Get table statistics.

        Args:
            db_name: Database name (ignored)
            table_name: Table name
            include_columns: Include column statistics

        Returns:
            Statistics dictionary
        """
        try:
            await self._ensure_connected()

            def _get_stats():
                # Get row count
                count_result = self._conn.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = count_result.fetchone()[0]

                stats = {
                    'table_name': table_name,
                    'row_count': row_count,
                    'size_bytes': 0,  # DuckDB doesn't expose this directly
                    'column_stats': []
                }

                if include_columns:
                    # Get column info
                    desc_result = self._conn.execute(f"DESCRIBE {table_name}")
                    for row in desc_result.fetchall():
                        col_name = row[0]
                        # Get distinct count
                        distinct_result = self._conn.execute(
                            f"SELECT COUNT(DISTINCT {col_name}) FROM {table_name}"
                        )
                        distinct_count = distinct_result.fetchone()[0]

                        # Get null count
                        null_result = self._conn.execute(
                            f"SELECT COUNT(*) FROM {table_name} WHERE {col_name} IS NULL"
                        )
                        null_count = null_result.fetchone()[0]

                        stats['column_stats'].append({
                            'column_name': col_name,
                            'distinct_count': distinct_count,
                            'null_count': null_count
                        })

                return stats

            return await self._run_in_executor(_get_stats)

        except Exception as e:
            return self.handle_error(e, "get table stats")

    # ============================================
    # File Operations
    # ============================================

    async def read_parquet(self, file_path: str, table_name: Optional[str] = None) -> Optional[List[Dict]]:
        """Read Parquet file.

        Args:
            file_path: Path to Parquet file
            table_name: Optional table name to create

        Returns:
            List of rows as dictionaries
        """
        try:
            await self._ensure_connected()

            def _read_parquet():
                if table_name:
                    self._conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet('{file_path}')")
                    return []
                else:
                    result = self._conn.execute(f"SELECT * FROM read_parquet('{file_path}')")
                    columns = [desc[0] for desc in result.description]
                    rows = result.fetchall()
                    return [dict(zip(columns, row)) for row in rows]

            return await self._run_in_executor(_read_parquet)

        except Exception as e:
            return self.handle_error(e, "read parquet")

    async def read_csv(self, file_path: str, table_name: Optional[str] = None,
                      header: bool = True, delimiter: str = ',') -> Optional[List[Dict]]:
        """Read CSV file.

        Args:
            file_path: Path to CSV file
            table_name: Optional table name to create
            header: CSV has header row
            delimiter: Column delimiter

        Returns:
            List of rows as dictionaries
        """
        try:
            await self._ensure_connected()

            def _read_csv():
                opts = f"header={header}, delim='{delimiter}'"
                if table_name:
                    self._conn.execute(
                        f"CREATE TABLE {table_name} AS SELECT * FROM read_csv('{file_path}', {opts})"
                    )
                    return []
                else:
                    result = self._conn.execute(f"SELECT * FROM read_csv('{file_path}', {opts})")
                    columns = [desc[0] for desc in result.description]
                    rows = result.fetchall()
                    return [dict(zip(columns, row)) for row in rows]

            return await self._run_in_executor(_read_csv)

        except Exception as e:
            return self.handle_error(e, "read csv")

    async def write_parquet(self, table_or_query: str, file_path: str) -> Optional[bool]:
        """Write table or query result to Parquet file.

        Args:
            table_or_query: Table name or SELECT query
            file_path: Output Parquet file path

        Returns:
            True if successful
        """
        try:
            await self._ensure_connected()

            def _write_parquet():
                if table_or_query.upper().startswith('SELECT'):
                    self._conn.execute(f"COPY ({table_or_query}) TO '{file_path}' (FORMAT PARQUET)")
                else:
                    self._conn.execute(f"COPY {table_or_query} TO '{file_path}' (FORMAT PARQUET)")
                return True

            return await self._run_in_executor(_write_parquet)

        except Exception as e:
            return self.handle_error(e, "write parquet")

    async def write_csv(self, table_or_query: str, file_path: str,
                       header: bool = True, delimiter: str = ',') -> Optional[bool]:
        """Write table or query result to CSV file.

        Args:
            table_or_query: Table name or SELECT query
            file_path: Output CSV file path
            header: Include header row
            delimiter: Column delimiter

        Returns:
            True if successful
        """
        try:
            await self._ensure_connected()

            def _write_csv():
                opts = f"FORMAT CSV, HEADER {header}, DELIMITER '{delimiter}'"
                if table_or_query.upper().startswith('SELECT'):
                    self._conn.execute(f"COPY ({table_or_query}) TO '{file_path}' ({opts})")
                else:
                    self._conn.execute(f"COPY {table_or_query} TO '{file_path}' ({opts})")
                return True

            return await self._run_in_executor(_write_csv)

        except Exception as e:
            return self.handle_error(e, "write csv")

    # ============================================
    # Bulk Insert Operations
    # ============================================

    async def insert_many(self, table: str, rows: List[Dict]) -> Optional[int]:
        """Insert multiple rows.

        Args:
            table: Table name
            rows: List of row dictionaries

        Returns:
            Number of rows inserted
        """
        try:
            if not rows:
                return 0

            await self._ensure_connected()

            def _insert_many():
                columns = list(rows[0].keys())
                cols_str = ', '.join(columns)
                placeholders = ', '.join(['?' for _ in columns])

                count = 0
                for row in rows:
                    values = [row.get(col) for col in columns]
                    self._conn.execute(
                        f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})",
                        values
                    )
                    count += 1
                return count

            return await self._run_in_executor(_insert_many)

        except Exception as e:
            return self.handle_error(e, "insert many")

    # ============================================
    # Analytics Operations
    # ============================================

    async def aggregate(self, table: str, aggregations: List[Dict],
                       group_by: Optional[List[str]] = None,
                       where: Optional[str] = None) -> Optional[List[Dict]]:
        """Perform aggregation query.

        Args:
            table: Table name
            aggregations: List of {'function': 'SUM/AVG/COUNT/...', 'column': 'col', 'alias': 'name'}
            group_by: Group by columns
            where: WHERE clause condition

        Returns:
            Aggregation results
        """
        try:
            await self._ensure_connected()

            def _aggregate():
                # Build aggregation expressions
                agg_exprs = []
                for agg in aggregations:
                    func = agg.get('function', 'COUNT').upper()
                    col = agg.get('column', '*')
                    alias = agg.get('alias', f"{func}_{col}")
                    agg_exprs.append(f"{func}({col}) AS {alias}")

                agg_str = ', '.join(agg_exprs)

                # Build SQL
                sql = f"SELECT {agg_str}"
                if group_by:
                    sql = f"SELECT {', '.join(group_by)}, {agg_str}"

                sql += f" FROM {table}"

                if where:
                    sql += f" WHERE {where}"

                if group_by:
                    sql += f" GROUP BY {', '.join(group_by)}"

                result = self._conn.execute(sql)
                columns = [desc[0] for desc in result.description]
                rows = result.fetchall()
                return [dict(zip(columns, row)) for row in rows]

            return await self._run_in_executor(_aggregate)

        except Exception as e:
            return self.handle_error(e, "aggregate")

    async def count(self, table: str, where: Optional[str] = None) -> Optional[int]:
        """Count rows in table.

        Args:
            table: Table name
            where: Optional WHERE condition

        Returns:
            Row count
        """
        try:
            await self._ensure_connected()

            def _count():
                sql = f"SELECT COUNT(*) FROM {table}"
                if where:
                    sql += f" WHERE {where}"
                result = self._conn.execute(sql)
                return result.fetchone()[0]

            return await self._run_in_executor(_count)

        except Exception as e:
            return self.handle_error(e, "count")

    # ============================================
    # Statistics
    # ============================================

    async def get_statistics(self) -> Optional[Dict]:
        """Get database statistics.

        Returns:
            Statistics dictionary
        """
        try:
            await self._ensure_connected()

            def _get_stats():
                # Get table count
                result = self._conn.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
                )
                table_count = result.fetchone()[0]

                return {
                    'database': self._database,
                    'table_count': table_count,
                    'is_memory': self._database == ':memory:'
                }

            return await self._run_in_executor(_get_stats)

        except Exception as e:
            return self.handle_error(e, "get statistics")

    # ============================================
    # Concurrent Operations
    # ============================================

    async def query_many_concurrent(self, queries: List[str]) -> List[Optional[List[Dict]]]:
        """Execute multiple queries concurrently.

        Args:
            queries: List of SQL queries

        Returns:
            List of results for each query
        """
        tasks = [self.query(q) for q in queries]
        return await asyncio.gather(*tasks)

    async def execute_queries_concurrent(self, db_name: str,
                                        queries: List[str]) -> List[List[Dict]]:
        """Execute multiple queries concurrently (compatibility method).

        Args:
            db_name: Database name (ignored)
            queries: List of SQL queries

        Returns:
            List of results for each query
        """
        results = await self.query_many_concurrent(queries)
        return [r or [] for r in results]


# Example usage
if __name__ == '__main__':
    async def main():
        async with AsyncDuckDBClient(
            database=':memory:',
            user_id='test_user'
        ) as client:
            # Health check
            health = await client.health_check()
            print(f"Health: {health}")

            # Create table
            await client.create_table('', 'test_table', {
                'id': 'INTEGER',
                'name': 'VARCHAR',
                'value': 'DOUBLE'
            })

            # Insert data
            await client.insert_many('test_table', [
                {'id': 1, 'name': 'test1', 'value': 10.5},
                {'id': 2, 'name': 'test2', 'value': 20.5},
                {'id': 3, 'name': 'test3', 'value': 30.5},
            ])

            # Query
            results = await client.query("SELECT * FROM test_table")
            print(f"Query results: {results}")

            # Aggregate
            agg = await client.aggregate('test_table', [
                {'function': 'SUM', 'column': 'value', 'alias': 'total'},
                {'function': 'AVG', 'column': 'value', 'alias': 'average'}
            ])
            print(f"Aggregation: {agg}")

            # List tables
            tables = await client.list_tables()
            print(f"Tables: {tables}")

            # Stats
            stats = await client.get_statistics()
            print(f"Stats: {stats}")

    asyncio.run(main())
