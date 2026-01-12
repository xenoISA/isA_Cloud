#!/usr/bin/env python3
"""
Async PostgreSQL Native Client
High-performance async PostgreSQL client using asyncpg.

This client connects directly to PostgreSQL using the official asyncpg library,
providing full support for all PostgreSQL operations including:
- Query execution (SELECT, INSERT, UPDATE, DELETE)
- Prepared statements and parameterized queries
- Connection pooling
- Transaction management
- Batch operations

Performance Benefits:
- True async I/O without GIL blocking
- Connection pooling via asyncpg
- Binary protocol for faster data transfer
- Prepared statements for query optimization
- Direct protocol (no gRPC gateway overhead)
"""

import os
import logging
import asyncio
from typing import List, Dict, Optional, Any

import asyncpg
from asyncpg import Pool, Connection

logger = logging.getLogger(__name__)


class AsyncPostgresClient:
    """
    Async PostgreSQL client using native asyncpg driver.

    Provides direct connection to PostgreSQL with full feature support including
    all query operations, transactions, and high-performance connection pooling.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user_id: Optional[str] = None,
        database: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        lazy_connect: bool = True,
        min_pool_size: int = 5,
        max_pool_size: int = 20,
        **kwargs  # Accept additional kwargs for compatibility
    ):
        """
        Initialize async PostgreSQL client with native driver.

        Args:
            host: PostgreSQL host (default: from POSTGRES_HOST env or 'localhost')
            port: PostgreSQL port (default: from POSTGRES_PORT env or 5432)
            user_id: User ID for isolation (optional)
            database: Database name (default: from POSTGRES_DB env or 'postgres')
            username: Database username (default: from POSTGRES_USER env)
            password: Database password (default: from POSTGRES_PASSWORD env)
            lazy_connect: Delay connection until first use (default: True)
            min_pool_size: Minimum connections in pool (default: 5)
            max_pool_size: Maximum connections in pool (default: 20)
        """
        self._host = host or os.getenv('POSTGRES_HOST', 'localhost')
        self._port = port or int(os.getenv('POSTGRES_PORT', '5432'))
        self._database = database or os.getenv('POSTGRES_DB', 'postgres')
        self._username = username or os.getenv('POSTGRES_USER', 'postgres')
        self._password = password or os.getenv('POSTGRES_PASSWORD', '')
        self._min_pool_size = min_pool_size
        self._max_pool_size = max_pool_size

        self.user_id = user_id or 'default'

        self._pool: Optional[Pool] = None

        logger.info(f"AsyncPostgresClient initialized: {self._host}:{self._port}/{self._database}")

    async def _ensure_connected(self):
        """Ensure PostgreSQL connection pool is established."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=self._host,
                port=self._port,
                database=self._database,
                user=self._username,
                password=self._password,
                min_size=self._min_pool_size,
                max_size=self._max_pool_size,
                command_timeout=60
            )
            logger.info(f"Connected to PostgreSQL at {self._host}:{self._port}/{self._database}")

    async def close(self):
        """Close PostgreSQL connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
        logger.info("PostgreSQL connection pool closed")

    async def __aenter__(self):
        """Async context manager entry - ensures connection pool is ready."""
        await self._ensure_connected()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - keeps pool alive for reuse.

        Note: Pool is intentionally NOT closed here to allow connection reuse.
        Call close() or shutdown() explicitly when done with the client.
        """
        # Don't close pool - keep it alive for reuse
        pass

    async def shutdown(self):
        """Explicitly shutdown the connection pool. Call at application exit."""
        await self.close()

    def handle_error(self, error: Exception, operation: str) -> None:
        """Handle and log errors."""
        logger.error(f"PostgreSQL {operation} failed: {error}")
        return None

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self, detailed: bool = True) -> Optional[Dict]:
        """Check PostgreSQL service health."""
        try:
            await self._ensure_connected()

            async with self._pool.acquire() as conn:
                # Simple ping
                result = await conn.fetchval('SELECT 1')

                details = {}
                if detailed:
                    version = await conn.fetchval('SELECT version()')
                    details['version'] = version
                    details['pool_size'] = self._pool.get_size()
                    details['pool_free'] = self._pool.get_idle_size()

                return {
                    'status': 'healthy',
                    'healthy': True,
                    'version': details.get('version', ''),
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
            sql: SQL query statement
            params: Query parameters
            schema: Database schema (default: public)

        Returns:
            List of result rows as dictionaries
        """
        try:
            await self._ensure_connected()

            async with self._pool.acquire() as conn:
                # Set search path for schema
                if schema != 'public':
                    await conn.execute(f'SET search_path TO {schema}, public')

                if params:
                    rows = await conn.fetch(sql, *params)
                else:
                    rows = await conn.fetch(sql)

                return [dict(row) for row in rows]

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

            async with self._pool.acquire() as conn:
                if schema != 'public':
                    await conn.execute(f'SET search_path TO {schema}, public')

                if params:
                    row = await conn.fetchrow(sql, *params)
                else:
                    row = await conn.fetchrow(sql)

                if row:
                    return dict(row)
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

            async with self._pool.acquire() as conn:
                if schema != 'public':
                    await conn.execute(f'SET search_path TO {schema}, public')

                if params:
                    result = await conn.execute(sql, *params)
                else:
                    result = await conn.execute(sql)

                # Parse rows affected from result string (e.g., "UPDATE 5")
                parts = result.split()
                if len(parts) >= 2 and parts[-1].isdigit():
                    return int(parts[-1])
                return 0

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

            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    if schema != 'public':
                        await conn.execute(f'SET search_path TO {schema}, public')

                    for op in operations:
                        sql = op.get('sql', '')
                        params = op.get('params', [])

                        try:
                            if params:
                                result = await conn.execute(sql, *params)
                            else:
                                result = await conn.execute(sql)

                            # Parse rows affected
                            parts = result.split()
                            rows_affected = int(parts[-1]) if len(parts) >= 2 and parts[-1].isdigit() else 0
                            total_rows += rows_affected
                            results.append({'rows_affected': rows_affected, 'error': ''})
                        except Exception as e:
                            results.append({'rows_affected': 0, 'error': str(e)})

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
        """Query builder style SELECT.

        Args:
            table: Table name
            columns: Columns to select (default: all)
            where: WHERE conditions as list of dicts
            order_by: ORDER BY clauses
            limit: LIMIT value
            offset: OFFSET value
            schema: Database schema

        Returns:
            List of result rows
        """
        try:
            # Build SELECT clause
            cols = ', '.join(columns) if columns else '*'
            sql = f'SELECT {cols} FROM {table}'

            params = []
            param_idx = 1

            # Build WHERE clause
            if where:
                conditions = []
                for w in where:
                    col = w.get('column', '')
                    op = w.get('operator', '=')
                    val = w.get('value')
                    conditions.append(f'{col} {op} ${param_idx}')
                    params.append(val)
                    param_idx += 1
                sql += ' WHERE ' + ' AND '.join(conditions)

            # Build ORDER BY clause
            if order_by:
                sql += ' ORDER BY ' + ', '.join(order_by)

            # Add LIMIT and OFFSET
            if limit > 0:
                sql += f' LIMIT {limit}'
            if offset > 0:
                sql += f' OFFSET {offset}'

            return await self.query(sql, params if params else None, schema)

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
            returning: Return inserted rows
            schema: Database schema

        Returns:
            Number of rows inserted
        """
        try:
            if not rows:
                return 0

            await self._ensure_connected()

            async with self._pool.acquire() as conn:
                if schema != 'public':
                    await conn.execute(f'SET search_path TO {schema}, public')

                # Get columns from first row
                columns = list(rows[0].keys())
                cols_str = ', '.join(columns)

                # Build values placeholders
                placeholders = ', '.join(f'${i+1}' for i in range(len(columns)))
                sql = f'INSERT INTO {table} ({cols_str}) VALUES ({placeholders})'

                if returning:
                    sql += ' RETURNING *'

                # Use executemany for batch insert
                count = 0
                async with conn.transaction():
                    for row in rows:
                        values = [row.get(col) for col in columns]
                        await conn.execute(sql, *values)
                        count += 1

                return count

        except Exception as e:
            return self.handle_error(e, "insert into")

    # ============================================
    # Table Operations
    # ============================================

    async def list_tables(self, schema: str = 'public') -> List[str]:
        """List all tables in schema.

        Args:
            schema: Database schema

        Returns:
            List of table names
        """
        try:
            await self._ensure_connected()

            sql = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = $1
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """

            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, schema)
                return [row['table_name'] for row in rows]

        except Exception as e:
            self.handle_error(e, "list tables")
            return []

    async def table_exists(self, table: str, schema: str = 'public') -> bool:
        """Check if table exists.

        Args:
            table: Table name
            schema: Database schema

        Returns:
            True if table exists, False otherwise
        """
        try:
            await self._ensure_connected()

            sql = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = $1
                    AND table_name = $2
                )
            """

            async with self._pool.acquire() as conn:
                return await conn.fetchval(sql, schema, table)

        except Exception as e:
            self.handle_error(e, "table exists check")
            return False

    # ============================================
    # Statistics
    # ============================================

    async def get_stats(self) -> Optional[Dict]:
        """Get connection pool and database statistics.

        Returns:
            Statistics dictionary
        """
        try:
            await self._ensure_connected()

            async with self._pool.acquire() as conn:
                version = await conn.fetchval('SELECT version()')

                return {
                    'pool': {
                        'max_connections': self._max_pool_size,
                        'open_connections': self._pool.get_size(),
                        'idle_connections': self._pool.get_idle_size(),
                        'active_connections': self._pool.get_size() - self._pool.get_idle_size(),
                        'total_queries': 0,  # asyncpg doesn't track this
                    },
                    'database': {
                        'version': version,
                    }
                }

        except Exception as e:
            return self.handle_error(e, "get stats")

    # ============================================
    # Transaction Support
    # ============================================

    async def transaction(self):
        """Get a connection with transaction context.

        Usage:
            async with client.transaction() as conn:
                await conn.execute(...)
                await conn.execute(...)
        """
        await self._ensure_connected()
        return self._pool.acquire()

    async def execute_in_transaction(self, operations: List[Dict[str, Any]],
                                     schema: str = 'public') -> bool:
        """Execute multiple operations in a single transaction.

        Args:
            operations: List of {'sql': str, 'params': list} dicts
            schema: Database schema

        Returns:
            True if successful, False otherwise
        """
        try:
            await self._ensure_connected()

            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    if schema != 'public':
                        await conn.execute(f'SET search_path TO {schema}, public')

                    for op in operations:
                        sql = op.get('sql', '')
                        params = op.get('params', [])

                        if params:
                            await conn.execute(sql, *params)
                        else:
                            await conn.execute(sql)

            return True

        except Exception as e:
            self.handle_error(e, "execute in transaction")
            return False

    # ============================================
    # Concurrent Operations
    # ============================================

    async def query_many_concurrent(self, queries: List[Dict[str, Any]]) -> List[Optional[List[Dict]]]:
        """
        Execute multiple queries concurrently.

        Args:
            queries: List of {'sql': str, 'params': list, 'schema': str} dicts

        Returns:
            List of results for each query
        """
        async def execute_query(q: Dict) -> Optional[List[Dict]]:
            return await self.query(
                sql=q.get('sql', ''),
                params=q.get('params'),
                schema=q.get('schema', 'public')
            )

        return await asyncio.gather(*[execute_query(q) for q in queries])

    async def execute_many_concurrent(self, statements: List[Dict[str, Any]]) -> List[Optional[int]]:
        """
        Execute multiple statements concurrently.

        Args:
            statements: List of {'sql': str, 'params': list, 'schema': str} dicts

        Returns:
            List of rows affected for each statement
        """
        async def execute_stmt(s: Dict) -> Optional[int]:
            return await self.execute(
                sql=s.get('sql', ''),
                params=s.get('params'),
                schema=s.get('schema', 'public')
            )

        return await asyncio.gather(*[execute_stmt(s) for s in statements])


# Example usage
if __name__ == '__main__':
    async def main():
        async with AsyncPostgresClient(
            host='localhost',
            port=5432,
            database='testdb',
            username='postgres',
            password='postgres',
            user_id='test_user'
        ) as client:
            # Health check
            health = await client.health_check()
            print(f"Health: {health}")

            # List tables
            tables = await client.list_tables()
            print(f"Tables: {tables}")

            # Query
            results = await client.query("SELECT 1 as num, 'hello' as msg")
            print(f"Query result: {results}")

            # Concurrent queries
            results = await client.query_many_concurrent([
                {'sql': 'SELECT 1 as num'},
                {'sql': 'SELECT 2 as num'},
                {'sql': 'SELECT 3 as num'}
            ])
            print(f"Concurrent results: {results}")

    asyncio.run(main())
