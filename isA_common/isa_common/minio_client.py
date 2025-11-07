#!/usr/bin/env python3
"""
MinIO gRPC Client
MinIO 对象存储客户端
"""

from typing import List, Dict, Optional, TYPE_CHECKING
from .base_client import BaseGRPCClient
from .proto import minio_service_pb2, minio_service_pb2_grpc

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry


class MinIOClient(BaseGRPCClient):
    """MinIO gRPC 客户端"""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, user_id: Optional[str] = None,
                 lazy_connect: bool = True, enable_compression: bool = True, enable_retry: bool = True,
                 consul_registry: Optional['ConsulRegistry'] = None, service_name_override: Optional[str] = None):
        """
        初始化 MinIO 客户端

        Args:
            host: 服务地址 (optional, will use Consul discovery if not provided)
            port: 服务端口 (optional, will use Consul discovery if not provided)
            user_id: 用户 ID
            lazy_connect: 延迟连接 (默认: True)
            enable_compression: 启用压缩 (默认: True)
            enable_retry: 启用重试 (默认: True)
            consul_registry: ConsulRegistry instance for service discovery (optional)
            service_name_override: Override service name for Consul lookup (optional, defaults to 'minio')
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
        """创建 MinIO service stub"""
        return minio_service_pb2_grpc.MinIOServiceStub(self.channel)
    
    def service_name(self) -> str:
        return "MinIO"

    def default_port(self) -> int:
        return 50051

    def health_check(self, detailed: bool = True) -> Optional[Dict]:
        """健康检查"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.MinIOHealthCheckRequest(detailed=detailed)
            response = self.stub.HealthCheck(request)

            return {
                'status': response.status,
                'healthy': response.healthy,
                'details': dict(response.details) if response.details else {}
            }
            
        except Exception as e:
            return self.handle_error(e, "健康检查")
    
    def create_bucket(self, bucket_name: str, organization_id: str = 'default-org',
                     region: str = 'us-east-1') -> Optional[Dict]:
        """创建存储桶"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.CreateBucketRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                organization_id=organization_id,
                region=region
            )
            
            response = self.stub.CreateBucket(request)

            if response.success:
                return {
                    'success': True,
                    'bucket': response.bucket_info.name if response.bucket_info else bucket_name
                }
            else:
                return None
            
        except Exception as e:
            return self.handle_error(e, "创建桶")

    def delete_bucket(self, bucket_name: str, force: bool = False) -> bool:
        """删除存储桶

        Args:
            bucket_name: 桶名称
            force: 强制删除（包括所有对象）

        Returns:
            bool: 成功返回 True，失败返回 False
        """
        try:
            self._ensure_connected()
            request = minio_service_pb2.DeleteBucketRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                force=force
            )

            response = self.stub.DeleteBucket(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "删除桶")
            return False

    def list_buckets(self, organization_id: str = 'default-org') -> List[str]:
        """列出存储桶"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.ListBucketsRequest(
                user_id=self.user_id,
                organization_id=organization_id
            )

            response = self.stub.ListBuckets(request)

            if response.success:
                bucket_names = [bucket.name for bucket in response.buckets]
                return bucket_names
            else:
                return []

        except Exception as e:
            return self.handle_error(e, "列出桶") or []

    def bucket_exists(self, bucket_name: str) -> bool:
        """检查桶是否存在"""
        try:
            info = self.get_bucket_info(bucket_name)
            return info is not None
        except Exception:
            return False

    def get_bucket_info(self, bucket_name: str) -> Optional[Dict]:
        """获取桶信息"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetBucketInfoRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = self.stub.GetBucketInfo(request)

            if response.success and response.bucket_info:
                info = {
                    'name': response.bucket_info.name,
                    'owner_id': response.bucket_info.owner_id,
                    'organization_id': response.bucket_info.organization_id,
                    'region': response.bucket_info.region,
                    'size_bytes': response.bucket_info.size_bytes,
                    'object_count': response.bucket_info.object_count
                }
                return info
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "获取桶信息")

    def set_bucket_policy(self, bucket_name: str, policy: str) -> bool:
        """设置桶策略"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.SetBucketPolicyRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                policy_type=minio_service_pb2.BUCKET_POLICY_CUSTOM,
                custom_policy=policy
            )

            response = self.stub.SetBucketPolicy(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "设置桶策略")
            return False

    def get_bucket_policy(self, bucket_name: str) -> Optional[str]:
        """获取桶策略"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetBucketPolicyRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = self.stub.GetBucketPolicy(request)

            if response.success:
                return response.policy_json
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "获取桶策略")

    def delete_bucket_policy(self, bucket_name: str) -> bool:
        """删除桶策略"""
        # MinIO 通过设置空策略来删除
        return self.set_bucket_policy(bucket_name, "")

    # Bucket tags, versioning, and lifecycle methods
    def set_bucket_tags(self, bucket_name: str, tags: Dict[str, str]) -> bool:
        """设置桶标签"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.SetBucketTagsRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                tags=tags
            )

            response = self.stub.SetBucketTags(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "设置桶标签")
            return False

    def get_bucket_tags(self, bucket_name: str) -> Optional[Dict[str, str]]:
        """获取桶标签"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetBucketTagsRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = self.stub.GetBucketTags(request)

            if response.success:
                return dict(response.tags)
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "获取桶标签")

    def delete_bucket_tags(self, bucket_name: str) -> bool:
        """删除桶标签"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.DeleteBucketTagsRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = self.stub.DeleteBucketTags(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "删除桶标签")
            return False

    def set_bucket_versioning(self, bucket_name: str, enabled: bool) -> bool:
        """设置桶版本控制"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.SetBucketVersioningRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                enabled=enabled
            )

            response = self.stub.SetBucketVersioning(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "设置桶版本控制")
            return False

    def get_bucket_versioning(self, bucket_name: str) -> bool:
        """获取桶版本控制状态"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetBucketVersioningRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = self.stub.GetBucketVersioning(request)

            if response.success:
                return response.enabled
            else:
                return False

        except Exception as e:
            self.handle_error(e, "获取桶版本控制状态")
            return False

    def set_bucket_lifecycle(self, bucket_name: str, rules: List[Dict]) -> bool:
        """设置桶生命周期策略"""
        try:
            self._ensure_connected()
            from google.protobuf import struct_pb2

            # Convert rules to protobuf LifecycleRule objects
            lifecycle_rules = []
            for rule in rules:
                # Create LifecycleRule protobuf message
                lifecycle_rule = minio_service_pb2.LifecycleRule()
                lifecycle_rule.id = rule.get('id', '')
                lifecycle_rule.status = rule.get('status', 'Enabled')

                # Convert nested dicts to Struct objects
                if 'filter' in rule and rule['filter']:
                    lifecycle_rule.filter.update(rule['filter'])
                if 'expiration' in rule and rule['expiration']:
                    lifecycle_rule.expiration.update(rule['expiration'])
                if 'transition' in rule and rule['transition']:
                    lifecycle_rule.transition.update(rule['transition'])

                lifecycle_rules.append(lifecycle_rule)

            request = minio_service_pb2.SetBucketLifecycleRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                rules=lifecycle_rules
            )

            response = self.stub.SetBucketLifecycle(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "设置桶生命周期策略")
            return False

    def get_bucket_lifecycle(self, bucket_name: str) -> Optional[List[Dict]]:
        """获取桶生命周期策略"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetBucketLifecycleRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = self.stub.GetBucketLifecycle(request)

            if response.success:
                from google.protobuf.json_format import MessageToDict
                rules = [MessageToDict(rule) for rule in response.rules]
                return rules
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "获取桶生命周期策略")

    def delete_bucket_lifecycle(self, bucket_name: str) -> bool:
        """删除桶生命周期策略"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.DeleteBucketLifecycleRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = self.stub.DeleteBucketLifecycle(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "删除桶生命周期策略")
            return False
    
    def upload_object(self, bucket_name: str, object_key: str, data: bytes,
                     content_type: str = 'application/octet-stream', metadata: Optional[Dict[str, str]] = None) -> Optional[Dict]:
        """上传对象 (流式)"""
        try:
            self._ensure_connected()

            # Ensure bucket exists before uploading
            if not self.bucket_exists(bucket_name):
                # Use user_id as organization_id for user-scoped buckets
                create_result = self.create_bucket(bucket_name, organization_id=self.user_id)
                if not create_result or not create_result.get('success'):
                    return {
                        'success': False,
                        'error': f"Failed to create bucket '{bucket_name}'"
                    }

            def request_generator():
                # 第一个消息：元数据
                meta = minio_service_pb2.PutObjectMetadata(
                    bucket_name=bucket_name,
                    object_key=object_key,
                    user_id=self.user_id,
                    content_type=content_type,
                    content_length=len(data)
                )
                if metadata:
                    meta.metadata.update(metadata)
                yield minio_service_pb2.PutObjectRequest(metadata=meta)

                # 后续消息：数据块
                chunk_size = 1024 * 64  # 64KB chunks
                for i in range(0, len(data), chunk_size):
                    chunk = data[i:i + chunk_size]
                    yield minio_service_pb2.PutObjectRequest(chunk=chunk)

            response = self.stub.PutObject(request_generator())

            if response.success:
                return {
                    'success': True,
                    'object_key': response.object_key,
                    'size': response.size,
                    'etag': response.etag
                }
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "上传对象")
    
    def list_objects(self, bucket_name: str, prefix: str = '', max_keys: int = 100) -> List[Dict]:
        """列出对象"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.ListObjectsRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                prefix=prefix,
                max_keys=max_keys
            )

            response = self.stub.ListObjects(request)

            if response.success:
                objects = []
                for obj in response.objects:
                    objects.append({
                        'name': obj.key,  # Add 'name' alias for compatibility
                        'key': obj.key,
                        'size': obj.size,
                        'content_type': obj.content_type,
                        'etag': obj.etag
                    })
                return objects
            else:
                return []

        except Exception as e:
            return self.handle_error(e, "列出对象") or []

    def get_object(self, bucket_name: str, object_key: str) -> Optional[bytes]:
        """下载对象 (流式)"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetObjectRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            response_stream = self.stub.GetObject(request)
            data = bytearray()

            for response in response_stream:
                if response.HasField('metadata'):
                    # First response contains metadata
                    continue
                elif response.HasField('chunk'):
                    data.extend(response.chunk)

            return bytes(data)

        except Exception as e:
            return self.handle_error(e, "下载对象")

    def delete_object(self, bucket_name: str, object_key: str) -> bool:
        """删除对象"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.DeleteObjectRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            response = self.stub.DeleteObject(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "删除对象")
            return False

    def delete_objects(self, bucket_name: str, object_keys: List[str]) -> bool:
        """批量删除对象"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.DeleteObjectsRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                object_keys=object_keys,
                quiet=False
            )

            response = self.stub.DeleteObjects(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "批量删除对象")
            return False

    def copy_object(self, dest_bucket: str, dest_key: str, source_bucket: str, source_key: str) -> bool:
        """复制对象"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.CopyObjectRequest(
                source_bucket=source_bucket,
                source_key=source_key,
                dest_bucket=dest_bucket,
                dest_key=dest_key,
                user_id=self.user_id
            )

            response = self.stub.CopyObject(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "复制对象")
            return False

    def get_object_metadata(self, bucket_name: str, object_key: str) -> Optional[Dict]:
        """获取对象元数据 (使用 StatObject)"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.StatObjectRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            response = self.stub.StatObject(request)

            if response.success and response.object_info:
                metadata = {
                    'key': response.object_info.key,
                    'size': response.object_info.size,
                    'etag': response.object_info.etag,
                    'content_type': response.object_info.content_type,
                    'last_modified': response.object_info.last_modified,
                    'metadata': dict(response.object_info.metadata) if response.object_info.metadata else {}
                }
                return metadata
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "获取对象元数据")

    # Convenience aliases for compatibility
    def put_object(self, bucket_name: str, object_key: str, data, size: int, metadata: Optional[Dict] = None) -> bool:
        """上传对象 (兼容性方法)"""
        import io
        if isinstance(data, io.BytesIO):
            data = data.read()
        elif not isinstance(data, bytes):
            data = bytes(data)

        result = self.upload_object(bucket_name, object_key, data, metadata=metadata or {})
        return result is not None

    def upload_file(self, bucket_name: str, object_key: str, file_path: str) -> bool:
        """从文件上传对象"""
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            result = self.upload_object(bucket_name, object_key, data)
            return result is not None
        except Exception as e:
            self.handle_error(e, "从文件上传对象")
            return False

    # Object tags methods
    def set_object_tags(self, bucket_name: str, object_key: str, tags: Dict[str, str]) -> bool:
        """设置对象标签"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.SetObjectTagsRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id,
                tags=tags
            )

            response = self.stub.SetObjectTags(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "设置对象标签")
            return False

    def get_object_tags(self, bucket_name: str, object_key: str) -> Optional[Dict[str, str]]:
        """获取对象标签"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetObjectTagsRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            response = self.stub.GetObjectTags(request)

            if response.success:
                return dict(response.tags)
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "获取对象标签")

    def delete_object_tags(self, bucket_name: str, object_key: str) -> bool:
        """删除对象标签"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.DeleteObjectTagsRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            response = self.stub.DeleteObjectTags(request)

            if response.success:
                return True
            else:
                return False

        except Exception as e:
            self.handle_error(e, "删除对象标签")
            return False

    def list_object_versions(self, bucket_name: str, object_key: str) -> Optional[List[Dict]]:
        """列出对象版本 (暂未实现)"""
        return None
    
    def get_presigned_url(self, bucket_name: str, object_key: str,
                         expiry_seconds: int = 3600) -> Optional[str]:
        """获取预签名 URL (GET)"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetPresignedURLRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id,
                expiry_seconds=expiry_seconds
            )

            response = self.stub.GetPresignedURL(request)

            if response.success:
                return response.url
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "获取预签名 URL")

    def get_presigned_put_url(self, bucket_name: str, object_key: str,
                              expiry_seconds: int = 3600, content_type: str = 'application/octet-stream') -> Optional[str]:
        """获取预签名 URL (PUT)"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetPresignedPutURLRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id,
                expiry_seconds=expiry_seconds,
                content_type=content_type
            )

            response = self.stub.GetPresignedPutURL(request)

            if response.success:
                return response.url
            else:
                return None

        except Exception as e:
            return self.handle_error(e, "获取预签名 PUT URL")

    def generate_presigned_url(self, bucket_name: str, object_key: str,
                               expiry_seconds: int = 3600, method: str = 'GET') -> Optional[str]:
        """生成预签名 URL (兼容性方法)"""
        if method.upper() == 'PUT':
            return self.get_presigned_put_url(bucket_name, object_key, expiry_seconds)
        else:
            return self.get_presigned_url(bucket_name, object_key, expiry_seconds)


# 便捷使用示例
if __name__ == '__main__':
    with MinIOClient(host='localhost', port=50051, user_id='test_user') as client:
        # 健康检查
        client.health_check()
        
        # 创建桶
        client.create_bucket('test-bucket')
        
        # 上传文件
        client.upload_object('test-bucket', 'test.txt', b'Hello MinIO!')
        
        # 列出对象
        objects = client.list_objects('test-bucket')

