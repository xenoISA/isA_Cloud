#!/usr/bin/env python3
"""
Async MinIO Native Client
High-performance async MinIO/S3 client using aioboto3 for direct S3 protocol access.

This client connects directly to MinIO using the S3-compatible API,
providing full support for all object storage features including:
- Bucket management
- Object upload/download with streaming
- Presigned URLs
- Tags and metadata
- Concurrent operations
"""

import os
from typing import List, Dict, Optional, AsyncIterator, Callable, Any
from contextlib import asynccontextmanager
from datetime import datetime, timezone

# aioboto3 for async S3 operations
import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .async_base_client import AsyncBaseClient

# Constants
DEFAULT_CHUNK_SIZE = 64 * 1024  # 64KB for streaming
DEFAULT_PRESIGN_EXPIRY = 3600  # 1 hour
MAX_PRESIGN_EXPIRY = 7 * 24 * 3600  # 7 days
MIN_PRESIGN_EXPIRY = 60  # 1 minute


class AsyncMinIOClient(AsyncBaseClient):
    """
    Async MinIO client using aioboto3 for direct S3 protocol access.

    Provides direct connection to MinIO with full feature support including
    bucket management, object operations, presigned URLs, and streaming.
    """

    # Class-level configuration
    SERVICE_NAME = "MinIO"
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 9000
    ENV_PREFIX = "MINIO"
    TENANT_SEPARATOR = "-"  # user-{user}-{bucket}

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: str = 'us-east-1',
        secure: bool = False,
        **kwargs
    ):
        """
        Initialize async MinIO client with native S3 driver.

        Args:
            endpoint_url: Full MinIO endpoint URL (overrides host/port if provided)
            access_key: MinIO access key (default: from MINIO_ACCESS_KEY env)
            secret_key: MinIO secret key (default: from MINIO_SECRET_KEY env)
            region: AWS region (default: 'us-east-1')
            secure: Use HTTPS (default: False for local MinIO)
            **kwargs: Base client args (host, port, user_id, organization_id, lazy_connect)
        """
        super().__init__(**kwargs)

        # Build endpoint URL from host/port or use provided URL
        if endpoint_url:
            self._endpoint_url = endpoint_url
        else:
            protocol = 'https' if secure else 'http'
            self._endpoint_url = f"{protocol}://{self._host}:{self._port}"

        # Get credentials from env or parameters
        self._access_key = access_key or os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
        self._secret_key = secret_key or os.getenv('MINIO_SECRET_KEY', 'minioadmin')
        self._region = region

        # aioboto3 session and client state
        self._session = None
        self._s3_client = None
        self._s3_resource = None

        # boto config with retry
        self._config = Config(
            signature_version='s3v4',
            retries={
                'max_attempts': 3,
                'mode': 'standard'
            },
            connect_timeout=10,
            read_timeout=30
        )

    async def _connect(self) -> None:
        """Create aioboto3 session."""
        self._session = aioboto3.Session()
        self._self._logger.info(f"Created aioboto3 session for {self._endpoint_url}")

    async def _disconnect(self) -> None:
        """Close aioboto3 session."""
        self._session = None

    def _get_prefixed_bucket_name(self, bucket_name: str) -> str:
        """
        Get bucket name with user prefix for multi-tenant isolation.

        Maintains compatibility with gRPC client's bucket naming convention:
        user-{user_id}-{bucket_name}

        S3 bucket naming rules:
        - 3-63 characters
        - Only lowercase letters, numbers, hyphens
        - Must start/end with letter or number
        """
        if self.user_id:
            # Sanitize user_id: replace underscores and special chars with hyphens
            safe_user_id = self.user_id.lower().replace('_', '-').replace('|', '-')
            # Remove consecutive hyphens
            while '--' in safe_user_id:
                safe_user_id = safe_user_id.replace('--', '-')
            # Strip leading/trailing hyphens
            safe_user_id = safe_user_id.strip('-')

            # Sanitize bucket_name similarly
            safe_bucket = bucket_name.lower().replace('_', '-')
            while '--' in safe_bucket:
                safe_bucket = safe_bucket.replace('--', '-')
            safe_bucket = safe_bucket.strip('-')

            return f"user-{safe_user_id}-{safe_bucket}"

        # Sanitize bucket name even without user prefix
        safe_bucket = bucket_name.lower().replace('_', '-')
        while '--' in safe_bucket:
            safe_bucket = safe_bucket.replace('--', '-')
        return safe_bucket.strip('-')

    async def _get_client(self):
        """Get or create S3 client context manager."""
        await self._ensure_connected()
        return self._session.client(
            's3',
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
            config=self._config
        )

    async def _get_resource(self):
        """Get or create S3 resource context manager."""
        await self._ensure_connected()
        return self._session.resource(
            's3',
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
            config=self._config
        )

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self, detailed: bool = True) -> Optional[Dict]:
        """Check MinIO service health by listing buckets."""
        try:
            async with await self._get_client() as client:
                response = await client.list_buckets()
                bucket_count = len(response.get('Buckets', []))

                return {
                    'status': 'healthy',
                    'healthy': True,
                    'details': {
                        'endpoint': self._endpoint_url,
                        'bucket_count': bucket_count,
                        'owner': response.get('Owner', {}).get('DisplayName', 'unknown')
                    } if detailed else {}
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
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                # MinIO ignores LocationConstraint for us-east-1
                if region == 'us-east-1':
                    await client.create_bucket(Bucket=prefixed_name)
                else:
                    await client.create_bucket(
                        Bucket=prefixed_name,
                        CreateBucketConfiguration={'LocationConstraint': region}
                    )

                self._logger.info(f"Created bucket: {prefixed_name}")
                return {
                    'success': True,
                    'bucket': prefixed_name,
                    'message': f'Bucket {prefixed_name} created successfully'
                }

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'BucketAlreadyOwnedByYou':
                return {
                    'success': True,
                    'bucket': self._get_prefixed_bucket_name(bucket_name),
                    'message': 'Bucket already exists'
                }
            return self.handle_error(e, "create bucket")
        except Exception as e:
            return self.handle_error(e, "create bucket")

    async def delete_bucket(self, bucket_name: str, force: bool = False) -> bool:
        """Delete a bucket."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                if force:
                    # Delete all objects first
                    await self._empty_bucket(client, prefixed_name)

                await client.delete_bucket(Bucket=prefixed_name)
                self._logger.info(f"Deleted bucket: {prefixed_name}")
                return True

        except Exception as e:
            self.handle_error(e, "delete bucket")
            return False

    async def _empty_bucket(self, client, bucket_name: str):
        """Delete all objects in a bucket."""
        try:
            paginator = client.get_paginator('list_objects_v2')
            async for page in paginator.paginate(Bucket=bucket_name):
                objects = page.get('Contents', [])
                if objects:
                    delete_objects = [{'Key': obj['Key']} for obj in objects]
                    await client.delete_objects(
                        Bucket=bucket_name,
                        Delete={'Objects': delete_objects}
                    )
        except Exception as e:
            self._logger.warning(f"Error emptying bucket {bucket_name}: {e}")

    async def list_buckets(self, organization_id: str = 'default-org') -> List[str]:
        """List all accessible buckets."""
        try:
            async with await self._get_client() as client:
                response = await client.list_buckets()
                buckets = response.get('Buckets', [])

                # Filter by user prefix if user_id is set
                if self.user_id:
                    prefix = f"user-{self.user_id}-"
                    return [
                        b['Name'].replace(prefix, '', 1)
                        for b in buckets
                        if b['Name'].startswith(prefix)
                    ]
                return [b['Name'] for b in buckets]

        except Exception as e:
            return self.handle_error(e, "list buckets") or []

    async def bucket_exists(self, bucket_name: str) -> bool:
        """Check if bucket exists."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                await client.head_bucket(Bucket=prefixed_name)
                return True

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ('404', 'NoSuchBucket'):
                return False
            return False
        except Exception:
            return False

    async def get_bucket_info(self, bucket_name: str) -> Optional[Dict]:
        """Get bucket metadata."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                # Check bucket exists
                await client.head_bucket(Bucket=prefixed_name)

                # Get bucket location
                location = await client.get_bucket_location(Bucket=prefixed_name)
                region = location.get('LocationConstraint') or 'us-east-1'

                # Count objects and calculate size
                total_size = 0
                object_count = 0
                paginator = client.get_paginator('list_objects_v2')
                async for page in paginator.paginate(Bucket=prefixed_name):
                    for obj in page.get('Contents', []):
                        total_size += obj.get('Size', 0)
                        object_count += 1

                return {
                    'name': bucket_name,
                    'owner_id': self.user_id,
                    'organization_id': 'default-org',
                    'region': region,
                    'size_bytes': total_size,
                    'object_count': object_count
                }

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
        """Upload object to MinIO."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            # Auto-create bucket if needed
            if auto_create_bucket and not await self.bucket_exists(bucket_name):
                create_result = await self.create_bucket(bucket_name)
                if not create_result or not create_result.get('success'):
                    return {
                        'success': False,
                        'error': f"Failed to create bucket '{bucket_name}'"
                    }

            async with await self._get_client() as client:
                put_args = {
                    'Bucket': prefixed_name,
                    'Key': object_key,
                    'Body': data,
                    'ContentType': content_type
                }

                if metadata:
                    # S3 metadata keys must be strings
                    put_args['Metadata'] = {k: str(v) for k, v in metadata.items()}

                response = await client.put_object(**put_args)

                return {
                    'success': True,
                    'object_key': object_key,
                    'size': len(data),
                    'etag': response.get('ETag', '').strip('"')
                }

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
        """Upload large file using multipart upload with progress support."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            if not await self.bucket_exists(bucket_name):
                create_result = await self.create_bucket(bucket_name)
                if not create_result:
                    return False

            async with await self._get_client() as client:
                # Start multipart upload
                mpu = await client.create_multipart_upload(
                    Bucket=prefixed_name,
                    Key=object_key,
                    ContentType=content_type
                )
                upload_id = mpu['UploadId']

                parts = []
                part_number = 1
                bytes_sent = 0

                try:
                    while True:
                        chunk = file_obj.read(chunk_size)
                        if not chunk:
                            break

                        response = await client.upload_part(
                            Bucket=prefixed_name,
                            Key=object_key,
                            UploadId=upload_id,
                            PartNumber=part_number,
                            Body=chunk
                        )

                        parts.append({
                            'PartNumber': part_number,
                            'ETag': response['ETag']
                        })

                        bytes_sent += len(chunk)
                        if progress_callback and file_size:
                            progress_callback(bytes_sent, file_size)

                        part_number += 1

                    # Complete multipart upload
                    await client.complete_multipart_upload(
                        Bucket=prefixed_name,
                        Key=object_key,
                        UploadId=upload_id,
                        MultipartUpload={'Parts': parts}
                    )
                    return True

                except Exception as e:
                    # Abort on failure
                    await client.abort_multipart_upload(
                        Bucket=prefixed_name,
                        Key=object_key,
                        UploadId=upload_id
                    )
                    raise e

        except Exception as e:
            self.handle_error(e, "upload large file")
            return False

    # ============================================
    # Object Download
    # ============================================

    async def get_object(self, bucket_name: str, object_key: str) -> Optional[bytes]:
        """Download object to memory."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                response = await client.get_object(
                    Bucket=prefixed_name,
                    Key=object_key
                )

                # Read the streaming body
                async with response['Body'] as stream:
                    data = await stream.read()
                return data

        except Exception as e:
            return self.handle_error(e, "get object")

    async def download_stream(self, bucket_name: str, object_key: str) -> AsyncIterator[bytes]:
        """Stream download for memory-efficient large file handling."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                response = await client.get_object(
                    Bucket=prefixed_name,
                    Key=object_key
                )

                async with response['Body'] as stream:
                    while True:
                        chunk = await stream.read(DEFAULT_CHUNK_SIZE)
                        if not chunk:
                            break
                        yield chunk

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
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                response = await client.list_objects_v2(
                    Bucket=prefixed_name,
                    Prefix=prefix,
                    MaxKeys=max_keys
                )

                objects = []
                for obj in response.get('Contents', []):
                    objects.append({
                        'name': obj['Key'],
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'content_type': '',  # Not returned by list
                        'etag': obj.get('ETag', '').strip('"'),
                        'last_modified': obj.get('LastModified')
                    })
                return objects

        except Exception as e:
            return self.handle_error(e, "list objects") or []

    async def delete_object(self, bucket_name: str, object_key: str) -> bool:
        """Delete single object."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                await client.delete_object(
                    Bucket=prefixed_name,
                    Key=object_key
                )
                return True

        except Exception as e:
            self.handle_error(e, "delete object")
            return False

    async def delete_objects(self, bucket_name: str, object_keys: List[str]) -> bool:
        """Batch delete objects."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                delete_objects = [{'Key': key} for key in object_keys]
                await client.delete_objects(
                    Bucket=prefixed_name,
                    Delete={'Objects': delete_objects}
                )
                return True

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
            dest_prefixed = self._get_prefixed_bucket_name(dest_bucket)
            source_prefixed = self._get_prefixed_bucket_name(source_bucket)

            async with await self._get_client() as client:
                await client.copy_object(
                    Bucket=dest_prefixed,
                    Key=dest_key,
                    CopySource={'Bucket': source_prefixed, 'Key': source_key}
                )
                return True

        except Exception as e:
            self.handle_error(e, "copy object")
            return False

    async def get_object_metadata(self, bucket_name: str, object_key: str) -> Optional[Dict]:
        """Get object metadata without downloading content."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                response = await client.head_object(
                    Bucket=prefixed_name,
                    Key=object_key
                )

                last_modified = response.get('LastModified')
                if last_modified:
                    last_modified = last_modified.isoformat()

                return {
                    'key': object_key,
                    'size': response.get('ContentLength', 0),
                    'etag': response.get('ETag', '').strip('"'),
                    'content_type': response.get('ContentType', ''),
                    'last_modified': last_modified,
                    'metadata': response.get('Metadata', {})
                }

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
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                url = await client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': prefixed_name,
                        'Key': object_key
                    },
                    ExpiresIn=expiry_seconds
                )
                return url

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
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                url = await client.generate_presigned_url(
                    'put_object',
                    Params={
                        'Bucket': prefixed_name,
                        'Key': object_key,
                        'ContentType': content_type
                    },
                    ExpiresIn=expiry_seconds
                )
                return url

        except Exception as e:
            return self.handle_error(e, "get presigned PUT URL")

    # ============================================
    # Bucket Configuration
    # ============================================

    async def set_bucket_versioning(self, bucket_name: str, enabled: bool) -> bool:
        """Enable/disable bucket versioning."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                await client.put_bucket_versioning(
                    Bucket=prefixed_name,
                    VersioningConfiguration={
                        'Status': 'Enabled' if enabled else 'Suspended'
                    }
                )
                return True

        except Exception as e:
            self.handle_error(e, "set bucket versioning")
            return False

    async def set_bucket_tags(self, bucket_name: str, tags: Dict[str, str]) -> bool:
        """Set bucket tags."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                tag_set = [{'Key': k, 'Value': v} for k, v in tags.items()]
                await client.put_bucket_tagging(
                    Bucket=prefixed_name,
                    Tagging={'TagSet': tag_set}
                )
                return True

        except Exception as e:
            self.handle_error(e, "set bucket tags")
            return False

    async def get_bucket_tags(self, bucket_name: str) -> Optional[Dict[str, str]]:
        """Get bucket tags."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                response = await client.get_bucket_tagging(Bucket=prefixed_name)
                tags = {}
                for tag in response.get('TagSet', []):
                    tags[tag['Key']] = tag['Value']
                return tags

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'NoSuchTagSet':
                return {}
            return self.handle_error(e, "get bucket tags")
        except Exception as e:
            return self.handle_error(e, "get bucket tags")

    # ============================================
    # Object Tags
    # ============================================

    async def set_object_tags(self, bucket_name: str, object_key: str, tags: Dict[str, str]) -> bool:
        """Set object tags."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                tag_set = [{'Key': k, 'Value': v} for k, v in tags.items()]
                await client.put_object_tagging(
                    Bucket=prefixed_name,
                    Key=object_key,
                    Tagging={'TagSet': tag_set}
                )
                return True

        except Exception as e:
            self.handle_error(e, "set object tags")
            return False

    async def get_object_tags(self, bucket_name: str, object_key: str) -> Optional[Dict[str, str]]:
        """Get object tags."""
        try:
            prefixed_name = self._get_prefixed_bucket_name(bucket_name)

            async with await self._get_client() as client:
                response = await client.get_object_tagging(
                    Bucket=prefixed_name,
                    Key=object_key
                )
                tags = {}
                for tag in response.get('TagSet', []):
                    tags[tag['Key']] = tag['Value']
                return tags

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
        # Using environment variables for credentials
        async with AsyncMinIOClient(
            host='localhost',
            port=9000,
            user_id='test-user'
        ) as client:
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

            # Generate presigned URL
            url = await client.get_presigned_url('async-test-bucket', 'file0.txt')
            print(f"Presigned URL: {url}")

            # Download concurrently
            downloads = [
                {'bucket': 'async-test-bucket', 'key': f'file{i}.txt'}
                for i in range(5)
            ]
            data = await client.download_many_concurrent(downloads)
            print(f"Downloaded: {[d.decode() if d else None for d in data]}")

    asyncio.run(main())
