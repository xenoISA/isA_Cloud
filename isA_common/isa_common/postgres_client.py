#!/usr/bin/env python3
"""
PostgreSQL gRPC Client
PostgreSQL database client
"""

from typing import List, Dict, Optional, Any, TYPE_CHECKING
from google.protobuf.struct_pb2 import Struct, Value
from .base_client import BaseGRPCClient
from .proto import postgres_service_pb2, postgres_service_pb2_grpc

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry


class PostgresClient(BaseGRPCClient):
    """PostgreSQL gRPC client"""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, user_id: Optional[str] = None,
                 lazy_connect: bool = True, enable_compression: bool = True, enable_retry: bool = True,
                 consul_registry: Optional['ConsulRegistry'] = None, service_name_override: Optional[str] = None):
        """
        Initialize PostgreSQL client

        Args:
            host: Service address (optional, will use Consul discovery if not provided)
            port: Service port (optional, will use Consul discovery if not provided)
            user_id: User ID
            lazy_connect: Lazy connection (default: True)
            enable_compression: Enable compression (default: True)
            enable_retry: Enable retry (default: True)
            consul_registry: ConsulRegistry instance for service discovery (optional)
            service_name_override: Override service name for Consul lookup (optional, defaults to 'postgres')
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
        """Create PostgreSQL service stub"""
        return postgres_service_pb2_grpc.PostgresServiceStub(self.channel)

    def service_name(self) -> str:
        return "PostgreSQL"

    def default_port(self) -> int:
        return 50061

    def health_check(self, detailed: bool = True) -> Optional[Dict]:
        """Health check"""
        try:
            self._ensure_connected()
            request = postgres_service_pb2.HealthCheckRequest(detailed=detailed)
            response = self.stub.HealthCheck(request)

            return {
                'status': response.status,
                'healthy': response.healthy,
                'version': response.version,
                'details': dict(response.details) if response.details else {}
            }

        except Exception as e:
            return self.handle_error(e, "Health check")

    def query(self, sql: str, params: Optional[List[Any]] = None, schema: str = 'public') -> Optional[List[Dict]]:
        """Execute SELECT query

        Args:
            sql: SQL query statement
            params: Query parameters
            schema: Database schema (default: public)

        Returns:
            List of result rows as dictionaries
        """
        try:
            self._ensure_connected()

            # Convert parameters to proto Value
            proto_params = []
            if params:
                for param in params:
                    proto_params.append(self._python_to_proto_value(param))

            request = postgres_service_pb2.QueryRequest(
                sql=sql,
                params=proto_params,
                schema=schema
            )

            response = self.stub.Query(request)

            if response.metadata.success:
                rows = [dict(row) for row in response.rows]
                return rows
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Query")

    def query_row(self, sql: str, params: Optional[List[Any]] = None, schema: str = 'public') -> Optional[Dict]:
        """Execute single row query

        Args:
            sql: SQL query statement
            params: Query parameters
            schema: Database schema

        Returns:
            Single row as dictionary or None
        """
        try:
            self._ensure_connected()

            proto_params = []
            if params:
                for param in params:
                    proto_params.append(self._python_to_proto_value(param))

            request = postgres_service_pb2.QueryRowRequest(
                sql=sql,
                params=proto_params,
                schema=schema
            )

            response = self.stub.QueryRow(request)

            if response.metadata.success and response.found:
                row = dict(response.row)
                return row
            elif not response.found:
                return None
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Query row")

    def execute(self, sql: str, params: Optional[List[Any]] = None, schema: str = 'public') -> Optional[int]:
        """Execute INSERT/UPDATE/DELETE statement

        Args:
            sql: SQL statement
            params: Statement parameters
            schema: Database schema

        Returns:
            Number of rows affected
        """
        try:
            self._ensure_connected()

            proto_params = []
            if params:
                for param in params:
                    proto_params.append(self._python_to_proto_value(param))

            request = postgres_service_pb2.ExecuteRequest(
                sql=sql,
                params=proto_params,
                schema=schema
            )

            response = self.stub.Execute(request)

            if response.metadata.success:
                return response.rows_affected
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Execute")

    def execute_batch(self, operations: List[Dict[str, Any]], schema: str = 'public') -> Optional[Dict]:
        """Execute batch operations

        Args:
            operations: List of {'sql': str, 'params': List} dictionaries
            schema: Database schema

        Returns:
            Batch execution results
        """
        try:
            self._ensure_connected()

            batch_ops = []
            for op in operations:
                proto_params = []
                if 'params' in op and op['params']:
                    for param in op['params']:
                        proto_params.append(self._python_to_proto_value(param))

                batch_ops.append(postgres_service_pb2.BatchOperation(
                    sql=op['sql'],
                    params=proto_params
                ))

            request = postgres_service_pb2.ExecuteBatchRequest(
                operations=batch_ops,
                schema=schema
            )

            response = self.stub.ExecuteBatch(request)

            if response.metadata.success:
                return {
                    'total_rows_affected': response.total_rows_affected,
                    'results': [{'rows_affected': r.rows_affected, 'error': r.error} for r in response.results]
                }
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Execute batch")

    def select_from(self, table: str, columns: Optional[List[str]] = None, where: Optional[List[Dict]] = None,
                   order_by: Optional[List[str]] = None, limit: int = 0, offset: int = 0,
                   schema: str = 'public') -> Optional[List[Dict]]:
        """Query builder style SELECT

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
            self._ensure_connected()

            where_clauses = []
            if where:
                for w in where:
                    where_clauses.append(postgres_service_pb2.WhereClause(
                        column=w.get('column', ''),
                        operator=w.get('operator', '='),
                        value=self._python_to_proto_value(w.get('value'))
                    ))

            request = postgres_service_pb2.SelectFromRequest(
                table=table,
                columns=columns or [],
                where=where_clauses,
                order_by=order_by or [],
                limit=limit,
                offset=offset,
                schema=schema
            )

            response = self.stub.SelectFrom(request)

            if response.metadata.success:
                rows = [dict(row) for row in response.rows]
                return rows
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Select from")

    def insert_into(self, table: str, rows: List[Dict], returning: bool = False,
                   schema: str = 'public') -> Optional[int]:
        """Insert rows into table

        Args:
            table: Table name
            rows: List of row dictionaries to insert
            returning: Return inserted rows
            schema: Database schema

        Returns:
            Number of rows inserted
        """
        try:
            self._ensure_connected()

            proto_rows = []
            for row in rows:
                struct = Struct()
                # Use update() to properly handle all Python types
                struct.update(row)
                proto_rows.append(struct)

            request = postgres_service_pb2.InsertIntoRequest(
                table=table,
                rows=proto_rows,
                returning=returning,
                schema=schema
            )

            response = self.stub.InsertInto(request)

            if response.metadata.success:
                return response.rows_inserted
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Insert into")

    def list_tables(self, schema: str = 'public') -> List[str]:
        """List all tables in schema

        Args:
            schema: Database schema

        Returns:
            List of table names
        """
        try:
            self._ensure_connected()

            request = postgres_service_pb2.ListTablesRequest(schema=schema)
            response = self.stub.ListTables(request)

            if response.metadata.success:
                return list(response.tables)
            else:
                return []

        except Exception as e:
            self.handle_error(e, "List tables")
            return []

    def table_exists(self, table: str, schema: str = 'public') -> bool:
        """Check if table exists

        Args:
            table: Table name
            schema: Database schema

        Returns:
            True if table exists, False otherwise
        """
        try:
            self._ensure_connected()

            request = postgres_service_pb2.TableExistsRequest(
                table=table,
                schema=schema
            )
            response = self.stub.TableExists(request)

            if response.metadata.success:
                exists = response.exists
                return exists
            else:
                return False

        except Exception as e:
            self.handle_error(e, "Table exists check")
            return False

    def get_stats(self) -> Optional[Dict]:
        """Get connection pool and database statistics

        Returns:
            Statistics dictionary
        """
        try:
            self._ensure_connected()

            request = postgres_service_pb2.GetStatsRequest()
            response = self.stub.GetStats(request)

            if response.metadata.success:
                stats = {
                    'pool': {
                        'max_connections': response.pool_stats.max_connections,
                        'open_connections': response.pool_stats.open_connections,
                        'idle_connections': response.pool_stats.idle_connections,
                        'active_connections': response.pool_stats.active_connections,
                        'total_queries': response.pool_stats.total_queries,
                    },
                    'database': {
                        'version': response.db_stats.version,
                    }
                }
                return stats
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "Get stats")

    def _python_to_proto_value(self, value: Any) -> Value:
        """Convert Python value to proto Value"""
        proto_value = Value()

        if value is None:
            proto_value.null_value = 0
        elif isinstance(value, bool):
            proto_value.bool_value = value
        elif isinstance(value, (int, float)):
            proto_value.number_value = float(value)
        elif isinstance(value, str):
            proto_value.string_value = value
        elif isinstance(value, list):
            proto_value.list_value.values.extend([self._python_to_proto_value(v) for v in value])
        elif isinstance(value, dict):
            for k, v in value.items():
                proto_value.struct_value.fields[k].CopyFrom(self._python_to_proto_value(v))
        else:
            proto_value.string_value = str(value)

        return proto_value
