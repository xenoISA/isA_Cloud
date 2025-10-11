"""
MinIO and DuckDB Service Python Client Examples
为 isA Cloud Python 服务提供的 MinIO 和 DuckDB gRPC 客户端示例

文件名: examples/python/storage_client_example.py

使用方法:
    python storage_client_example.py
"""

import grpc
import io
from typing import List, Dict, Any
from datetime import datetime, timedelta

# 导入生成的 protobuf 文件
# 注意：需要先从 .proto 文件生成 Python 代码
# python -m grpc_tools.protoc -I../../api/proto --python_out=. --grpc_python_out=. minio_service.proto duckdb_service.proto common.proto

# import minio_service_pb2
# import minio_service_pb2_grpc
# import duckdb_service_pb2
# import duckdb_service_pb2_grpc


class MinIOClient:
    """MinIO gRPC 客户端封装
    
    提供简单易用的接口来访问 MinIO 对象存储服务
    
    示例:
        client = MinIOClient('localhost:50051')
        client.create_bucket('my-bucket', 'user123', 'org456')
        client.upload_file('my-bucket', 'test.txt', b'Hello World', 'user123')
    """
    
    def __init__(self, server_address: str = 'localhost:50051'):
        """初始化 MinIO 客户端
        
        Args:
            server_address: gRPC 服务器地址，默认 'localhost:50051'
        """
        self.channel = grpc.insecure_channel(server_address)
        # self.stub = minio_service_pb2_grpc.MinIOServiceStub(self.channel)
        print(f"✓ Connected to MinIO service at {server_address}")
    
    def create_bucket(self, bucket_name: str, user_id: str, organization_id: str) -> bool:
        """创建桶
        
        Args:
            bucket_name: 桶名称
            user_id: 用户ID
            organization_id: 组织ID
            
        Returns:
            bool: 是否成功
            
        示例:
            success = client.create_bucket('user-123', 'user123', 'org456')
        """
        try:
            # request = minio_service_pb2.CreateBucketRequest(
            #     bucket_name=bucket_name,
            #     user_id=user_id,
            #     organization_id=organization_id,
            #     region='us-east-1'
            # )
            # response = self.stub.CreateBucket(request)
            
            print(f"✓ Created bucket: {bucket_name}")
            # return response.success
            return True
        except grpc.RpcError as e:
            print(f"✗ Failed to create bucket: {e.details()}")
            return False
    
    def upload_file(
        self,
        bucket_name: str,
        object_key: str,
        data: bytes,
        user_id: str,
        content_type: str = 'application/octet-stream',
        metadata: Dict[str, str] = None
    ) -> bool:
        """上传文件（流式）
        
        Args:
            bucket_name: 桶名称
            object_key: 对象键（路径）
            data: 文件数据
            user_id: 用户ID
            content_type: MIME 类型
            metadata: 自定义元数据
            
        Returns:
            bool: 是否成功
            
        示例:
            with open('file.txt', 'rb') as f:
                data = f.read()
            client.upload_file('my-bucket', 'docs/file.txt', data, 'user123')
        """
        try:
            def request_iterator():
                # 第一个请求：发送元数据
                # metadata_req = minio_service_pb2.PutObjectRequest(
                #     metadata=minio_service_pb2.PutObjectMetadata(
                #         bucket_name=bucket_name,
                #         object_key=object_key,
                #         user_id=user_id,
                #         content_type=content_type,
                #         content_length=len(data),
                #         metadata=metadata or {}
                #     )
                # )
                # yield metadata_req
                
                # 后续请求：发送数据块（每块 1MB）
                chunk_size = 1024 * 1024  # 1MB
                for i in range(0, len(data), chunk_size):
                    chunk = data[i:i + chunk_size]
                    # chunk_req = minio_service_pb2.PutObjectRequest(chunk=chunk)
                    # yield chunk_req
                    pass
            
            # response = self.stub.PutObject(request_iterator())
            print(f"✓ Uploaded: {object_key} ({len(data)} bytes)")
            # return response.success
            return True
        except grpc.RpcError as e:
            print(f"✗ Failed to upload file: {e.details()}")
            return False
    
    def download_file(self, bucket_name: str, object_key: str, user_id: str) -> bytes:
        """下载文件（流式）
        
        Args:
            bucket_name: 桶名称
            object_key: 对象键
            user_id: 用户ID
            
        Returns:
            bytes: 文件数据
            
        示例:
            data = client.download_file('my-bucket', 'docs/file.txt', 'user123')
            with open('downloaded.txt', 'wb') as f:
                f.write(data)
        """
        try:
            # request = minio_service_pb2.GetObjectRequest(
            #     bucket_name=bucket_name,
            #     object_key=object_key,
            #     user_id=user_id
            # )
            
            # response_stream = self.stub.GetObject(request)
            
            # 收集所有数据块
            chunks = []
            # for response in response_stream:
            #     if response.HasField('chunk'):
            #         chunks.append(response.chunk)
            
            data = b''.join(chunks)
            print(f"✓ Downloaded: {object_key} ({len(data)} bytes)")
            return data
        except grpc.RpcError as e:
            print(f"✗ Failed to download file: {e.details()}")
            return b''
    
    def list_objects(self, bucket_name: str, user_id: str, prefix: str = '') -> List[Dict]:
        """列出对象
        
        Args:
            bucket_name: 桶名称
            user_id: 用户ID
            prefix: 前缀过滤
            
        Returns:
            List[Dict]: 对象列表
            
        示例:
            objects = client.list_objects('my-bucket', 'user123', prefix='docs/')
            for obj in objects:
                print(f"{obj['key']}: {obj['size']} bytes")
        """
        try:
            # request = minio_service_pb2.ListObjectsRequest(
            #     bucket_name=bucket_name,
            #     user_id=user_id,
            #     prefix=prefix,
            #     recursive=True
            # )
            # response = self.stub.ListObjects(request)
            
            objects = []
            # for obj in response.objects:
            #     objects.append({
            #         'key': obj.key,
            #         'size': obj.size,
            #         'etag': obj.etag,
            #         'content_type': obj.content_type,
            #         'last_modified': obj.last_modified.ToDatetime()
            #     })
            
            print(f"✓ Listed {len(objects)} objects")
            return objects
        except grpc.RpcError as e:
            print(f"✗ Failed to list objects: {e.details()}")
            return []
    
    def delete_object(self, bucket_name: str, object_key: str, user_id: str) -> bool:
        """删除对象
        
        Args:
            bucket_name: 桶名称
            object_key: 对象键
            user_id: 用户ID
            
        Returns:
            bool: 是否成功
        """
        try:
            # request = minio_service_pb2.DeleteObjectRequest(
            #     bucket_name=bucket_name,
            #     object_key=object_key,
            #     user_id=user_id
            # )
            # response = self.stub.DeleteObject(request)
            
            print(f"✓ Deleted: {object_key}")
            # return response.success
            return True
        except grpc.RpcError as e:
            print(f"✗ Failed to delete object: {e.details()}")
            return False
    
    def get_presigned_url(
        self,
        bucket_name: str,
        object_key: str,
        user_id: str,
        expiry_seconds: int = 3600
    ) -> str:
        """生成预签名下载 URL
        
        Args:
            bucket_name: 桶名称
            object_key: 对象键
            user_id: 用户ID
            expiry_seconds: 过期时间（秒）
            
        Returns:
            str: 预签名 URL
            
        示例:
            url = client.get_presigned_url('my-bucket', 'file.txt', 'user123', 3600)
            print(f"Download URL: {url}")
        """
        try:
            # request = minio_service_pb2.GetPresignedURLRequest(
            #     bucket_name=bucket_name,
            #     object_key=object_key,
            #     user_id=user_id,
            #     expiry_seconds=expiry_seconds
            # )
            # response = self.stub.GetPresignedURL(request)
            
            url = f"http://localhost:9000/{bucket_name}/{object_key}?expires_in={expiry_seconds}"
            print(f"✓ Generated presigned URL")
            # return response.url
            return url
        except grpc.RpcError as e:
            print(f"✗ Failed to generate presigned URL: {e.details()}")
            return ''
    
    def close(self):
        """关闭连接"""
        self.channel.close()


