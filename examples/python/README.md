# Python 集成指南

## 文件名：`examples/python/README.md`

本指南介绍如何在 Python 服务（isA_MCP、isA_Model、isA_Agent）中使用 MinIO 和 DuckDB 基础服务。

## 快速开始

### 1. 安装依赖

```bash
pip install grpcio grpcio-tools
```

### 2. 生成 Python gRPC 代码

从 proto 文件生成 Python 代码：

```bash
cd /Users/xenodennis/Documents/Fun/isA_Cloud

# 生成 MinIO 服务的 Python 代码
python -m grpc_tools.protoc \
    -I./api/proto \
    --python_out=./examples/python \
    --grpc_python_out=./examples/python \
    api/proto/minio_service.proto \
    api/proto/common.proto

# 生成 DuckDB 服务的 Python 代码
python -m grpc_tools.protoc \
    -I./api/proto \
    --python_out=./examples/python \
    --grpc_python_out=./examples/python \
    api/proto/duckdb_service.proto \
    api/proto/common.proto
```

这将生成以下文件：
- `minio_service_pb2.py` - MinIO protobuf 消息定义
- `minio_service_pb2_grpc.py` - MinIO gRPC 客户端/服务端代码
- `duckdb_service_pb2.py` - DuckDB protobuf 消息定义
- `duckdb_service_pb2_grpc.py` - DuckDB gRPC 客户端/服务端代码
- `common_pb2.py` - 通用消息定义

### 3. 使用客户端

```python
from storage_client_example import MinIOClient, DuckDBClient

# MinIO 客户端
minio_client = MinIOClient('localhost:50051')
minio_client.upload_file('my-bucket', 'test.txt', b'Hello World', 'user123')
minio_client.close()

# DuckDB 客户端
duckdb_client = DuckDBClient('localhost:50052')
db_id = duckdb_client.create_database('analytics', 'user123', 'org456')
duckdb_client.close()
```

## 在 isA_MCP 中集成

### 方法 1: 直接使用 gRPC 客户端

创建一个通用的存储客户端模块：

```python
# isA_MCP/src/infrastructure/storage_client.py

import grpc
from typing import Optional, List, Dict, Any
import minio_service_pb2
import minio_service_pb2_grpc
import duckdb_service_pb2
import duckdb_service_pb2_grpc


class StorageService:
    """统一的存储服务客户端
    
    整合 MinIO 和 DuckDB 服务，提供简单的接口给 MCP 服务使用
    """
    
    def __init__(self, minio_address: str, duckdb_address: str):
        # 创建 gRPC channels
        self.minio_channel = grpc.insecure_channel(minio_address)
        self.duckdb_channel = grpc.insecure_channel(duckdb_address)
        
        # 创建 stubs
        self.minio_stub = minio_service_pb2_grpc.MinIOServiceStub(self.minio_channel)
        self.duckdb_stub = duckdb_service_pb2_grpc.DuckDBServiceStub(self.duckdb_channel)
    
    # MinIO 操作
    def upload_file(self, bucket: str, key: str, data: bytes, user_id: str) -> bool:
        """上传文件到 MinIO"""
        def request_iterator():
            # 发送元数据
            yield minio_service_pb2.PutObjectRequest(
                metadata=minio_service_pb2.PutObjectMetadata(
                    bucket_name=bucket,
                    object_key=key,
                    user_id=user_id,
                    content_length=len(data)
                )
            )
            # 发送数据
            chunk_size = 1024 * 1024
            for i in range(0, len(data), chunk_size):
                yield minio_service_pb2.PutObjectRequest(
                    chunk_data=data[i:i+chunk_size]
                )
        
        response = self.minio_stub.PutObject(request_iterator())
        return response.success
    
    def download_file(self, bucket: str, key: str, user_id: str) -> bytes:
        """从 MinIO 下载文件"""
        request = minio_service_pb2.GetObjectRequest(
            bucket_name=bucket,
            object_key=key,
            user_id=user_id
        )
        
        chunks = []
        for response in self.minio_stub.GetObject(request):
            if response.HasField('chunk_data'):
                chunks.append(response.chunk_data)
        
        return b''.join(chunks)
    
    # DuckDB 操作
    def analyze_data(
        self,
        db_id: str,
        user_id: str,
        query: str
    ) -> List[Dict[str, Any]]:
        """执行数据分析查询"""
        request = duckdb_service_pb2.ExecuteQueryRequest(
            database_id=db_id,
            user_id=user_id,
            query=query
        )
        
        response = self.duckdb_stub.ExecuteQuery(request)
        
        # 转换结果为字典列表
        results = []
        for row in response.rows:
            row_dict = {}
            for i, col in enumerate(response.columns):
                row_dict[col] = self._convert_value(row.values[i])
            results.append(row_dict)
        
        return results
    
    def import_from_storage(
        self,
        db_id: str,
        user_id: str,
        table: str,
        bucket: str,
        key: str,
        format: str = 'parquet'
    ) -> int:
        """从 MinIO 导入数据到 DuckDB"""
        request = duckdb_service_pb2.ImportFromMinIORequest(
            database_id=db_id,
            user_id=user_id,
            table_name=table,
            bucket_name=bucket,
            object_key=key,
            format=format,
            create_table=True
        )
        
        response = self.duckdb_stub.ImportFromMinIO(request)
        return response.rows_imported
    
    def _convert_value(self, value):
        """转换 protobuf 值到 Python 类型"""
        if value.HasField('string_value'):
            return value.string_value
        elif value.HasField('int_value'):
            return value.int_value
        elif value.HasField('double_value'):
            return value.double_value
        elif value.HasField('bool_value'):
            return value.bool_value
        elif value.HasField('null_value'):
            return None
        return None
    
    def close(self):
        """关闭连接"""
        self.minio_channel.close()
        self.duckdb_channel.close()
```

