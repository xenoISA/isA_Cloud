#!/usr/bin/env python3
"""
Supabase gRPC Client
Supabase 数据库和向量搜索客户端
"""

import sys
from typing import List, Dict, Any, Optional
from google.protobuf import struct_pb2

from .base_client import BaseGRPCClient
from .proto import supabase_service_pb2, supabase_service_pb2_grpc, common_pb2


class SupabaseClient(BaseGRPCClient):
    """Supabase gRPC 客户端"""

    def __init__(self, host: str = 'localhost', port: int = 50057, user_id: Optional[str] = None,
                 lazy_connect: bool = True, enable_compression: bool = True, enable_retry: bool = True):
        """
        初始化 Supabase 客户端

        Args:
            host: 服务地址 (默认: localhost)
            port: 服务端口 (默认: 50057)
            user_id: 用户 ID
            lazy_connect: 延迟连接 (默认: True)
            enable_compression: 启用压缩 (默认: True)
            enable_retry: 启用重试 (默认: True)
        """
        super().__init__(host, port, user_id, lazy_connect, enable_compression, enable_retry)
    
    def _create_stub(self):
        """创建 Supabase service stub"""
        return supabase_service_pb2_grpc.SupabaseServiceStub(self.channel)
    
    def service_name(self) -> str:
        return "Supabase"
    
    def _create_metadata(self, org_id: str = 'default_org') -> common_pb2.RequestMetadata:
        """创建请求元数据"""
        return common_pb2.RequestMetadata(
            user_id=self.user_id,
            organization_id=org_id,
            access_token=self.user_id,  # 简化，实际应该是 JWT
            request_id=f'req_{id(self)}',
        )
    
    # ========================================
    # 数据库操作
    # ========================================
    
    def query(self, table: str, select: str = '*', filter: str = '',
              limit: int = 10, order: str = '') -> List[Dict]:
        """
        查询数据

        Args:
            table: 表名
            select: 选择字段
            filter: 过滤条件 (PostgREST 语法)
            limit: 限制数量
            order: 排序

        Returns:
            查询结果列表
        """
        try:
            self._ensure_connected()
            request = supabase_service_pb2.QueryRequest(
                metadata=self._create_metadata(),
                table=table,
                select=select,
                filter=filter,
                limit=limit,
                order=order,
            )
            
            response = self.stub.Query(request)
            
            if response.metadata.success:
                print(f"✅ [Supabase] 查询成功，返回 {len(response.data)} 条记录")
                return [dict(item) for item in response.data]
            else:
                print(f"❌ [Supabase] 查询失败: {response.metadata.error}")
                return []
                
        except Exception as e:
            return self.handle_error(e, "查询")
    
    def insert(self, table: str, data: List[Dict]) -> List[Dict]:
        """
        插入数据

        Args:
            table: 表名
            data: 要插入的数据列表

        Returns:
            插入的数据
        """
        try:
            self._ensure_connected()
            # 转换为 protobuf Struct
            structs = []
            for item in data:
                s = struct_pb2.Struct()
                s.update(item)
                structs.append(s)
            
            request = supabase_service_pb2.InsertRequest(
                metadata=self._create_metadata(),
                table=table,
                data=structs,
                return_data=True,
            )
            
            response = self.stub.Insert(request)
            
            if response.metadata.success:
                print(f"✅ [Supabase] 插入成功，插入了 {response.count} 条记录")
                return [dict(item) for item in response.data]
            else:
                print(f"❌ [Supabase] 插入失败: {response.metadata.error}")
                return []
                
        except Exception as e:
            return self.handle_error(e, "插入")
    
    def update(self, table: str, data: Dict, filter: str = '') -> List[Dict]:
        """
        更新数据

        Args:
            table: 表名
            data: 要更新的数据
            filter: 过滤条件

        Returns:
            更新后的数据
        """
        try:
            self._ensure_connected()
            # 转换为 protobuf Struct
            s = struct_pb2.Struct()
            s.update(data)
            
            request = supabase_service_pb2.UpdateRequest(
                metadata=self._create_metadata(),
                table=table,
                data=s,
                filter=filter,
                return_data=True,
            )
            
            response = self.stub.Update(request)
            
            if response.metadata.success:
                print(f"✅ [Supabase] 更新成功，更新了 {response.count} 条记录")
                return [dict(item) for item in response.data]
            else:
                print(f"❌ [Supabase] 更新失败: {response.metadata.error}")
                return []
                
        except Exception as e:
            return self.handle_error(e, "更新")
    
    def delete(self, table: str, filter: str) -> List[Dict]:
        """
        删除数据

        Args:
            table: 表名
            filter: 过滤条件

        Returns:
            删除的数据
        """
        try:
            self._ensure_connected()
            request = supabase_service_pb2.DeleteRequest(
                metadata=self._create_metadata(),
                table=table,
                filter=filter,
                return_data=True,
            )
            
            response = self.stub.Delete(request)
            
            if response.metadata.success:
                print(f"✅ [Supabase] 删除成功，删除了 {response.count} 条记录")
                return [dict(item) for item in response.data]
            else:
                print(f"❌ [Supabase] 删除失败: {response.metadata.error}")
                return []
                
        except Exception as e:
            return self.handle_error(e, "删除")

    def upsert(self, table: str, data: List[Dict], on_conflict: str = 'id') -> List[Dict]:
        """
        插入或更新数据 (UPSERT)

        Args:
            table: 表名
            data: 要插入/更新的数据列表
            on_conflict: 冲突字段 (默认: 'id')

        Returns:
            插入/更新的数据
        """
        try:
            self._ensure_connected()
            # 转换为 protobuf Struct
            structs = []
            for item in data:
                s = struct_pb2.Struct()
                s.update(item)
                structs.append(s)
            
            request = supabase_service_pb2.UpsertRequest(
                metadata=self._create_metadata(),
                table=table,
                data=structs,
                on_conflict=on_conflict,
                return_data=True,
            )
            
            response = self.stub.Upsert(request)
            
            if response.metadata.success:
                print(f"✅ [Supabase] Upsert成功，影响了 {response.count} 条记录")
                return [dict(item) for item in response.data]
            else:
                print(f"❌ [Supabase] Upsert失败: {response.metadata.error}")
                return []
                
        except Exception as e:
            return self.handle_error(e, "Upsert")

    def execute_rpc(self, function_name: str, params: Dict = None) -> Any:
        """
        执行 PostgreSQL 存储过程/函数

        Args:
            function_name: 函数名
            params: 参数字典

        Returns:
            函数返回值
        """
        try:
            self._ensure_connected()
            # 转换参数为 protobuf Struct
            params_struct = struct_pb2.Struct()
            if params:
                params_struct.update(params)
            
            request = supabase_service_pb2.RPCRequest(
                metadata=self._create_metadata(),
                function_name=function_name,
                params=params_struct,
            )
            
            response = self.stub.ExecuteRPC(request)
            
            if response.metadata.success:
                print(f"✅ [Supabase] RPC调用成功: {function_name}()")
                # Convert protobuf Value to Python object
                return self._value_to_python(response.data)
            else:
                print(f"❌ [Supabase] RPC调用失败: {response.metadata.error}")
                return None
                
        except Exception as e:
            return self.handle_error(e, f"RPC调用 ({function_name})")

    def batch_insert(self, table: str, data: List[Dict], batch_size: int = 100) -> Dict:
        """
        批量插入数据

        Args:
            table: 表名
            data: 要插入的数据列表
            batch_size: 每批大小

        Returns:
            插入结果统计
        """
        try:
            self._ensure_connected()
            # 转换为 protobuf Struct
            structs = []
            for item in data:
                s = struct_pb2.Struct()
                s.update(item)
                structs.append(s)
            
            request = supabase_service_pb2.BatchInsertRequest(
                metadata=self._create_metadata(),
                table=table,
                data=structs,
                batch_size=batch_size,
            )
            
            response = self.stub.BatchInsert(request)
            
            if response.metadata.success:
                print(f"✅ [Supabase] 批量插入成功: {response.success_count}/{response.total_count}")
                if response.error_count > 0:
                    print(f"   ⚠️  错误: {response.error_count} 条记录失败")
                return {
                    'total_count': response.total_count,
                    'success_count': response.success_count,
                    'error_count': response.error_count,
                    'errors': list(response.errors)
                }
            else:
                print(f"❌ [Supabase] 批量插入失败: {response.metadata.error}")
                return {}
                
        except Exception as e:
            return self.handle_error(e, "批量插入") or {}

    def _value_to_python(self, value):
        """Convert protobuf Value to Python object"""
        from google.protobuf import json_format
        return json_format.MessageToDict(value)
    
    # ========================================
    # 向量操作 (pgvector)
    # ========================================
    
    def upsert_embedding(self, table: str, doc_id: str, embedding: List[float],
                         metadata: Optional[Dict] = None) -> Optional[str]:
        """
        插入或更新向量

        Args:
            table: 向量表名
            doc_id: 文档 ID
            embedding: 向量 (1536 维)
            metadata: 元数据

        Returns:
            文档 ID 或 None
        """
        try:
            self._ensure_connected()
            # 转换元数据
            meta_struct = struct_pb2.Struct()
            if metadata:
                meta_struct.update(metadata)
            
            request = supabase_service_pb2.UpsertEmbeddingRequest(
                metadata=self._create_metadata(),
                table=table,
                id=doc_id,
                embedding=embedding,
                metadata_json=meta_struct,
            )
            
            response = self.stub.UpsertEmbedding(request)
            
            if response.metadata.success:
                print(f"✅ [Supabase] 向量插入成功: {response.id}")
                return response.id
            else:
                print(f"❌ [Supabase] 向量插入失败: {response.metadata.error}")
                return None
                
        except Exception as e:
            return self.handle_error(e, "插入向量")
    
    def similarity_search(self, table: str, query_embedding: List[float],
                         limit: int = 10, filter: str = '',
                         threshold: float = 0.5) -> List[Dict]:
        """
        向量相似度搜索

        Args:
            table: 向量表名
            query_embedding: 查询向量
            limit: 返回数量
            filter: 元数据过滤
            threshold: 相似度阈值

        Returns:
            搜索结果列表
        """
        try:
            self._ensure_connected()
            request = supabase_service_pb2.SimilaritySearchRequest(
                metadata=self._create_metadata(),
                table=table,
                query_embedding=query_embedding,
                limit=limit,
                filter=filter,
                metric='cosine',
                threshold=threshold,
            )
            
            response = self.stub.SimilaritySearch(request)
            
            if response.metadata.success:
                print(f"✅ [Supabase] 相似度搜索成功，找到 {len(response.results)} 个结果")
                results = []
                for result in response.results:
                    results.append({
                        'id': result.id,
                        'similarity': result.similarity,
                        'metadata': dict(result.metadata),
                    })
                return results
            else:
                print(f"❌ [Supabase] 搜索失败: {response.metadata.error}")
                return []
                
        except Exception as e:
            return self.handle_error(e, "相似度搜索")
    
    def hybrid_search(self, table: str, text_query: str, vector_query: List[float],
                     limit: int = 10, text_weight: float = 0.5,
                     vector_weight: float = 0.5) -> List[Dict]:
        """
        混合搜索 (文本 + 向量)

        Args:
            table: 表名
            text_query: 文本查询
            vector_query: 向量查询
            limit: 返回数量
            text_weight: 文本权重
            vector_weight: 向量权重

        Returns:
            搜索结果列表
        """
        try:
            self._ensure_connected()
            request = supabase_service_pb2.HybridSearchRequest(
                metadata=self._create_metadata(),
                table=table,
                text_query=text_query,
                vector_query=vector_query,
                limit=limit,
                text_weight=text_weight,
                vector_weight=vector_weight,
            )
            
            response = self.stub.HybridSearch(request)
            
            if response.metadata.success:
                print(f"✅ [Supabase] 混合搜索成功，找到 {len(response.results)} 个结果")
                results = []
                for result in response.results:
                    results.append({
                        'id': result.id,
                        'similarity': result.similarity,
                        'metadata': dict(result.metadata),
                    })
                return results
            else:
                print(f"❌ [Supabase] 搜索失败: {response.metadata.error}")
                return []
                
        except Exception as e:
            return self.handle_error(e, "混合搜索")
    
    def delete_embedding(self, table: str, doc_id: str) -> bool:
        """
        删除向量嵌入

        Args:
            table: 向量表名
            doc_id: 文档 ID

        Returns:
            是否成功删除
        """
        try:
            self._ensure_connected()
            request = supabase_service_pb2.DeleteEmbeddingRequest(
                metadata=self._create_metadata(),
                table=table,
                id=doc_id,
            )
            
            response = self.stub.DeleteEmbedding(request)
            
            if response.metadata.success and response.success:
                print(f"✅ [Supabase] 向量删除成功: {doc_id}")
                return True
            else:
                print(f"❌ [Supabase] 向量删除失败: {response.metadata.error}")
                return False
                
        except Exception as e:
            self.handle_error(e, "删除向量")
            return False

    def batch_upsert_embeddings(self, table: str, embeddings_data: List[Dict]) -> int:
        """
        批量插入向量

        Args:
            table: 表名
            embeddings_data: 向量数据列表 [{'id': ..., 'embedding': ..., 'metadata': ...}]

        Returns:
            成功插入的数量
        """
        try:
            self._ensure_connected()
            embeddings = []
            for data in embeddings_data:
                meta_struct = struct_pb2.Struct()
                meta_struct.update(data.get('metadata', {}))
                
                emb = supabase_service_pb2.EmbeddingData(
                    id=data['id'],
                    embedding=data['embedding'],
                    metadata=meta_struct,
                )
                embeddings.append(emb)
            
            request = supabase_service_pb2.BatchUpsertEmbeddingsRequest(
                metadata=self._create_metadata(),
                table=table,
                embeddings=embeddings,
            )
            
            response = self.stub.BatchUpsertEmbeddings(request)
            
            if response.metadata.success:
                print(f"✅ [Supabase] 批量插入成功: {response.success_count}/{response.total_count}")
                return response.success_count
            else:
                print(f"❌ [Supabase] 批量插入失败: {response.metadata.error}")
                return 0
                
        except Exception as e:
            return self.handle_error(e, "批量插入向量") or 0
    
    # ========================================
    # 健康检查
    # ========================================
    
    def health_check(self) -> bool:
        """健康检查"""
        try:
            self._ensure_connected()
            request = supabase_service_pb2.HealthCheckRequest(
                metadata=self._create_metadata(),
            )
            
            response = self.stub.HealthCheck(request)
            
            if response.metadata.success:
                print(f"✅ [Supabase] 服务健康")
                print(f"   Supabase 状态: {response.supabase_status}")
                print(f"   PostgreSQL: {response.postgres_version}")
                print(f"   pgvector: {'启用' if response.pgvector_enabled else '禁用'}")
                return True
            else:
                print(f"❌ [Supabase] 服务不健康: {response.metadata.error}")
                return False
                
        except Exception as e:
            return self.handle_error(e, "健康检查") or False


# 便捷使用示例
if __name__ == '__main__':
    # 使用 with 语句自动管理连接
    with SupabaseClient(host='localhost', port=50057, user_id='test_user') as client:
        # 健康检查
        client.health_check()
        
        # 数据库操作
        client.insert('users', [{'name': 'Alice', 'email': 'alice@example.com'}])
        results = client.query('users', select='*', limit=10)
        print(f"查询结果: {results}")
        
        # 向量操作
        import random
        fake_embedding = [random.random() for _ in range(1536)]
        client.upsert_embedding('embeddings', 'doc_001', fake_embedding, 
                               {'title': 'Test Document'})