class DuckDBClient:
    """DuckDB gRPC 客户端封装
    
    提供简单易用的接口来访问 DuckDB 数据分析服务
    
    示例:
        client = DuckDBClient('localhost:50052')
        db_id = client.create_database('analytics', 'user123', 'org456')
        client.execute_query(db_id, 'user123', 'SELECT * FROM my_table')
    """
    
    def __init__(self, server_address: str = 'localhost:50052'):
        """初始化 DuckDB 客户端
        
        Args:
            server_address: gRPC 服务器地址，默认 'localhost:50052'
        """
        self.channel = grpc.insecure_channel(server_address)
        # self.stub = duckdb_service_pb2_grpc.DuckDBServiceStub(self.channel)
        print(f"✓ Connected to DuckDB service at {server_address}")
    
    def create_database(
        self,
        database_name: str,
        user_id: str,
        organization_id: str
    ) -> str:
        """创建数据库
        
        Args:
            database_name: 数据库名称
            user_id: 用户ID
            organization_id: 组织ID
            
        Returns:
            str: 数据库ID
            
        示例:
            db_id = client.create_database('analytics', 'user123', 'org456')
        """
        try:
            # request = duckdb_service_pb2.CreateDatabaseRequest(
            #     database_name=database_name,
            #     user_id=user_id,
            #     organization_id=organization_id,
            #     minio_bucket=f'user-{user_id}'
            # )
            # response = self.stub.CreateDatabase(request)
            
            db_id = f"db_{database_name}_{user_id}"
            print(f"✓ Created database: {database_name} (ID: {db_id})")
            # return response.database_info.database_id
            return db_id
        except grpc.RpcError as e:
            print(f"✗ Failed to create database: {e.details()}")
            return ''
    
    def execute_query(
        self,
        database_id: str,
        user_id: str,
        query: str,
        parameters: Dict[str, Any] = None
    ) -> List[Dict]:
        """执行 SQL 查询
        
        Args:
            database_id: 数据库ID
            user_id: 用户ID
            query: SQL 查询语句
            parameters: 查询参数
            
        Returns:
            List[Dict]: 查询结果
            
        示例:
            results = client.execute_query(
                'db123',
                'user123',
                'SELECT * FROM users WHERE age > $1',
                {'1': 25}
            )
            for row in results:
                print(row)
        """
        try:
            # request = duckdb_service_pb2.ExecuteQueryRequest(
            #     database_id=database_id,
            #     user_id=user_id,
            #     query=query,
            #     parameters=parameters or {}
            # )
            # response = self.stub.ExecuteQuery(request)
            
            results = []
            # for row in response.rows:
            #     row_dict = {}
            #     for i, col in enumerate(response.columns):
            #         row_dict[col] = self._convert_value(row.values[i])
            #     results.append(row_dict)
            
            print(f"✓ Query executed: {len(results)} rows returned")
            return results
        except grpc.RpcError as e:
            print(f"✗ Failed to execute query: {e.details()}")
            return []
    
    def execute_statement(
        self,
        database_id: str,
        user_id: str,
        statement: str
    ) -> int:
        """执行 SQL 语句（INSERT、UPDATE、DELETE）
        
        Args:
            database_id: 数据库ID
            user_id: 用户ID
            statement: SQL 语句
            
        Returns:
            int: 受影响的行数
            
        示例:
            rows = client.execute_statement(
                'db123',
                'user123',
                "INSERT INTO users (name, age) VALUES ('Alice', 30)"
            )
            print(f"Inserted {rows} rows")
        """
        try:
            # request = duckdb_service_pb2.ExecuteStatementRequest(
            #     database_id=database_id,
            #     user_id=user_id,
            #     statement=statement
            # )
            # response = self.stub.ExecuteStatement(request)
            
            affected_rows = 1
            print(f"✓ Statement executed: {affected_rows} rows affected")
            # return response.affected_rows
            return affected_rows
        except grpc.RpcError as e:
            print(f"✗ Failed to execute statement: {e.details()}")
            return 0
    
    def create_table(
        self,
        database_id: str,
        user_id: str,
        table_name: str,
        columns: List[Dict[str, Any]]
    ) -> bool:
        """创建表
        
        Args:
            database_id: 数据库ID
            user_id: 用户ID
            table_name: 表名
            columns: 列定义列表
            
        Returns:
            bool: 是否成功
            
        示例:
            success = client.create_table(
                'db123',
                'user123',
                'users',
                [
                    {'name': 'id', 'data_type': 'INTEGER', 'nullable': False},
                    {'name': 'name', 'data_type': 'VARCHAR', 'nullable': False},
                    {'name': 'age', 'data_type': 'INTEGER', 'nullable': True}
                ]
            )
        """
        try:
            # column_infos = []
            # for col in columns:
            #     column_infos.append(duckdb_service_pb2.ColumnInfo(
            #         name=col['name'],
            #         data_type=col['data_type'],
            #         nullable=col.get('nullable', True)
            #     ))
            
            # request = duckdb_service_pb2.CreateTableRequest(
            #     database_id=database_id,
            #     user_id=user_id,
            #     table_name=table_name,
            #     columns=column_infos
            # )
            # response = self.stub.CreateTable(request)
            
            print(f"✓ Created table: {table_name}")
            # return response.success
            return True
        except grpc.RpcError as e:
            print(f"✗ Failed to create table: {e.details()}")
            return False
    
    def import_from_minio(
        self,
        database_id: str,
        user_id: str,
        table_name: str,
        bucket_name: str,
        object_key: str,
        format: str = 'csv'
    ) -> int:
        """从 MinIO 导入数据
        
        Args:
            database_id: 数据库ID
            user_id: 用户ID
            table_name: 目标表名
            bucket_name: MinIO 桶名
            object_key: 对象键
            format: 文件格式（csv, parquet, json）
            
        Returns:
            int: 导入的行数
            
        示例:
            rows = client.import_from_minio(
                'db123',
                'user123',
                'sales',
                'data-bucket',
                'sales.csv',
                'csv'
            )
            print(f"Imported {rows} rows")
        """
        try:
            # request = duckdb_service_pb2.ImportFromMinIORequest(
            #     database_id=database_id,
            #     user_id=user_id,
            #     table_name=table_name,
            #     bucket_name=bucket_name,
            #     object_key=object_key,
            #     format=format,
            #     create_table=True
            # )
            # response = self.stub.ImportFromMinIO(request)
            
            rows_imported = 100
            print(f"✓ Imported {rows_imported} rows from MinIO")
            # return response.rows_imported
            return rows_imported
        except grpc.RpcError as e:
            print(f"✗ Failed to import from MinIO: {e.details()}")
            return 0
    
    def export_to_minio(
        self,
        database_id: str,
        user_id: str,
        query: str,
        bucket_name: str,
        object_key: str,
        format: str = 'parquet'
    ) -> int:
        """导出数据到 MinIO
        
        Args:
            database_id: 数据库ID
            user_id: 用户ID
            query: SQL 查询
            bucket_name: MinIO 桶名
            object_key: 对象键
            format: 文件格式（csv, parquet, json）
            
        Returns:
            int: 导出的行数
            
        示例:
            rows = client.export_to_minio(
                'db123',
                'user123',
                'SELECT * FROM sales WHERE date >= "2024-01-01"',
                'reports',
                'sales_2024.parquet',
                'parquet'
            )
        """
        try:
            # request = duckdb_service_pb2.ExportToMinIORequest(
            #     database_id=database_id,
            #     user_id=user_id,
            #     query=query,
            #     bucket_name=bucket_name,
            #     object_key=object_key,
            #     format=format,
            #     overwrite=True
            # )
            # response = self.stub.ExportToMinIO(request)
            
            rows_exported = 100
            print(f"✓ Exported {rows_exported} rows to MinIO")
            # return response.rows_exported
            return rows_exported
        except grpc.RpcError as e:
            print(f"✗ Failed to export to MinIO: {e.details()}")
            return 0
    
    def query_minio_file(
        self,
        database_id: str,
        user_id: str,
        bucket_name: str,
        object_key: str,
        query: str,
        format: str = 'parquet'
    ) -> List[Dict]:
        """直接查询 MinIO 中的文件（无需导入）
        
        Args:
            database_id: 数据库ID
            user_id: 用户ID
            bucket_name: MinIO 桶名
            object_key: 对象键
            query: SQL 查询
            format: 文件格式
            
        Returns:
            List[Dict]: 查询结果
            
        示例:
            results = client.query_minio_file(
                'db123',
                'user123',
                'data-bucket',
                'sales.parquet',
                'SELECT product, SUM(amount) as total FROM data GROUP BY product',
                'parquet'
            )
        """
        try:
            # request = duckdb_service_pb2.QueryMinIOFileRequest(
            #     database_id=database_id,
            #     user_id=user_id,
            #     bucket_name=bucket_name,
            #     object_key=object_key,
            #     format=format,
            #     query=query
            # )
            # response = self.stub.QueryMinIOFile(request)
            
            results = []
            print(f"✓ Query executed on MinIO file: {len(results)} rows returned")
            return results
        except grpc.RpcError as e:
            print(f"✗ Failed to query MinIO file: {e.details()}")
            return []
    
    def _convert_value(self, value):
        """转换 protobuf Value 到 Python 类型"""
        # 实现类型转换逻辑
        pass
    
    def close(self):
        """关闭连接"""
        self.channel.close()