### 方法 2: 创建服务层抽象

```python
# isA_MCP/src/services/data_service.py

from infrastructure.storage_client import StorageService
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class DataService:
    """数据服务层
    
    封装存储和分析逻辑，提供业务级别的接口
    """
    
    def __init__(self, storage_service: StorageService):
        self.storage = storage_service
    
    async def store_user_data(
        self,
        user_id: str,
        file_name: str,
        data: bytes
    ) -> bool:
        """存储用户数据"""
        try:
            bucket = f'user-{user_id}'
            success = self.storage.upload_file(bucket, file_name, data, user_id)
            
            if success:
                logger.info(f"Stored {file_name} for user {user_id}")
            return success
        except Exception as e:
            logger.error(f"Failed to store data: {e}")
            return False
    
    async def analyze_user_behavior(
        self,
        user_id: str,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """分析用户行为"""
        try:
            # 1. 确保用户数据已导入
            db_id = f'user-{user_id}-analytics'
            
            # 2. 执行分析查询
            query = f"""
                SELECT 
                    event_type,
                    COUNT(*) as count,
                    AVG(duration) as avg_duration
                FROM user_events
                WHERE date BETWEEN '{start_date}' AND '{end_date}'
                GROUP BY event_type
                ORDER BY count DESC
            """
            
            results = self.storage.analyze_data(db_id, user_id, query)
            
            logger.info(f"Analyzed {len(results)} event types for user {user_id}")
            return {
                'user_id': user_id,
                'period': f'{start_date} to {end_date}',
                'events': results
            }
        except Exception as e:
            logger.error(f"Failed to analyze behavior: {e}")
            return {}
    
    async def generate_report(
        self,
        user_id: str,
        report_type: str,
        parameters: Dict[str, Any]
    ) -> str:
        """生成报告并存储"""
        try:
            db_id = f'user-{user_id}-analytics'
            
            # 1. 执行查询生成报告数据
            query = self._build_report_query(report_type, parameters)
            results = self.storage.analyze_data(db_id, user_id, query)
            
            # 2. 格式化报告
            report_data = self._format_report(report_type, results)
            
            # 3. 导出到 MinIO
            bucket = f'user-{user_id}'
            report_key = f'reports/{report_type}_{parameters.get("date")}.json'
            
            import json
            report_bytes = json.dumps(report_data).encode()
            self.storage.upload_file(bucket, report_key, report_bytes, user_id)
            
            logger.info(f"Generated {report_type} report for user {user_id}")
            return report_key
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            return ''
    
    def _build_report_query(self, report_type: str, params: Dict) -> str:
        """构建报告查询"""
        # 根据报告类型构建不同的 SQL 查询
        queries = {
            'daily_summary': """
                SELECT date, COUNT(*) as events, SUM(value) as total
                FROM events
                WHERE date = '{date}'
                GROUP BY date
            """,
            'user_activity': """
                SELECT user_id, event_type, COUNT(*) as count
                FROM events
                WHERE date BETWEEN '{start_date}' AND '{end_date}'
                GROUP BY user_id, event_type
            """
        }
        
        query = queries.get(report_type, '')
        return query.format(**params)
    
    def _format_report(self, report_type: str, data: List[Dict]) -> Dict:
        """格式化报告数据"""
        return {
            'report_type': report_type,
            'generated_at': datetime.now().isoformat(),
            'data': data
        }
```

