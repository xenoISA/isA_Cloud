#!/usr/bin/env python3
"""
Async SQLite Native Client
Local alternative to AsyncPostgresClient for ICP (Intelligent Personal Context) mode.

This client provides the same interface as AsyncPostgresClient but uses SQLite,
making it suitable for local desktop usage without requiring PostgreSQL.

Key differences from PostgreSQL:
- Uses ? placeholders instead of $1, $2 (auto-converted)
- JSONB stored as TEXT (JSON strings)
- TEXT[] arrays stored as JSON arrays
- ILIKE converted to LIKE with COLLATE NOCASE
- No connection pooling (SQLite handles this differently)
"""

import os
import re
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Any

import aiosqlite

from .async_base_client import AsyncBaseClient


def _convert_pg_placeholders(sql: str) -> str:
    """Convert PostgreSQL $1, $2 placeholders to SQLite ? placeholders."""
    # Replace $N with ? while preserving order
    return re.sub(r'\$\d+', '?', sql)


def _convert_pg_syntax(sql: str) -> str:
    """Convert PostgreSQL-specific syntax to SQLite equivalents."""
    result = sql

    # Convert ILIKE to LIKE (SQLite uses COLLATE NOCASE for case-insensitive)
    result = re.sub(r'\bILIKE\b', 'LIKE', result, flags=re.IGNORECASE)

    # Convert PostgreSQL array overlap operator && to a custom check
    # This is complex - for now we'll handle it in query logic

    # Convert JSONB operators (basic support)
    # PostgreSQL: data->>'key' or data->'key'
    # SQLite: json_extract(data, '$.key')

    # Convert ON CONFLICT DO UPDATE to INSERT OR REPLACE
    # This is simplified - full upsert logic may need custom handling

    # Convert RETURNING * (SQLite doesn't support this directly)
    # We'll handle this in the insert_into method

    return result


def _serialize_value(value: Any) -> Any:
    """Serialize Python objects for SQLite storage."""
    if isinstance(value, dict):
        return json.dumps(value)
    elif isinstance(value, list):
        return json.dumps(value)
    return value


def _deserialize_row(row: aiosqlite.Row, description: List) -> Dict:
    """Convert SQLite row to dictionary with JSON deserialization."""
    result = {}
    for i, col in enumerate(description):
        col_name = col[0]
        value = row[i]

        # Try to deserialize JSON strings
        if isinstance(value, str):
            try:
                if value.startswith('{') or value.startswith('['):
                    value = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                pass

        result[col_name] = value

    return result