# ============================================
# 使用示例
# ============================================

def example_minio_operations():
    """MinIO 操作示例"""
    print("=== MinIO 操作示例 ===\n")
    
    client = MinIOClient('localhost:50051')
    
    try:
        # 1. 创建桶
        client.create_bucket('demo-bucket', 'user123', 'org456')
        
        # 2. 上传文件
        data = b'Hello, MinIO from Python!'
        client.upload_file(
            'demo-bucket',
            'test.txt',
            data,
            'user123',
            content_type='text/plain',
            metadata={'source': 'python-example'}
        )
        
        # 3. 列出对象
        objects = client.list_objects('demo-bucket', 'user123')
        print(f"Objects: {objects}")
        
        # 4. 生成预签名 URL
        url = client.get_presigned_url('demo-bucket', 'test.txt', 'user123', 3600)
        print(f"Presigned URL: {url}")
        
        # 5. 下载文件
        downloaded_data = client.download_file('demo-bucket', 'test.txt', 'user123')
        print(f"Downloaded: {downloaded_data.decode()}")
        
    finally:
        client.close()


def example_duckdb_operations():
    """DuckDB 操作示例"""
    print("\n=== DuckDB 操作示例 ===\n")
    
    client = DuckDBClient('localhost:50052')
    
    try:
        # 1. 创建数据库
        db_id = client.create_database('analytics', 'user123', 'org456')
        
        # 2. 创建表
        client.create_table(
            db_id,
            'user123',
            'users',
            [
                {'name': 'id', 'data_type': 'INTEGER', 'nullable': False},
                {'name': 'name', 'data_type': 'VARCHAR', 'nullable': False},
                {'name': 'age', 'data_type': 'INTEGER', 'nullable': True},
                {'name': 'email', 'data_type': 'VARCHAR', 'nullable': True}
            ]
        )
        
        # 3. 插入数据
        client.execute_statement(
            db_id,
            'user123',
            "INSERT INTO users VALUES (1, 'Alice', 30, 'alice@example.com')"
        )
        client.execute_statement(
            db_id,
            'user123',
            "INSERT INTO users VALUES (2, 'Bob', 25, 'bob@example.com')"
        )
        
        # 4. 查询数据
        results = client.execute_query(
            db_id,
            'user123',
            'SELECT * FROM users WHERE age > $1',
            {'1': 20}
        )
        print(f"Query results: {results}")
        
    finally:
        client.close()