## 在 FastAPI 中使用

### 示例：MCP 服务端点

```python
# isA_MCP/src/api/endpoints/data.py

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from services.data_service import DataService
from dependencies import get_data_service

router = APIRouter(prefix='/api/v1/data', tags=['data'])


class UploadRequest(BaseModel):
    file_name: str
    data: str  # base64 编码


class AnalysisRequest(BaseModel):
    start_date: str
    end_date: str


@router.post('/upload')
async def upload_data(
    user_id: str,
    request: UploadRequest,
    data_service: DataService = Depends(get_data_service)
):
    """上传用户数据"""
    import base64
    
    try:
        data_bytes = base64.b64decode(request.data)
        success = await data_service.store_user_data(
            user_id,
            request.file_name,
            data_bytes
        )
        
        if success:
            return {'status': 'success', 'message': 'Data uploaded'}
        else:
            raise HTTPException(status_code=500, detail='Upload failed')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/analyze')
async def analyze_behavior(
    user_id: str,
    request: AnalysisRequest,
    data_service: DataService = Depends(get_data_service)
):
    """分析用户行为"""
    try:
        results = await data_service.analyze_user_behavior(
            user_id,
            request.start_date,
            request.end_date
        )
        
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/report/{report_type}')
async def generate_report(
    user_id: str,
    report_type: str,
    parameters: dict,
    data_service: DataService = Depends(get_data_service)
):
    """生成报告"""
    try:
        report_key = await data_service.generate_report(
            user_id,
            report_type,
            parameters
        )
        
        return {
            'status': 'success',
            'report_key': report_key,
            'message': f'Report {report_type} generated'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

## 配置

### 环境变量

在 `.env` 文件或环境变量中配置服务地址：

```bash
# MinIO Service
MINIO_GRPC_HOST=localhost
MINIO_GRPC_PORT=50051

# DuckDB Service
DUCKDB_GRPC_HOST=localhost
DUCKDB_GRPC_PORT=50052
```

### 依赖注入配置

```python
# isA_MCP/src/dependencies.py

from infrastructure.storage_client import StorageService
from services.data_service import DataService
import os

# 全局存储服务实例
_storage_service = None
_data_service = None


def get_storage_service() -> StorageService:
    """获取存储服务单例"""
    global _storage_service
    
    if _storage_service is None:
        minio_address = f"{os.getenv('MINIO_GRPC_HOST')}:{os.getenv('MINIO_GRPC_PORT')}"
        duckdb_address = f"{os.getenv('DUCKDB_GRPC_HOST')}:{os.getenv('DUCKDB_GRPC_PORT')}"
        
        _storage_service = StorageService(minio_address, duckdb_address)
    
    return _storage_service


def get_data_service() -> DataService:
    """获取数据服务单例"""
    global _data_service
    
    if _data_service is None:
        storage_service = get_storage_service()
        _data_service = DataService(storage_service)
    
    return _data_service