class AsyncSQLiteClient(AsyncBaseClient):
    """
    Async SQLite client - drop-in replacement for AsyncPostgresClient.

    Provides the same interface as AsyncPostgresClient for local ICP mode.
    All data is stored in a local SQLite database file.
    """

    # Class-level configuration
    SERVICE_NAME = "SQLite"
    DEFAULT_HOST = "localhost"  # Not used, but kept for interface compatibility
    DEFAULT_PORT = 0  # Embedded, no port
    ENV_PREFIX = "SQLITE"

    def __init__(
        self,
        database: Optional[str] = None,
        db_path: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize async SQLite client.

        Args:
            database: Database filename (default: from SQLITE_DB env or 'isa_mcp.db')
            db_path: Full path to database directory (default: ~/.isa_mcp)
            **kwargs: Base client args (user_id, organization_id, lazy_connect)
        """
        super().__init__(**kwargs)

        self._database = database or os.getenv('SQLITE_DB', 'isa_mcp.db')

        # Determine database path
        if db_path:
            self._db_path = Path(db_path)
        else:
            default_path = os.getenv('SQLITE_PATH', '~/.isa_mcp')
            self._db_path = Path(default_path).expanduser()

        # Ensure directory exists
        self._db_path.mkdir(parents=True, exist_ok=True)

        self._db_file = self._db_path / self._database
        self._conn: Optional[aiosqlite.Connection] = None

        # Schema mapping (PostgreSQL schema -> SQLite table prefix)
        self._schema_prefix = {}

    async def _connect(self) -> None:
        """Establish SQLite connection."""
        self._conn = await aiosqlite.connect(
            str(self._db_file),
            isolation_level=None  # Autocommit mode, we manage transactions explicitly
        )
        # Enable foreign keys
        await self._conn.execute('PRAGMA foreign_keys = ON')
        # Enable WAL mode for better concurrency
        await self._conn.execute('PRAGMA journal_mode = WAL')
        # Row factory for dict-like access
        self._conn.row_factory = aiosqlite.Row

        self._logger.info(f"Connected to SQLite at {self._db_file}")

    async def _disconnect(self) -> None:
        """Close SQLite connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self, detailed: bool = True) -> Optional[Dict]:
        """Check SQLite service health."""
        try:
            await self._ensure_connected()

            async with self._conn.execute('SELECT sqlite_version()') as cursor:
                row = await cursor.fetchone()
                version = row[0] if row else 'unknown'

            details = {}
            if detailed:
                # Get database file size
                if self._db_file.exists():
                    details['file_size_bytes'] = self._db_file.stat().st_size
                details['version'] = version
                details['path'] = str(self._db_file)

            return {
                'status': 'healthy',
                'healthy': True,
                'version': version,
                'details': details
            }

        except Exception as e:
            return self.handle_error(e, "health check")

    # ============================================
    # Query Operations
    # ============================================

    async def query(self, sql: str, params: Optional[List[Any]] = None,
                   schema: str = 'public') -> Optional[List[Dict]]:
        """Execute SELECT query.

        Args:
            sql: SQL query statement (PostgreSQL syntax, auto-converted)
            params: Query parameters
            schema: Database schema (converted to table prefix for SQLite)

        Returns:
            List of result rows as dictionaries
        """
        try:
            await self._ensure_connected()

            # Convert PostgreSQL syntax to SQLite
            sqlite_sql = _convert_pg_placeholders(_convert_pg_syntax(sql))

            # Handle schema by replacing schema references
            if schema != 'public':
                sqlite_sql = sqlite_sql.replace(f'{schema}.', f'{schema}_')

            # Serialize parameters
            sqlite_params = [_serialize_value(p) for p in (params or [])]

            async with self._conn.execute(sqlite_sql, sqlite_params) as cursor:
                rows = await cursor.fetchall()
                description = cursor.description

                if not rows:
                    return []

                return [_deserialize_row(row, description) for row in rows]

        except Exception as e:
            return self.handle_error(e, "query")

    async def query_row(self, sql: str, params: Optional[List[Any]] = None,
                       schema: str = 'public') -> Optional[Dict]:
        """Execute single row query.

        Args:
            sql: SQL query statement
            params: Query parameters
            schema: Database schema

        Returns:
            Single row as dictionary or None
        """
        try:
            await self._ensure_connected()

            sqlite_sql = _convert_pg_placeholders(_convert_pg_syntax(sql))

            if schema != 'public':
                sqlite_sql = sqlite_sql.replace(f'{schema}.', f'{schema}_')

            sqlite_params = [_serialize_value(p) for p in (params or [])]

            async with self._conn.execute(sqlite_sql, sqlite_params) as cursor:
                row = await cursor.fetchone()

                if row:
                    return _deserialize_row(row, cursor.description)
                return None

        except Exception as e:
            return self.handle_error(e, "query row")

    async def execute(self, sql: str, params: Optional[List[Any]] = None,
                     schema: str = 'public') -> Optional[int]:
        """Execute INSERT/UPDATE/DELETE statement.

        Args:
            sql: SQL statement
            params: Statement parameters
            schema: Database schema

        Returns:
            Number of rows affected
        """
        try:
            await self._ensure_connected()

            sqlite_sql = _convert_pg_placeholders(_convert_pg_syntax(sql))

            if schema != 'public':
                sqlite_sql = sqlite_sql.replace(f'{schema}.', f'{schema}_')

            sqlite_params = [_serialize_value(p) for p in (params or [])]

            async with self._conn.execute(sqlite_sql, sqlite_params) as cursor:
                await self._conn.commit()
                return cursor.rowcount

        except Exception as e:
            return self.handle_error(e, "execute")

    async def execute_batch(self, operations: List[Dict[str, Any]],
                           schema: str = 'public') -> Optional[Dict]:
        """Execute batch operations in a transaction.

        Args:
            operations: List of {'sql': str, 'params': List} dictionaries
            schema: Database schema

        Returns:
            Batch execution results
        """
        try:
            await self._ensure_connected()

            results = []
            total_rows = 0

            await self._conn.execute('BEGIN')

            try:
                for op in operations:
                    sql = op.get('sql', '')
                    params = op.get('params', [])

                    sqlite_sql = _convert_pg_placeholders(_convert_pg_syntax(sql))
                    if schema != 'public':
                        sqlite_sql = sqlite_sql.replace(f'{schema}.', f'{schema}_')

                    sqlite_params = [_serialize_value(p) for p in params]

                    try:
                        async with self._conn.execute(sqlite_sql, sqlite_params) as cursor:
                            rows_affected = cursor.rowcount
                            total_rows += rows_affected
                            results.append({'rows_affected': rows_affected, 'error': ''})
                    except Exception as e:
                        results.append({'rows_affected': 0, 'error': str(e)})

                await self._conn.execute('COMMIT')

            except Exception as e:
                await self._conn.execute('ROLLBACK')
                raise

            return {
                'total_rows_affected': total_rows,
                'results': results
            }

        except Exception as e:
            return self.handle_error(e, "execute batch")

    # ============================================
    # Query Builder Operations
    # ============================================

    async def select_from(
        self,
        table: str,
        columns: Optional[List[str]] = None,
        where: Optional[List[Dict]] = None,
        order_by: Optional[List[str]] = None,
        limit: int = 0,
        offset: int = 0,
        schema: str = 'public'
    ) -> Optional[List[Dict]]:
        """Query builder style SELECT."""
        try:
            # Build SELECT clause
            cols = ', '.join(columns) if columns else '*'

            # Handle schema
            table_name = f'{schema}_{table}' if schema != 'public' else table
            sql = f'SELECT {cols} FROM {table_name}'

            params = []

            # Build WHERE clause
            if where:
                conditions = []
                for w in where:
                    col = w.get('column', '')
                    op = w.get('operator', '=')
                    val = w.get('value')
                    conditions.append(f'{col} {op} ?')
                    params.append(_serialize_value(val))
                sql += ' WHERE ' + ' AND '.join(conditions)

            # Build ORDER BY clause
            if order_by:
                sql += ' ORDER BY ' + ', '.join(order_by)

            # Add LIMIT and OFFSET
            if limit > 0:
                sql += f' LIMIT {limit}'
            if offset > 0:
                sql += f' OFFSET {offset}'

            await self._ensure_connected()

            async with self._conn.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
                description = cursor.description

                if not rows:
                    return []

                return [_deserialize_row(row, description) for row in rows]

        except Exception as e:
            return self.handle_error(e, "select from")

    async def insert_into(
        self,
        table: str,
        rows: List[Dict],
        returning: bool = False,
        schema: str = 'public'
    ) -> Optional[int]:
        """Insert rows into table.

        Args:
            table: Table name
            rows: List of row dictionaries to insert
            returning: Return inserted rows (limited support in SQLite)
            schema: Database schema

        Returns:
            Number of rows inserted
        """
        try:
            if not rows:
                return 0

            await self._ensure_connected()

            # Handle schema
            table_name = f'{schema}_{table}' if schema != 'public' else table

            # Get columns from first row
            columns = list(rows[0].keys())
            cols_str = ', '.join(columns)

            # Build values placeholders
            placeholders = ', '.join('?' for _ in columns)
            sql = f'INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders})'

            count = 0
            await self._conn.execute('BEGIN')

            try:
                for row in rows:
                    values = [_serialize_value(row.get(col)) for col in columns]
                    await self._conn.execute(sql, values)
                    count += 1

                await self._conn.execute('COMMIT')

            except Exception as e:
                await self._conn.execute('ROLLBACK')
                raise

            return count

        except Exception as e:
            return self.handle_error(e, "insert into")

    # ============================================
    # Table Operations
    # ============================================

    async def list_tables(self, schema: str = 'public') -> List[str]:
        """List all tables."""
        try:
            await self._ensure_connected()

            sql = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"

            async with self._conn.execute(sql) as cursor:
                rows = await cursor.fetchall()

                tables = [row[0] for row in rows]

                # Filter by schema prefix if not public
                if schema != 'public':
                    prefix = f'{schema}_'
                    tables = [t[len(prefix):] for t in tables if t.startswith(prefix)]

                return sorted(tables)

        except Exception as e:
            self.handle_error(e, "list tables")
            return []

    async def table_exists(self, table: str, schema: str = 'public') -> bool:
        """Check if table exists."""
        try:
            await self._ensure_connected()

            table_name = f'{schema}_{table}' if schema != 'public' else table

            sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"

            async with self._conn.execute(sql, [table_name]) as cursor:
                row = await cursor.fetchone()
                return row is not None

        except Exception as e:
            self.handle_error(e, "table exists check")
            return False

    # ============================================
    # Schema Migration Support
    # ============================================

    async def execute_script(self, script: str) -> bool:
        """Execute a SQL script (multiple statements).

        Useful for running migrations.
        """
        try:
            await self._ensure_connected()

            # Convert PostgreSQL syntax
            sqlite_script = _convert_pg_syntax(script)

            # Replace common PostgreSQL types
            sqlite_script = sqlite_script.replace('SERIAL', 'INTEGER')
            sqlite_script = sqlite_script.replace('BIGSERIAL', 'INTEGER')
            sqlite_script = sqlite_script.replace('JSONB', 'TEXT')
            sqlite_script = sqlite_script.replace('TEXT[]', 'TEXT')  # Arrays as JSON
            sqlite_script = sqlite_script.replace('TIMESTAMP WITH TIME ZONE', 'TEXT')
            sqlite_script = sqlite_script.replace('TIMESTAMPTZ', 'TEXT')
            sqlite_script = sqlite_script.replace('UUID', 'TEXT')
            sqlite_script = sqlite_script.replace('BOOLEAN', 'INTEGER')

            await self._conn.executescript(sqlite_script)
            return True

        except Exception as e:
            self.handle_error(e, "execute script")
            return False

    # ============================================
    # Statistics
    # ============================================

    async def get_stats(self) -> Optional[Dict]:
        """Get database statistics."""
        try:
            await self._ensure_connected()

            async with self._conn.execute('SELECT sqlite_version()') as cursor:
                row = await cursor.fetchone()
                version = row[0] if row else 'unknown'

            # Count tables
            async with self._conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ) as cursor:
                row = await cursor.fetchone()
                table_count = row[0] if row else 0

            return {
                'database': {
                    'version': version,
                    'path': str(self._db_file),
                    'size_bytes': self._db_file.stat().st_size if self._db_file.exists() else 0,
                    'table_count': table_count
                }
            }

        except Exception as e:
            return self.handle_error(e, "get stats")

    # ============================================
    # Transaction Support
    # ============================================

    async def execute_in_transaction(self, operations: List[Dict[str, Any]],
                                     schema: str = 'public') -> bool:
        """Execute multiple operations in a single transaction."""
        try:
            await self._ensure_connected()

            await self._conn.execute('BEGIN')

            try:
                for op in operations:
                    sql = op.get('sql', '')
                    params = op.get('params', [])

                    sqlite_sql = _convert_pg_placeholders(_convert_pg_syntax(sql))
                    if schema != 'public':
                        sqlite_sql = sqlite_sql.replace(f'{schema}.', f'{schema}_')

                    sqlite_params = [_serialize_value(p) for p in params]
                    await self._conn.execute(sqlite_sql, sqlite_params)

                await self._conn.execute('COMMIT')
                return True

            except Exception as e:
                await self._conn.execute('ROLLBACK')
                raise

        except Exception as e:
            self.handle_error(e, "execute in transaction")
            return False

    # ============================================
    # Concurrent Operations
    # ============================================

    async def query_many_concurrent(self, queries: List[Dict[str, Any]]) -> List[Optional[List[Dict]]]:
        """Execute multiple queries (sequentially for SQLite thread safety)."""
        results = []
        for q in queries:
            result = await self.query(
                sql=q.get('sql', ''),
                params=q.get('params'),
                schema=q.get('schema', 'public')
            )
            results.append(result)
        return results

    async def execute_many_concurrent(self, statements: List[Dict[str, Any]]) -> List[Optional[int]]:
        """Execute multiple statements (sequentially for SQLite thread safety)."""
        results = []
        for s in statements:
            result = await self.execute(
                sql=s.get('sql', ''),
                params=s.get('params'),
                schema=s.get('schema', 'public')
            )
            results.append(result)
        return results


# Example usage
if __name__ == '__main__':
    async def main():
        async with AsyncSQLiteClient(
            database='test.db',
            db_path='/tmp/isa_test',
            user_id='test_user'
        ) as client:
            # Health check
            health = await client.health_check()
            print(f"Health: {health}")

            # Create table
            await client.execute('''
                CREATE TABLE IF NOT EXISTS test_table (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    data TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Insert
            count = await client.insert_into('test_table', [
                {'name': 'test1', 'data': json.dumps({'key': 'value1'})},
                {'name': 'test2', 'data': json.dumps({'key': 'value2'})}
            ])
            print(f"Inserted: {count}")

            # Query
            results = await client.query("SELECT * FROM test_table WHERE name LIKE ?", ['test%'])
            print(f"Query result: {results}")

            # List tables
            tables = await client.list_tables()
            print(f"Tables: {tables}")

            # Stats
            stats = await client.get_stats()
            print(f"Stats: {stats}")

    asyncio.run(main())
