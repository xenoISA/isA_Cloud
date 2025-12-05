#!/usr/bin/env python3
"""
Async DuckDB gRPC Client
High-performance async DuckDB client using grpc.aio

Performance Benefits:
- True async I/O without GIL blocking
- Concurrent analytics queries
- Non-blocking data imports/exports
- Memory-efficient connection pooling
"""

import asyncio
import logging
import re
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from .async_base_client import AsyncBaseGRPCClient
from .proto import duckdb_service_pb2, duckdb_service_pb2_grpc

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry

logger = logging.getLogger(__name__)


class AsyncDuckDBClient(AsyncBaseGRPCClient):
    """Async DuckDB gRPC client for high-performance analytics."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user_id: Optional[str] = None,
        lazy_connect: bool = True,
        enable_compression: bool = True,
        enable_retry: bool = True,
        consul_registry: Optional['ConsulRegistry'] = None,
        service_name_override: Optional[str] = None
    ):
        """
        Initialize async DuckDB client.

        Args:
            host: Service address (optional, will use Consul discovery if not provided)
            port: Service port (optional, will use Consul discovery if not provided)
            user_id: User ID
            lazy_connect: Lazy connection (default: True)
            enable_compression: Enable compression (default: True for large data)
            enable_retry: Enable retry (default: True)
            consul_registry: ConsulRegistry instance for service discovery (optional)
            service_name_override: Override service name for Consul lookup (optional)
        """
        super().__init__(
            host=host,
            port=port,
            user_id=user_id,
            lazy_connect=lazy_connect,
            enable_compression=enable_compression,
            enable_retry=enable_retry,
            consul_registry=consul_registry,
            service_name_override=service_name_override
        )

    def _create_stub(self):
        """Create DuckDB service stub."""
        return duckdb_service_pb2_grpc.DuckDBServiceStub(self.channel)

    def service_name(self) -> str:
        return "DuckDB"

    def default_port(self) -> int:
        return 50052

    def _get_org_id(self) -> str:
        """Get organization ID."""
        return 'default_org'

    def get_table_prefix(self) -> str:
        """Get table name prefix."""
        return f"user_{self.user_id}_"

    def qualify_table_name(self, table_name: str, use_prefix: bool = True) -> str:
        """Add user prefix to table name."""
        if use_prefix and not table_name.startswith(self.get_table_prefix()):
            return f"{self.get_table_prefix()}{table_name}"
        return table_name

    def _qualify_sql_tables(self, sql: str) -> str:
        """Auto-qualify table names in SQL with user prefix."""
        prefix = self.get_table_prefix()

        if prefix in sql:
            return sql

        cte_names = set()
        cte_pattern = r'\bWITH\s+(\w+)\s+AS\s*\('
        for match in re.finditer(cte_pattern, sql, re.IGNORECASE):
            cte_names.add(match.group(1).lower())
        chained_cte_pattern = r',\s*(\w+)\s+AS\s*\('
        for match in re.finditer(chained_cte_pattern, sql, re.IGNORECASE):
            cte_names.add(match.group(1).lower())

        patterns = [
            (r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)\b', rf'FROM {prefix}\1'),
            (r'\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)\b', rf'JOIN {prefix}\1'),
            (r'\bINTO\s+([a-zA-Z_][a-zA-Z0-9_]*)\b', rf'INTO {prefix}\1'),
            (r'\bUPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)\b', rf'UPDATE {prefix}\1'),
            (r'\bTABLE\s+([a-zA-Z_][a-zA-Z0-9_]*)\b', rf'TABLE {prefix}\1'),
        ]

        result = sql
        for pattern, replacement in patterns:
            safe_pattern = pattern.replace('([a-zA-Z_][a-zA-Z0-9_]*)',
                                          r'(?!(?:pg_|information_schema|sqlite_|duckdb_|temp\.|main\.))([a-zA-Z_][a-zA-Z0-9_]*)')

            def replace_fn(match):
                table_name = match.group(1)
                if table_name.lower() in cte_names:
                    return match.group(0)
                return match.group(0).replace(table_name, f"{prefix}{table_name}")

            result = re.sub(safe_pattern, replace_fn, result, flags=re.IGNORECASE)

        return result

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self, detailed: bool = False) -> Optional[Dict]:
        """Health check."""
        try:
            await self._ensure_connected()
            request = duckdb_service_pb2.HealthCheckRequest(detailed=detailed)
            response = await self.stub.HealthCheck(request)

            return {
                'healthy': response.healthy,
                'version': getattr(response, 'version', ''),
                'message': getattr(response, 'message', '')
            }

        except Exception as e:
            return self.handle_error(e, "health check")

    # ============================================
    # Database Management
    # ============================================

    async def create_database(self, db_name: str, minio_bucket: str = '',
                             metadata: Optional[Dict[str, str]] = None) -> Optional[Dict]:
        """Create database."""
        try:
            await self._ensure_connected()
            request = duckdb_service_pb2.CreateDatabaseRequest(
                database_name=db_name,
                user_id=self.user_id,
                organization_id=self._get_org_id(),
                minio_bucket=minio_bucket,
                metadata=metadata or {},
            )

            response = await self.stub.CreateDatabase(request)

            if response.success:
                return {
                    'database_id': response.database_info.database_id,
                    'database_name': response.database_info.database_name,
                    'minio_bucket': response.database_info.minio_bucket,
                    'size_bytes': response.database_info.size_bytes,
                    'table_count': response.database_info.table_count,
                }
            return None

        except Exception as e:
            return self.handle_error(e, "create database")

    async def list_databases(self) -> List[Dict]:
        """List all databases."""
        try:
            await self._ensure_connected()
            request = duckdb_service_pb2.ListDatabasesRequest(
                user_id=self.user_id,
                organization_id=self._get_org_id(),
            )

            response = await self.stub.ListDatabases(request)

            if response.success:
                databases = []
                for db in response.databases:
                    databases.append({
                        'database_id': db.database_id,
                        'name': db.database_name,
                        'size': db.size_bytes,
                        'table_count': db.table_count,
                        'created_at': str(db.created_at),
                    })
                return databases
            return []

        except Exception as e:
            return self.handle_error(e, "list databases") or []

    async def delete_database(self, db_name: str, delete_from_minio: bool = True,
                             force: bool = False) -> bool:
        """Delete database."""
        try:
            await self._ensure_connected()
            request = duckdb_service_pb2.DeleteDatabaseRequest(
                database_id=db_name,
                user_id=self.user_id,
                delete_from_minio=delete_from_minio,
                force=force,
            )

            response = await self.stub.DeleteDatabase(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "delete database")
            return False

    async def get_database_info(self, db_name: str) -> Optional[Dict]:
        """Get database information."""
        try:
            await self._ensure_connected()
            request = duckdb_service_pb2.GetDatabaseInfoRequest(
                database_id=db_name,
                user_id=self.user_id,
            )

            response = await self.stub.GetDatabaseInfo(request)

            if response.success:
                return {
                    'database_name': response.database_info.database_name,
                    'size_bytes': response.database_info.size_bytes,
                    'table_count': response.database_info.table_count,
                    'minio_bucket': response.database_info.minio_bucket,
                    'minio_path': response.database_info.minio_path,
                    'created_at': str(response.database_info.created_at),
                    'last_accessed': str(response.database_info.last_accessed),
                }
            return None

        except Exception as e:
            return self.handle_error(e, "get database info")

    # ============================================
    # Query Operations
    # ============================================

    async def execute_query(self, db_name: str, sql: str, limit: int = 100,
                           auto_qualify_tables: bool = True) -> List[Dict]:
        """Execute SQL query."""
        try:
            await self._ensure_connected()

            if auto_qualify_tables:
                sql = self._qualify_sql_tables(sql)

            request = duckdb_service_pb2.ExecuteQueryRequest(
                database_id=db_name,
                user_id=self.user_id,
                query=sql,
                max_rows=limit,
            )

            response = await self.stub.ExecuteQuery(request)

            if response.success:
                columns = list(response.columns)
                results = []

                for row_msg in response.rows:
                    row_dict = {}
                    for i, value in enumerate(row_msg.values):
                        if i >= len(columns):
                            break
                        col_name = columns[i]

                        if value.HasField('int_value'):
                            row_dict[col_name] = value.int_value
                        elif value.HasField('double_value'):
                            row_dict[col_name] = value.double_value
                        elif value.HasField('string_value'):
                            row_dict[col_name] = value.string_value
                        elif value.HasField('bool_value'):
                            row_dict[col_name] = value.bool_value
                        elif value.HasField('null_value'):
                            row_dict[col_name] = None
                        else:
                            row_dict[col_name] = None
                    results.append(row_dict)

                return results
            return []

        except Exception as e:
            return self.handle_error(e, "execute query") or []

    async def execute_statement(self, db_name: str, sql: str,
                               auto_qualify_tables: bool = True) -> int:
        """Execute write operation (INSERT/UPDATE/DELETE)."""
        try:
            await self._ensure_connected()

            if auto_qualify_tables:
                sql = self._qualify_sql_tables(sql)

            request = duckdb_service_pb2.ExecuteStatementRequest(
                database_id=db_name,
                user_id=self.user_id,
                statement=sql,
            )

            response = await self.stub.ExecuteStatement(request)

            if response.success:
                return response.affected_rows
            return 0

        except Exception as e:
            return self.handle_error(e, "execute statement") or 0

    async def execute_batch(self, db_name: str, statements: List[str],
                           use_transaction: bool = True,
                           auto_qualify_tables: bool = True) -> Optional[Dict]:
        """Batch execute SQL statements."""
        try:
            await self._ensure_connected()

            if auto_qualify_tables:
                statements = [self._qualify_sql_tables(stmt) for stmt in statements]

            request = duckdb_service_pb2.ExecuteBatchRequest(
                database_id=db_name,
                user_id=self.user_id,
                statements=statements,
                transaction=use_transaction,
            )

            response = await self.stub.ExecuteBatch(request)

            if response.success:
                results = []
                for r in response.results:
                    results.append({
                        'success': r.success,
                        'affected_rows': r.affected_rows,
                        'error': r.error if r.error else None
                    })
                return {
                    'success': True,
                    'results': results,
                    'total_execution_time_ms': response.total_execution_time_ms
                }
            return None

        except Exception as e:
            return self.handle_error(e, "execute batch")

    # ============================================
    # Table Management
    # ============================================

    async def create_table(self, db_name: str, table_name: str,
                          schema: Dict[str, str]) -> bool:
        """Create table."""
        try:
            await self._ensure_connected()
            columns = [
                duckdb_service_pb2.ColumnInfo(name=name, data_type=dtype)
                for name, dtype in schema.items()
            ]

            request = duckdb_service_pb2.CreateTableRequest(
                database_id=db_name,
                user_id=self.user_id,
                table_name=table_name,
                columns=columns,
            )

            response = await self.stub.CreateTable(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "create table")
            return False

    async def list_tables(self, db_name: str) -> List[str]:
        """List all tables."""
        try:
            await self._ensure_connected()
            request = duckdb_service_pb2.ListTablesRequest(
                database_id=db_name,
                user_id=self.user_id,
            )

            response = await self.stub.ListTables(request)

            if response.success:
                return [table.table_name for table in response.tables]
            return []

        except Exception as e:
            return self.handle_error(e, "list tables") or []

    async def drop_table(self, db_name: str, table_name: str,
                        if_exists: bool = True, cascade: bool = False) -> bool:
        """Drop table."""
        try:
            await self._ensure_connected()
            request = duckdb_service_pb2.DropTableRequest(
                database_id=db_name,
                user_id=self.user_id,
                table_name=table_name,
                if_exists=if_exists,
                cascade=cascade,
            )

            response = await self.stub.DropTable(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "drop table")
            return False

    async def get_table_schema(self, db_name: str, table_name: str) -> Optional[Dict]:
        """Get table schema."""
        try:
            await self._ensure_connected()
            request = duckdb_service_pb2.GetTableSchemaRequest(
                database_id=db_name,
                user_id=self.user_id,
                table_name=table_name,
            )

            response = await self.stub.GetTableSchema(request)

            if response.success:
                columns = []
                for col in response.table_info.columns:
                    columns.append({
                        'name': col.name,
                        'data_type': col.data_type,
                        'nullable': col.nullable,
                        'is_primary_key': col.is_primary_key,
                    })

                return {
                    'table_name': response.table_info.table_name,
                    'columns': columns,
                    'row_count': response.table_info.row_count,
                    'size_bytes': response.table_info.size_bytes,
                }
            return None

        except Exception as e:
            return self.handle_error(e, "get table schema")

    async def get_table_stats(self, db_name: str, table_name: str,
                             include_columns: bool = True) -> Optional[Dict]:
        """Get table statistics."""
        try:
            await self._ensure_connected()
            request = duckdb_service_pb2.GetTableStatsRequest(
                database_id=db_name,
                user_id=self.user_id,
                table_name=table_name,
                include_columns=include_columns,
            )

            response = await self.stub.GetTableStats(request)

            if response.success:
                stats = {
                    'table_name': response.stats.table_name,
                    'row_count': response.stats.row_count,
                    'size_bytes': response.stats.size_bytes,
                    'column_stats': []
                }

                if include_columns:
                    for col_stat in response.stats.column_stats:
                        stats['column_stats'].append({
                            'column_name': col_stat.column_name,
                            'distinct_count': col_stat.distinct_count,
                            'null_count': col_stat.null_count,
                        })

                return stats
            return None

        except Exception as e:
            return self.handle_error(e, "get table stats")

    # ============================================
    # Data Import/Export (MinIO)
    # ============================================

    async def import_from_minio(self, db_name: str, table_name: str,
                               bucket: str, object_key: str,
                               file_format: str = 'parquet') -> bool:
        """Import data from MinIO."""
        try:
            await self._ensure_connected()
            request = duckdb_service_pb2.ImportFromMinIORequest(
                database_id=db_name,
                user_id=self.user_id,
                table_name=table_name,
                bucket_name=bucket,
                object_key=object_key,
                format=file_format,
            )

            response = await self.stub.ImportFromMinIO(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "import from MinIO")
            return False

    async def export_to_minio(self, db_name: str, query: str, bucket: str,
                             object_key: str, file_format: str = 'parquet',
                             overwrite: bool = True,
                             auto_qualify_tables: bool = True) -> Optional[Dict]:
        """Export query results to MinIO."""
        try:
            await self._ensure_connected()

            if auto_qualify_tables:
                query = self._qualify_sql_tables(query)

            request = duckdb_service_pb2.ExportToMinIORequest(
                database_id=db_name,
                user_id=self.user_id,
                query=query,
                bucket_name=bucket,
                object_key=object_key,
                format=file_format,
                overwrite=overwrite,
            )

            response = await self.stub.ExportToMinIO(request)

            if response.success:
                return {
                    'success': True,
                    'rows_exported': response.rows_exported,
                    'file_size': response.file_size,
                    'execution_time_ms': response.execution_time_ms
                }
            return None

        except Exception as e:
            return self.handle_error(e, "export to MinIO")

    async def query_minio_file(self, db_name: str, bucket: str,
                              object_key: str, file_format: str = 'parquet',
                              limit: int = 100) -> List[Dict]:
        """Query MinIO file directly without importing."""
        try:
            await self._ensure_connected()
            query = f"SELECT * FROM $FILE LIMIT {limit}"

            request = duckdb_service_pb2.QueryMinIOFileRequest(
                database_id=db_name,
                user_id=self.user_id,
                bucket_name=bucket,
                object_key=object_key,
                format=file_format,
                query=query,
            )

            response = await self.stub.QueryMinIOFile(request)

            if response.success:
                columns = list(response.columns)
                results = []

                for row_msg in response.rows:
                    row_dict = {}
                    for i, value in enumerate(row_msg.values):
                        if i >= len(columns):
                            break
                        col_name = columns[i]

                        if value.HasField('int_value'):
                            row_dict[col_name] = value.int_value
                        elif value.HasField('double_value'):
                            row_dict[col_name] = value.double_value
                        elif value.HasField('string_value'):
                            row_dict[col_name] = value.string_value
                        elif value.HasField('bool_value'):
                            row_dict[col_name] = value.bool_value
                        elif value.HasField('null_value'):
                            row_dict[col_name] = None
                        else:
                            row_dict[col_name] = None
                    results.append(row_dict)

                return results
            return []

        except Exception as e:
            return self.handle_error(e, "query MinIO file") or []

    # ============================================
    # Concurrent Operations
    # ============================================

    async def execute_queries_concurrent(self, db_name: str,
                                        queries: List[str]) -> List[List[Dict]]:
        """Execute multiple queries concurrently."""
        tasks = [self.execute_query(db_name, q) for q in queries]
        return await asyncio.gather(*tasks)

    async def execute_statements_concurrent(self, db_name: str,
                                           statements: List[str]) -> List[int]:
        """Execute multiple statements concurrently."""
        tasks = [self.execute_statement(db_name, s) for s in statements]
        return await asyncio.gather(*tasks)
