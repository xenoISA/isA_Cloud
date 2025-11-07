#!/usr/bin/env python3
"""
DuckDB gRPC Client
DuckDB OLAP 数据分析客户端
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING
from google.protobuf import struct_pb2
from google.protobuf.json_format import MessageToDict

from .base_client import BaseGRPCClient
from .proto import duckdb_service_pb2, duckdb_service_pb2_grpc, common_pb2

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry


class DuckDBClient(BaseGRPCClient):
    """DuckDB gRPC 客户端"""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, user_id: Optional[str] = None,
                 lazy_connect: bool = True, enable_compression: bool = True, enable_retry: bool = True,
                 consul_registry: Optional['ConsulRegistry'] = None, service_name_override: Optional[str] = None):
        """
        初始化 DuckDB 客户端

        Args:
            host: 服务地址 (optional, will use Consul discovery if not provided)
            port: 服务端口 (optional, will use Consul discovery if not provided)
            user_id: 用户 ID
            lazy_connect: 延迟连接 (默认: True)
            enable_compression: 启用压缩 (默认: True)
            enable_retry: 启用重试 (默认: True)
            consul_registry: ConsulRegistry instance for service discovery (optional)
            service_name_override: Override service name for Consul lookup (optional, defaults to 'duckdb')
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
        """创建 DuckDB service stub"""
        return duckdb_service_pb2_grpc.DuckDBServiceStub(self.channel)
    
    def service_name(self) -> str:
        return "DuckDB"

    def default_port(self) -> int:
        return 50052
    
    def _get_org_id(self) -> str:
        """获取组织ID"""
        return 'default_org'

    def get_table_prefix(self) -> str:
        """
        获取表名前缀

        DuckDB 服务使用平面命名约定：user_{user_id}_{table_name}

        Returns:
            表名前缀，例如: "user_test_user_"
        """
        return f"user_{self.user_id}_"

    def get_minio_bucket_name(self, base_bucket: str) -> str:
        """
        获取 MinIO 完整桶名（包含用户前缀）

        MinIO 服务为每个用户添加前缀：user-{sanitized_user_id}-{bucket}
        例如：user_id='test_user', bucket='duckdb-data' → 'user-test-user-duckdb-data'

        Args:
            base_bucket: 基础桶名

        Returns:
            完整的 MinIO 桶名
        """
        # Sanitize user_id: replace underscores with hyphens for DNS compliance
        sanitized_user_id = self.user_id.replace('_', '-')
        return f"user-{sanitized_user_id}-{base_bucket}"

    def qualify_table_name(self, table_name: str, use_prefix: bool = True) -> str:
        """
        为表名添加用户前缀

        Args:
            table_name: 表名
            use_prefix: 是否使用前缀

        Returns:
            带前缀的表名，例如: "user_test_user_hot_events"
        """
        if use_prefix and not table_name.startswith(self.get_table_prefix()):
            return f"{self.get_table_prefix()}{table_name}"
        return table_name

    def _qualify_sql_tables(self, sql: str) -> str:
        """
        在 SQL 语句中自动为表名添加用户前缀

        DuckDB 服务使用平面命名：user_{user_id}_{table_name}
        例如: "hot_events" -> "user_test_user_hot_events"

        支持的模式：
        - FROM table_name
        - JOIN table_name
        - INTO table_name
        - UPDATE table_name
        - TABLE table_name

        不会修改：
        - CTE (WITH ... AS) 定义的表名
        - 表别名
        - 系统表

        Args:
            sql: 原始 SQL 语句

        Returns:
            处理后的 SQL 语句
        """
        import re

        prefix = self.get_table_prefix()

        # Skip if SQL already contains prefixed tables for this user
        if prefix in sql:
            return sql

        # Extract CTE names from WITH clauses to exclude them from prefixing
        cte_names = set()
        cte_pattern = r'\bWITH\s+(\w+)\s+AS\s*\('
        for match in re.finditer(cte_pattern, sql, re.IGNORECASE):
            cte_names.add(match.group(1).lower())
        # Also match chained CTEs: WITH a AS (...), b AS (...)
        chained_cte_pattern = r',\s*(\w+)\s+AS\s*\('
        for match in re.finditer(chained_cte_pattern, sql, re.IGNORECASE):
            cte_names.add(match.group(1).lower())

        # Pattern to match table names in common SQL clauses
        patterns = [
            (r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)\b', rf'FROM {prefix}\1'),
            (r'\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)\b', rf'JOIN {prefix}\1'),
            (r'\bINTO\s+([a-zA-Z_][a-zA-Z0-9_]*)\b', rf'INTO {prefix}\1'),
            (r'\bUPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)\b', rf'UPDATE {prefix}\1'),
            (r'\bTABLE\s+([a-zA-Z_][a-zA-Z0-9_]*)\b', rf'TABLE {prefix}\1'),
        ]

        result = sql
        for pattern, replacement in patterns:
            # Use negative lookahead to avoid matching system tables and CTEs
            safe_pattern = pattern.replace('([a-zA-Z_][a-zA-Z0-9_]*)',
                                          r'(?!(?:pg_|information_schema|sqlite_|duckdb_|temp\.|main\.))([a-zA-Z_][a-zA-Z0-9_]*)')

            # Apply replacement, but skip if table name is a CTE
            def replace_fn(match):
                table_name = match.group(1)
                if table_name.lower() in cte_names:
                    return match.group(0)  # Don't replace CTEs
                return match.group(0).replace(table_name, f"{prefix}{table_name}")

            result = re.sub(safe_pattern, replace_fn, result, flags=re.IGNORECASE)

        return result

    # ========================================
    # 数据库管理
    # ========================================
    
    def create_database(self, db_name: str, minio_bucket: str = '', metadata: Optional[Dict[str, str]] = None) -> Optional[Dict]:
        """
        创建数据库

        Args:
            db_name: 数据库名称
            minio_bucket: MinIO bucket for data storage
            metadata: Metadata dict

        Returns:
            数据库信息 {'database_id': str, 'database_name': str, ...} 或 None
        """
        try:
            self._ensure_connected()
            request = duckdb_service_pb2.CreateDatabaseRequest(
                database_name=db_name,
                user_id=self.user_id,
                organization_id=self._get_org_id(),
                minio_bucket=minio_bucket,
                metadata=metadata or {},
            )

            response = self.stub.CreateDatabase(request)

            if response.success:
                db_info = {
                    'database_id': response.database_info.database_id,
                    'database_name': response.database_info.database_name,
                    'minio_bucket': response.database_info.minio_bucket,
                    'size_bytes': response.database_info.size_bytes,
                    'table_count': response.database_info.table_count,
                }
                return db_info
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "创建数据库") or None
    
    def list_databases(self) -> List[Dict]:
        """
        列出所有数据库

        Returns:
            数据库列表
        """
        try:
            self._ensure_connected()
            request = duckdb_service_pb2.ListDatabasesRequest(
                user_id=self.user_id,
                organization_id=self._get_org_id(),
            )
            
            response = self.stub.ListDatabases(request)
            
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
            else:
                return []
                
        except Exception as e:
            return self.handle_error(e, "列出数据库") or []
    
    # ========================================
    # 查询操作
    # ========================================
    
    def execute_query(self, db_name: str, sql: str, limit: int = 100, auto_qualify_tables: bool = True) -> List[Dict]:
        """
        执行 SQL 查询

        Args:
            db_name: 数据库名称
            sql: SQL 查询语句
            limit: 返回结果限制
            auto_qualify_tables: 自动在 SQL 中添加 schema 前缀（默认: True）

        Returns:
            查询结果列表

        Note:
            如果 auto_qualify_tables=True，会自动在 SQL 中的表名前添加 user schema
            例如: "SELECT * FROM hot_events" -> "SELECT * FROM user_test_user.hot_events"
        """
        try:
            self._ensure_connected()

            # Auto-qualify table names in SQL if requested
            if auto_qualify_tables:
                sql = self._qualify_sql_tables(sql)

            request = duckdb_service_pb2.ExecuteQueryRequest(
                database_id=db_name,
                user_id=self.user_id,
                query=sql,
                max_rows=limit,
            )
            
            response = self.stub.ExecuteQuery(request)
            
            if response.success:
                # 转换结果
                # Row contains repeated Value (list), need to combine with column names
                columns = list(response.columns)
                results = []

                for row_msg in response.rows:
                    row_dict = {}
                    # row_msg.values is a repeated field (list of Value messages)
                    for i, value in enumerate(row_msg.values):
                        if i >= len(columns):
                            break
                        col_name = columns[i]

                        # Extract the actual value from the Value oneof field
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
            else:
                return []
                
        except Exception as e:
            return self.handle_error(e, "执行查询") or []
    
    def execute_statement(self, db_name: str, sql: str, auto_qualify_tables: bool = True) -> int:
        """
        执行写操作 (INSERT/UPDATE/DELETE)

        Args:
            db_name: 数据库名称
            sql: SQL 语句
            auto_qualify_tables: 自动在 SQL 中添加 schema 前缀（默认: True）

        Returns:
            影响的行数
        """
        try:
            self._ensure_connected()

            # Auto-qualify table names in SQL if requested
            if auto_qualify_tables:
                sql = self._qualify_sql_tables(sql)

            request = duckdb_service_pb2.ExecuteStatementRequest(
                database_id=db_name,
                user_id=self.user_id,
                statement=sql,
            )

            response = self.stub.ExecuteStatement(request)

            if response.success:
                return response.affected_rows
            else:
                return 0

        except Exception as e:
            return self.handle_error(e, "执行语句") or 0
    
    # ========================================
    # 表管理
    # ========================================
    
    def create_table(self, db_name: str, table_name: str, schema: Dict[str, str]) -> bool:
        """
        创建表

        Args:
            db_name: 数据库名称
            table_name: 表名
            schema: 列定义 {'column_name': 'data_type'}

        Returns:
            是否成功
        """
        try:
            self._ensure_connected()
            columns = [
                duckdb_service_pb2.ColumnInfo(
                    name=name,
                    data_type=dtype,
                )
                for name, dtype in schema.items()
            ]

            request = duckdb_service_pb2.CreateTableRequest(
                database_id=db_name,
                user_id=self.user_id,
                table_name=table_name,
                columns=columns,
            )

            response = self.stub.CreateTable(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            return self.handle_error(e, "创建表") or False
    
    def list_tables(self, db_name: str) -> List[str]:
        """
        列出所有表

        Args:
            db_name: 数据库名称

        Returns:
            表名列表
        """
        try:
            self._ensure_connected()
            request = duckdb_service_pb2.ListTablesRequest(
                database_id=db_name,
                user_id=self.user_id,
            )

            response = self.stub.ListTables(request)

            if response.success:
                tables = [table.table_name for table in response.tables]
                return tables
            else:
                return []

        except Exception as e:
            return self.handle_error(e, "列出表") or []
    
    # ========================================
    # 数据导入/导出
    # ========================================
    
    def import_from_minio(self, db_name: str, table_name: str,
                         bucket: str, object_key: str,
                         file_format: str = 'parquet') -> bool:
        """
        从 MinIO 导入数据

        Args:
            db_name: 数据库名称
            table_name: 目标表名
            bucket: MinIO 桶名
            object_key: 对象键
            file_format: 文件格式 (parquet/csv/json)

        Returns:
            是否成功
        """
        try:
            self._ensure_connected()
            request = duckdb_service_pb2.ImportFromMinIORequest(
                database_id=db_name,
                user_id=self.user_id,
                table_name=table_name,
                bucket_name=bucket,
                object_key=object_key,
                format=file_format,
            )

            response = self.stub.ImportFromMinIO(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            return self.handle_error(e, "从MinIO导入") or False
    
    def query_minio_file(self, db_name: str, bucket: str,
                        object_key: str, file_format: str = 'parquet',
                        limit: int = 100) -> List[Dict]:
        """
        直接查询 MinIO 中的文件（无需导入）

        Args:
            db_name: 数据库名称
            bucket: MinIO 桶名 (base name, server will add user prefix)
            object_key: 对象键
            file_format: 文件格式
            limit: 返回结果限制

        Returns:
            查询结果
        """
        try:
            self._ensure_connected()
            # Build query with $FILE placeholder (server will replace with full s3:// path)
            query = f"SELECT * FROM $FILE LIMIT {limit}"

            request = duckdb_service_pb2.QueryMinIOFileRequest(
                database_id=db_name,
                user_id=self.user_id,
                bucket_name=bucket,
                object_key=object_key,
                format=file_format,
                query=query,
            )

            response = self.stub.QueryMinIOFile(request)

            if response.success:
                # 转换结果
                # Row contains repeated Value (list), need to combine with column names
                columns = list(response.columns)
                results = []

                for row_msg in response.rows:
                    row_dict = {}
                    # row_msg.values is a repeated field (list of Value messages)
                    for i, value in enumerate(row_msg.values):
                        if i >= len(columns):
                            break
                        col_name = columns[i]

                        # Extract the actual value from the Value oneof field
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
            else:
                return []

        except Exception as e:
            return self.handle_error(e, "查询MinIO文件") or []
    
    def export_to_minio(self, db_name: str, query: str, bucket: str,
                       object_key: str, file_format: str = 'parquet',
                       overwrite: bool = True, auto_qualify_tables: bool = True) -> Optional[Dict]:
        """
        导出查询结果到 MinIO (Critical for hot-to-cold data flow)

        Args:
            db_name: 数据库名称
            query: SQL 查询（结果将导出）
            bucket: MinIO 桶名
            object_key: 对象键
            file_format: 文件格式 (parquet/csv/json, default: parquet)
            overwrite: 是否覆盖已存在的文件
            auto_qualify_tables: 自动在 SQL 中添加 schema 前缀（默认: True）

        Returns:
            导出结果信息 {'success': bool, 'rows_exported': int, 'file_size': int}
        """
        try:
            self._ensure_connected()

            # Auto-qualify table names in query if requested
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

            response = self.stub.ExportToMinIO(request)

            if response.success:
                return {
                    'success': True,
                    'rows_exported': response.rows_exported,
                    'file_size': response.file_size,
                    'execution_time_ms': response.execution_time_ms
                }
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "导出到MinIO") or None

    def execute_batch(self, db_name: str, statements: List[str],
                     use_transaction: bool = True, auto_qualify_tables: bool = True) -> Optional[Dict]:
        """
        批量执行 SQL 语句 (Critical for efficient hot data operations)

        Args:
            db_name: 数据库名称
            statements: SQL 语句列表
            use_transaction: 是否在事务中执行
            auto_qualify_tables: 自动在 SQL 中添加表名前缀（默认: True）

        Returns:
            执行结果 {'success': bool, 'results': List[Dict]}
        """
        try:
            self._ensure_connected()

            # Auto-qualify table names in all statements if requested
            if auto_qualify_tables:
                statements = [self._qualify_sql_tables(stmt) for stmt in statements]

            request = duckdb_service_pb2.ExecuteBatchRequest(
                database_id=db_name,
                user_id=self.user_id,
                statements=statements,
                transaction=use_transaction,
            )

            response = self.stub.ExecuteBatch(request)

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
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "批量执行") or None

    def get_table_stats(self, db_name: str, table_name: str,
                       include_columns: bool = True) -> Optional[Dict]:
        """
        获取表统计信息 (Critical for understanding hot data characteristics)

        Args:
            db_name: 数据库名称
            table_name: 表名
            include_columns: 是否包含列统计

        Returns:
            统计信息 {'row_count': int, 'size_bytes': int, 'column_stats': List[Dict]}
        """
        try:
            self._ensure_connected()
            request = duckdb_service_pb2.GetTableStatsRequest(
                database_id=db_name,
                user_id=self.user_id,
                table_name=table_name,
                include_columns=include_columns,
            )

            response = self.stub.GetTableStats(request)

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
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "获取表统计") or None

    def delete_database(self, db_name: str, delete_from_minio: bool = True,
                       force: bool = False) -> bool:
        """
        删除数据库 (Critical for hot data lifecycle management)

        Args:
            db_name: 数据库名称
            delete_from_minio: 是否从 MinIO 删除文件
            force: 强制删除（忽略错误）

        Returns:
            是否成功
        """
        try:
            self._ensure_connected()
            request = duckdb_service_pb2.DeleteDatabaseRequest(
                database_id=db_name,
                user_id=self.user_id,
                delete_from_minio=delete_from_minio,
                force=force,
            )

            response = self.stub.DeleteDatabase(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            return self.handle_error(e, "删除数据库") or False

    def drop_table(self, db_name: str, table_name: str,
                  if_exists: bool = True, cascade: bool = False) -> bool:
        """
        删除表 (For managing hot data lifecycle)

        Args:
            db_name: 数据库名称
            table_name: 表名
            if_exists: 如果不存在不报错
            cascade: 级联删除依赖对象

        Returns:
            是否成功
        """
        try:
            self._ensure_connected()
            request = duckdb_service_pb2.DropTableRequest(
                database_id=db_name,
                user_id=self.user_id,
                table_name=table_name,
                if_exists=if_exists,
                cascade=cascade,
            )

            response = self.stub.DropTable(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            return self.handle_error(e, "删除表") or False

    def get_table_schema(self, db_name: str, table_name: str) -> Optional[Dict]:
        """
        获取表结构 (For introspection when selecting hot data)

        Args:
            db_name: 数据库名称
            table_name: 表名

        Returns:
            表结构信息 {'columns': List[Dict], 'row_count': int}
        """
        try:
            self._ensure_connected()
            request = duckdb_service_pb2.GetTableSchemaRequest(
                database_id=db_name,
                user_id=self.user_id,
                table_name=table_name,
            )

            response = self.stub.GetTableSchema(request)

            if response.success:
                columns = []
                for col in response.table_info.columns:
                    columns.append({
                        'name': col.name,
                        'data_type': col.data_type,
                        'nullable': col.nullable,
                        'is_primary_key': col.is_primary_key,
                    })

                schema = {
                    'table_name': response.table_info.table_name,
                    'columns': columns,
                    'row_count': response.table_info.row_count,
                    'size_bytes': response.table_info.size_bytes,
                }

                return schema
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "获取表结构") or None

    def get_database_info(self, db_name: str) -> Optional[Dict]:
        """
        获取数据库信息 (For monitoring hot data usage)

        Args:
            db_name: 数据库名称

        Returns:
            数据库信息 {'size_bytes': int, 'table_count': int, 'created_at': str}
        """
        try:
            self._ensure_connected()
            request = duckdb_service_pb2.GetDatabaseInfoRequest(
                database_id=db_name,
                user_id=self.user_id,
            )

            response = self.stub.GetDatabaseInfo(request)

            if response.success:
                info = {
                    'database_name': response.database_info.database_name,
                    'size_bytes': response.database_info.size_bytes,
                    'table_count': response.database_info.table_count,
                    'minio_bucket': response.database_info.minio_bucket,
                    'minio_path': response.database_info.minio_path,
                    'created_at': str(response.database_info.created_at),
                    'last_accessed': str(response.database_info.last_accessed),
                }

                return info
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "获取数据库信息") or None

    # ========================================
    # 健康检查
    # ========================================

    def health_check(self, detailed: bool = False) -> bool:
        """健康检查"""
        try:
            self._ensure_connected()
            request = duckdb_service_pb2.HealthCheckRequest(
                detailed=detailed,
            )
            
            response = self.stub.HealthCheck(request)

            if response.healthy:
                return True
            else:
                return False

        except Exception as e:
            return False


# 便捷使用示例
if __name__ == '__main__':
    # 使用 with 语句自动管理连接
    with DuckDBClient(host='localhost', port=50052, user_id='test_user') as client:
        # 健康检查
        client.health_check()
        
        # 数据库操作
        client.create_database('analytics', 'Analytics database')
        databases = client.list_databases()

        # 查询操作
        results = client.execute_query('analytics', 'SELECT * FROM users LIMIT 10')