```

## 测试

### 单元测试示例

```python
# tests/test_storage_client.py

import pytest
from unittest.mock import Mock, patch
from infrastructure.storage_client import StorageService


class TestStorageService:
    @pytest.fixture
    def storage_service(self):
        with patch('grpc.insecure_channel'):
            service = StorageService('localhost:50051', 'localhost:50052')
            yield service
            service.close()
    
    def test_upload_file(self, storage_service):
        """测试文件上传"""
        # Mock gRPC response
        storage_service.minio_stub.PutObject = Mock(
            return_value=Mock(success=True)
        )
        
        result = storage_service.upload_file(
            'test-bucket',
            'test.txt',
            b'test data',
            'user123'
        )
        
        assert result is True
    
    def test_analyze_data(self, storage_service):
        """测试数据分析"""
        # Mock gRPC response
        mock_response = Mock()
        mock_response.columns = ['id', 'name']
        mock_response.rows = []
        
        storage_service.duckdb_stub.ExecuteQuery = Mock(
            return_value=mock_response
        )
        
        results = storage_service.analyze_data(
            'db123',
            'user123',
            'SELECT * FROM users'
        )
        
        assert isinstance(results, list)
```

## 性能优化

### 1. 连接池管理

```python
class StorageServicePool:
    """gRPC 连接池"""
    
    def __init__(self, minio_address: str, duckdb_address: str, pool_size: int = 10):
        self.pool_size = pool_size
        self.minio_channels = []
        self.duckdb_channels = []
        
        for _ in range(pool_size):
            self.minio_channels.append(grpc.insecure_channel(minio_address))
            self.duckdb_channels.append(grpc.insecure_channel(duckdb_address))
    
    def get_minio_stub(self):
        """获取 MinIO stub"""
        channel = random.choice(self.minio_channels)
        return minio_service_pb2_grpc.MinIOServiceStub(channel)
    
    def get_duckdb_stub(self):
        """获取 DuckDB stub"""
        channel = random.choice(self.duckdb_channels)
        return duckdb_service_pb2_grpc.DuckDBServiceStub(channel)
```

### 2. 异步操作

```python
import asyncio
import grpc.aio


class AsyncStorageService:
    """异步存储服务客户端"""
    
    def __init__(self, minio_address: str, duckdb_address: str):
        self.minio_channel = grpc.aio.insecure_channel(minio_address)
        self.duckdb_channel = grpc.aio.insecure_channel(duckdb_address)
        
        self.minio_stub = minio_service_pb2_grpc.MinIOServiceStub(self.minio_channel)
        self.duckdb_stub = duckdb_service_pb2_grpc.DuckDBServiceStub(self.duckdb_channel)
    
    async def upload_file(self, bucket: str, key: str, data: bytes, user_id: str) -> bool:
        """异步上传文件"""
        # 实现异步上传逻辑
        pass
    
    async def analyze_data(self, db_id: str, user_id: str, query: str) -> List[Dict]:
        """异步数据分析"""
        # 实现异步查询逻辑
        pass
```

## 错误处理

```python
from grpc import StatusCode, RpcError


def handle_grpc_error(func):
    """gRPC 错误处理装饰器"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RpcError as e:
            if e.code() == StatusCode.UNAVAILABLE:
                logger.error("Service unavailable")
                raise ServiceUnavailableError("Storage service is unavailable")
            elif e.code() == StatusCode.PERMISSION_DENIED:
                logger.error("Permission denied")
                raise PermissionDeniedError("Access denied")
            else:
                logger.error(f"gRPC error: {e.details()}")
                raise StorageError(f"Storage operation failed: {e.details()}")
    return wrapper
```

## 相关文档

- [存储架构文档](../../docs/STORAGE_ARCHITECTURE.md)
- [MinIO SDK 文档](../../pkg/storage/minio/README.md)
- [DuckDB SDK 文档](../../pkg/analytics/duckdb/README.md)
- [gRPC Python 教程](https://grpc.io/docs/languages/python/)