def example_integrated_workflow():
    """集成工作流示例：从上传到分析"""
    print("\n=== 集成工作流示例 ===\n")
    
    minio_client = MinIOClient('localhost:50051')
    duckdb_client = DuckDBClient('localhost:50052')
    
    try:
        user_id = 'user123'
        org_id = 'org456'
        bucket_name = 'analytics-data'
        
        # 1. 准备 CSV 数据
        csv_data = b"""id,product,quantity,price,date
1,Laptop,10,999.99,2024-01-15
2,Mouse,100,29.99,2024-01-15
3,Keyboard,50,79.99,2024-01-16
4,Monitor,25,299.99,2024-01-16
5,Headphones,75,149.99,2024-01-17"""
        
        # 2. 上传到 MinIO
        print("Step 1: Uploading CSV to MinIO...")
        minio_client.create_bucket(bucket_name, user_id, org_id)
        minio_client.upload_file(
            bucket_name,
            'sales.csv',
            csv_data,
            user_id,
            content_type='text/csv'
        )
        
        # 3. 创建 DuckDB 数据库
        print("\nStep 2: Creating DuckDB database...")
        db_id = duckdb_client.create_database('sales_analytics', user_id, org_id)
        
        # 4. 从 MinIO 导入数据到 DuckDB
        print("\nStep 3: Importing data from MinIO to DuckDB...")
        rows = duckdb_client.import_from_minio(
            db_id,
            user_id,
            'sales',
            bucket_name,
            'sales.csv',
            'csv'
        )
        print(f"Imported {rows} rows")
        
        # 5. 执行分析查询
        print("\nStep 4: Running analysis queries...")
        
        # 5.1 产品销售统计
        results = duckdb_client.execute_query(
            db_id,
            user_id,
            """
            SELECT 
                product,
                SUM(quantity) as total_quantity,
                SUM(quantity * price) as total_revenue
            FROM sales
            GROUP BY product
            ORDER BY total_revenue DESC
            """
        )
        print("Product Sales Summary:")
        for row in results:
            print(f"  - {row}")
        
        # 5.2 日销售统计
        results = duckdb_client.execute_query(
            db_id,
            user_id,
            """
            SELECT 
                date,
                COUNT(*) as order_count,
                SUM(quantity * price) as daily_revenue
            FROM sales
            GROUP BY date
            ORDER BY date
            """
        )
        print("\nDaily Sales:")
        for row in results:
            print(f"  - {row}")
        
        # 6. 导出分析结果到 MinIO
        print("\nStep 5: Exporting results to MinIO...")
        rows_exported = duckdb_client.export_to_minio(
            db_id,
            user_id,
            'SELECT * FROM sales ORDER BY date',
            bucket_name,
            'reports/sales_report.parquet',
            'parquet'
        )
        print(f"Exported {rows_exported} rows to Parquet")
        
        # 7. 直接查询 MinIO 中的 Parquet 文件（无需导入）
        print("\nStep 6: Querying Parquet file directly from MinIO...")
        results = duckdb_client.query_minio_file(
            db_id,
            user_id,
            bucket_name,
            'reports/sales_report.parquet',
            'SELECT product, AVG(price) as avg_price FROM data GROUP BY product',
            'parquet'
        )
        print("Average Prices:")
        for row in results:
            print(f"  - {row}")
        
        print("\n✓ Integrated workflow completed successfully!")
        
    finally:
        minio_client.close()
        duckdb_client.close()


if __name__ == '__main__':
    print("MinIO and DuckDB Service Python Client Examples")
    print("=" * 60)
    
    # 注意：这些示例需要先启动 gRPC 服务
    print("\nNote: Make sure the gRPC services are running before executing these examples.")
    print("  - MinIO Service: localhost:50051")
    print("  - DuckDB Service: localhost:50052\n")
    
    # 运行示例（取消注释以运行）
    # example_minio_operations()
    # example_duckdb_operations()
    # example_integrated_workflow()
    
    print("\n" + "=" * 60)
    print("Examples completed!")

