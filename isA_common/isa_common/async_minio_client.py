#!/usr/bin/env python3
"""
Async MinIO gRPC Client
High-performance async MinIO/S3 client using grpc.aio

Performance Benefits:
- True async I/O without GIL blocking
- Concurrent upload/download operations
- Memory-efficient streaming
- Connection pooling
"""

import logging
from typing import List, Dict, Optional, AsyncIterator, Callable, TYPE_CHECKING
from .async_base_client import AsyncBaseGRPCClient
from .proto import minio_service_pb2, minio_service_pb2_grpc

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry

logger = logging.getLogger(__name__)

# Constants
DEFAULT_CHUNK_SIZE = 64 * 1024  # 64KB for streaming
DEFAULT_PRESIGN_EXPIRY = 3600  # 1 hour
MAX_PRESIGN_EXPIRY = 7 * 24 * 3600  # 7 days
MIN_PRESIGN_EXPIRY = 60  # 1 minute


class AsyncMinIOClient(AsyncBaseGRPCClient):
    """Async MinIO gRPC client for high-performance object storage operations."""

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
        Initialize async MinIO client.

        Args:
            host: Service host (optional, uses Consul if not provided)
            port: Service port (optional, uses Consul if not provided)
            user_id: User ID for multi-tenant isolation
            lazy_connect: Delay connection until first use
            enable_compression: Enable gRPC compression
            enable_retry: Enable automatic retries
            consul_registry: ConsulRegistry for service discovery
            service_name_override: Override service name for Consul
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
        """Create MinIO service stub."""
        return minio_service_pb2_grpc.MinIOServiceStub(self.channel)

    def service_name(self) -> str:
        return "MinIO"

    def default_port(self) -> int:
        return 50051

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self, detailed: bool = True) -> Optional[Dict]:
        """Check MinIO service health."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.MinIOHealthCheckRequest(detailed=detailed)
            response = await self.stub.HealthCheck(request)

            return {
                'status': response.status,
                'healthy': response.healthy,
                'details': self._proto_struct_to_dict(response.details) if response.details else {}
            }

        except Exception as e:
            return self.handle_error(e, "health check")

    # ============================================
    # Bucket Management
    # ============================================

    async def create_bucket(
        self,
        bucket_name: str,
        organization_id: str = 'default-org',
        region: str = 'us-east-1'
    ) -> Optional[Dict]:
        """Create a new bucket."""
        try:
            await self._ensure_connected()

            request = minio_service_pb2.CreateBucketRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                organization_id=organization_id,
                region=region
            )

            response = await self.stub.CreateBucket(request)

            if response.success:
                return {
                    'success': True,
                    'bucket': response.bucket_info.name if response.bucket_info else bucket_name,
                    'message': response.message
                }
            return None

        except Exception as e:
            return self.handle_error(e, "create bucket")

    async def delete_bucket(self, bucket_name: str, force: bool = False) -> bool:
        """Delete a bucket."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.DeleteBucketRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                force=force
            )

            response = await self.stub.DeleteBucket(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "delete bucket")
            return False

    async def list_buckets(self, organization_id: str = 'default-org') -> List[str]:
        """List all accessible buckets."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.ListBucketsRequest(
                user_id=self.user_id,
                organization_id=organization_id
            )

            response = await self.stub.ListBuckets(request)

            if response.success:
                return [bucket.name for bucket in response.buckets]
            return []

        except Exception as e:
            return self.handle_error(e, "list buckets") or []

    async def bucket_exists(self, bucket_name: str) -> bool:
        """Check if bucket exists."""
        try:
            info = await self.get_bucket_info(bucket_name)
            return info is not None
        except Exception:
            return False

    async def get_bucket_info(self, bucket_name: str) -> Optional[Dict]:
        """Get bucket metadata."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.GetBucketInfoRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = await self.stub.GetBucketInfo(request)

            if response.success and response.bucket_info:
                return {
                    'name': response.bucket_info.name,
                    'owner_id': response.bucket_info.owner_id,
                    'organization_id': response.bucket_info.organization_id,
                    'region': response.bucket_info.region,
                    'size_bytes': response.bucket_info.size_bytes,
                    'object_count': response.bucket_info.object_count
                }
            return None

        except Exception as e:
            return self.handle_error(e, "get bucket info")

    # ============================================
    # Object Upload
    # ============================================

    async def upload_object(
        self,
        bucket_name: str,
        object_key: str,
        data: bytes,
        content_type: str = 'application/octet-stream',
        metadata: Optional[Dict[str, str]] = None,
        auto_create_bucket: bool = True
    ) -> Optional[Dict]:
        """Upload object using streaming gRPC."""
        try:
            await self._ensure_connected()

            # Auto-create bucket if needed
            if auto_create_bucket and not await self.bucket_exists(bucket_name):
                create_result = await self.create_bucket(bucket_name)
                if not create_result or not create_result.get('success'):
                    return {
                        'success': False,
                        'error': f"Failed to create bucket '{bucket_name}'"
                    }

            async def request_generator():
                # First message: metadata
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

                # Subsequent messages: data chunks
                for i in range(0, len(data), DEFAULT_CHUNK_SIZE):
                    chunk = data[i:i + DEFAULT_CHUNK_SIZE]
                    yield minio_service_pb2.PutObjectRequest(chunk=chunk)

            response = await self.stub.PutObject(request_generator())

            if response.success:
                return {
                    'success': True,
                    'object_key': response.object_key,
                    'size': response.size,
                    'etag': response.etag
                }
            return None

        except Exception as e:
            return self.handle_error(e, "upload object")

    async def upload_large_file(
        self,
        bucket_name: str,
        object_key: str,
        file_obj,
        file_size: int = None,
        content_type: str = 'application/octet-stream',
        chunk_size: int = 5 * 1024 * 1024,  # 5MB
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        """Upload large file using streaming with progress support."""
        try:
            await self._ensure_connected()

            if not await self.bucket_exists(bucket_name):
                create_result = await self.create_bucket(bucket_name)
                if not create_result:
                    return False

            bytes_sent = 0

            async def request_generator():
                nonlocal bytes_sent

                # First message: metadata
                meta = minio_service_pb2.PutObjectMetadata(
                    bucket_name=bucket_name,
                    object_key=object_key,
                    user_id=self.user_id,
                    content_type=content_type,
                    content_length=file_size or 0
                )
                yield minio_service_pb2.PutObjectRequest(metadata=meta)

                # Stream chunks
                while True:
                    chunk = file_obj.read(chunk_size)
                    if not chunk:
                        break

                    yield minio_service_pb2.PutObjectRequest(chunk=chunk)

                    bytes_sent += len(chunk)
                    if progress_callback and file_size:
                        progress_callback(bytes_sent, file_size)

            response = await self.stub.PutObject(request_generator())
            return response.success

        except Exception as e:
            self.handle_error(e, "upload large file")
            return False

    # ============================================
    # Object Download
    # ============================================

    async def get_object(self, bucket_name: str, object_key: str) -> Optional[bytes]:
        """Download object to memory."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.GetObjectRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            data = bytearray()
            async for response in self.stub.GetObject(request):
                if response.HasField('metadata'):
                    continue
                elif response.HasField('chunk'):
                    data.extend(response.chunk)

            return bytes(data)

        except Exception as e:
            return self.handle_error(e, "get object")

    async def download_stream(self, bucket_name: str, object_key: str) -> AsyncIterator[bytes]:
        """Stream download for memory-efficient large file handling."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.GetObjectRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            async for response in self.stub.GetObject(request):
                if response.HasField('chunk'):
                    yield response.chunk

        except Exception as e:
            self.handle_error(e, "download stream")

    async def download_to_file(
        self,
        bucket_name: str,
        object_key: str,
        file_path: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        """Download object directly to file with progress support."""
        try:
            import aiofiles

            # Get size first for progress reporting
            metadata = await self.get_object_metadata(bucket_name, object_key)
            total_size = metadata.get('size', 0) if metadata else 0

            bytes_received = 0
            async with aiofiles.open(file_path, 'wb') as f:
                async for chunk in self.download_stream(bucket_name, object_key):
                    await f.write(chunk)
                    bytes_received += len(chunk)

                    if progress_callback and total_size:
                        progress_callback(bytes_received, total_size)

            return True

        except ImportError:
            # Fallback to sync write if aiofiles not available
            try:
                metadata = await self.get_object_metadata(bucket_name, object_key)
                total_size = metadata.get('size', 0) if metadata else 0

                bytes_received = 0
                with open(file_path, 'wb') as f:
                    async for chunk in self.download_stream(bucket_name, object_key):
                        f.write(chunk)
                        bytes_received += len(chunk)

                        if progress_callback and total_size:
                            progress_callback(bytes_received, total_size)

                return True

            except Exception as e:
                self.handle_error(e, "download to file")
                return False

        except Exception as e:
            self.handle_error(e, "download to file")
            return False

    # ============================================
    # Object Management
    # ============================================

    async def list_objects(
        self,
        bucket_name: str,
        prefix: str = '',
        max_keys: int = 1000
    ) -> List[Dict]:
        """List objects in bucket."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.ListObjectsRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                prefix=prefix,
                max_keys=max_keys
            )

            response = await self.stub.ListObjects(request)

            if response.success:
                return [
                    {
                        'name': obj.key,
                        'key': obj.key,
                        'size': obj.size,
                        'content_type': obj.content_type,
                        'etag': obj.etag,
                    }
                    for obj in response.objects
                ]
            return []

        except Exception as e:
            return self.handle_error(e, "list objects") or []

    async def delete_object(self, bucket_name: str, object_key: str) -> bool:
        """Delete single object."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.DeleteObjectRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            response = await self.stub.DeleteObject(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "delete object")
            return False

    async def delete_objects(self, bucket_name: str, object_keys: List[str]) -> bool:
        """Batch delete objects."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.DeleteObjectsRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                object_keys=object_keys,
                quiet=False
            )

            response = await self.stub.DeleteObjects(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "delete objects")
            return False

    async def copy_object(
        self,
        dest_bucket: str,
        dest_key: str,
        source_bucket: str,
        source_key: str
    ) -> bool:
        """Copy object between buckets or within bucket."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.CopyObjectRequest(
                source_bucket=source_bucket,
                source_key=source_key,
                dest_bucket=dest_bucket,
                dest_key=dest_key,
                user_id=self.user_id
            )

            response = await self.stub.CopyObject(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "copy object")
            return False

    async def get_object_metadata(self, bucket_name: str, object_key: str) -> Optional[Dict]:
        """Get object metadata without downloading content."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.StatObjectRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            response = await self.stub.StatObject(request)

            if response.success and response.object_info:
                return {
                    'key': response.object_info.key,
                    'size': response.object_info.size,
                    'etag': response.object_info.etag,
                    'content_type': response.object_info.content_type,
                    'last_modified': response.object_info.last_modified,
                    'metadata': dict(response.object_info.metadata) if response.object_info.metadata else {}
                }
            return None

        except Exception as e:
            return self.handle_error(e, "get object metadata")

    # ============================================
    # Presigned URLs
    # ============================================

    async def get_presigned_url(
        self,
        bucket_name: str,
        object_key: str,
        expiry_seconds: int = DEFAULT_PRESIGN_EXPIRY
    ) -> Optional[str]:
        """Generate presigned URL for download (GET)."""
        try:
            expiry_seconds = max(MIN_PRESIGN_EXPIRY, min(expiry_seconds, MAX_PRESIGN_EXPIRY))

            await self._ensure_connected()
            request = minio_service_pb2.GetPresignedURLRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id,
                expiry_seconds=expiry_seconds
            )

            response = await self.stub.GetPresignedURL(request)
            return response.url if response.success else None

        except Exception as e:
            return self.handle_error(e, "get presigned URL")

    async def get_presigned_put_url(
        self,
        bucket_name: str,
        object_key: str,
        expiry_seconds: int = DEFAULT_PRESIGN_EXPIRY,
        content_type: str = 'application/octet-stream'
    ) -> Optional[str]:
        """Generate presigned URL for upload (PUT)."""
        try:
            expiry_seconds = max(MIN_PRESIGN_EXPIRY, min(expiry_seconds, MAX_PRESIGN_EXPIRY))

            await self._ensure_connected()
            request = minio_service_pb2.GetPresignedPutURLRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id,
                expiry_seconds=expiry_seconds,
                content_type=content_type
            )

            response = await self.stub.GetPresignedPutURL(request)
            return response.url if response.success else None

        except Exception as e:
            return self.handle_error(e, "get presigned PUT URL")

    # ============================================
    # Bucket Configuration
    # ============================================

    async def set_bucket_versioning(self, bucket_name: str, enabled: bool) -> bool:
        """Enable/disable bucket versioning."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.SetBucketVersioningRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                enabled=enabled
            )

            response = await self.stub.SetBucketVersioning(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "set bucket versioning")
            return False

    async def set_bucket_tags(self, bucket_name: str, tags: Dict[str, str]) -> bool:
        """Set bucket tags."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.SetBucketTagsRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                tags=tags
            )

            response = await self.stub.SetBucketTags(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "set bucket tags")
            return False

    async def get_bucket_tags(self, bucket_name: str) -> Optional[Dict[str, str]]:
        """Get bucket tags."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.GetBucketTagsRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = await self.stub.GetBucketTags(request)
            return dict(response.tags) if response.success else None

        except Exception as e:
            return self.handle_error(e, "get bucket tags")

    # ============================================
    # Object Tags
    # ============================================

    async def set_object_tags(self, bucket_name: str, object_key: str, tags: Dict[str, str]) -> bool:
        """Set object tags."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.SetObjectTagsRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id,
                tags=tags
            )

            response = await self.stub.SetObjectTags(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "set object tags")
            return False

    async def get_object_tags(self, bucket_name: str, object_key: str) -> Optional[Dict[str, str]]:
        """Get object tags."""
        try:
            await self._ensure_connected()
            request = minio_service_pb2.GetObjectTagsRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            response = await self.stub.GetObjectTags(request)
            return dict(response.tags) if response.success else None

        except Exception as e:
            return self.handle_error(e, "get object tags")

    # ============================================
    # Concurrent Operations
    # ============================================

    async def upload_many_concurrent(self, uploads: List[Dict]) -> List[Optional[Dict]]:
        """
        Upload multiple objects concurrently.

        Args:
            uploads: List of {'bucket': str, 'key': str, 'data': bytes} dicts

        Returns:
            List of upload results
        """
        import asyncio

        async def upload_single(u: Dict) -> Optional[Dict]:
            return await self.upload_object(
                bucket_name=u['bucket'],
                object_key=u['key'],
                data=u['data'],
                content_type=u.get('content_type', 'application/octet-stream'),
                metadata=u.get('metadata')
            )

        return await asyncio.gather(*[upload_single(u) for u in uploads])

    async def download_many_concurrent(self, downloads: List[Dict]) -> List[Optional[bytes]]:
        """
        Download multiple objects concurrently.

        Args:
            downloads: List of {'bucket': str, 'key': str} dicts

        Returns:
            List of object data
        """
        import asyncio

        async def download_single(d: Dict) -> Optional[bytes]:
            return await self.get_object(
                bucket_name=d['bucket'],
                object_key=d['key']
            )

        return await asyncio.gather(*[download_single(d) for d in downloads])

    async def delete_many_concurrent(self, deletes: List[Dict]) -> List[bool]:
        """
        Delete multiple objects concurrently (from different buckets).

        Args:
            deletes: List of {'bucket': str, 'key': str} dicts

        Returns:
            List of delete results
        """
        import asyncio

        async def delete_single(d: Dict) -> bool:
            return await self.delete_object(
                bucket_name=d['bucket'],
                object_key=d['key']
            )

        return await asyncio.gather(*[delete_single(d) for d in deletes])


# Example usage
if __name__ == '__main__':
    import asyncio

    async def main():
        async with AsyncMinIOClient(host='localhost', port=50051, user_id='test-user') as client:
            # Health check
            health = await client.health_check()
            print(f"Health: {health}")

            # Create bucket
            result = await client.create_bucket('async-test-bucket')
            print(f"Create bucket: {result}")

            # Upload objects concurrently
            uploads = [
                {'bucket': 'async-test-bucket', 'key': f'file{i}.txt', 'data': f'content{i}'.encode()}
                for i in range(5)
            ]
            results = await client.upload_many_concurrent(uploads)
            print(f"Uploaded: {results}")

            # List objects
            objects = await client.list_objects('async-test-bucket')
            print(f"Objects: {objects}")

            # Download concurrently
            downloads = [
                {'bucket': 'async-test-bucket', 'key': f'file{i}.txt'}
                for i in range(5)
            ]
            data = await client.download_many_concurrent(downloads)
            print(f"Downloaded: {[d.decode() if d else None for d in data]}")

    asyncio.run(main())
