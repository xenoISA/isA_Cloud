#!/usr/bin/env python3
"""
Async Local Storage Client
Local alternative to AsyncMinIOClient for ICP (Intelligent Personal Context) mode.

This client provides the same interface as AsyncMinIOClient but uses local filesystem,
making it suitable for local desktop usage without requiring MinIO server.

Features:
- S3-compatible bucket/object operations on local filesystem
- Streaming upload/download support
- Metadata storage via JSON sidecar files
- Multi-tenant path isolation
"""

import os
import json
import asyncio
import hashlib
import mimetypes
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, AsyncIterator, Any
from concurrent.futures import ThreadPoolExecutor

import aiofiles
import aiofiles.os

from .async_base_client import AsyncBaseClient


class AsyncLocalStorageClient(AsyncBaseClient):
    """
    Async local storage client - drop-in replacement for AsyncMinIOClient.

    Provides the same interface as AsyncMinIOClient for local ICP mode.
    All objects are stored as files in the local filesystem.

    Structure:
        base_path/
        └── user-{user_id}/
            └── {bucket}/
                ├── {object_key}
                └── {object_key}.meta.json  (metadata)
    """

    # Class-level configuration
    SERVICE_NAME = "LocalStorage"
    DEFAULT_HOST = "localhost"  # Not used, but kept for interface compatibility
    DEFAULT_PORT = 0  # Local storage, no port
    ENV_PREFIX = "LOCAL_STORAGE"
    TENANT_SEPARATOR = "-"  # user-{user_id}-{bucket}

    def __init__(
        self,
        base_path: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize async local storage client.

        Args:
            base_path: Base directory for storage (default: ~/.isa_mcp/storage)
            **kwargs: Base client args (user_id, organization_id, lazy_connect)
        """
        super().__init__(**kwargs)

        # Determine base path
        if base_path:
            self._base_path = Path(base_path)
        else:
            default_path = os.getenv('LOCAL_STORAGE_PATH', '~/.isa_mcp/storage')
            self._base_path = Path(default_path).expanduser()

        self._executor = ThreadPoolExecutor(max_workers=4)

    async def _connect(self) -> None:
        """Initialize storage (create base directory)."""
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._logger.info(f"Local storage initialized at {self._base_path}")

    async def _disconnect(self) -> None:
        """Cleanup."""
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None

    def _get_user_path(self) -> Path:
        """Get user-specific storage path."""
        if self.user_id:
            # Sanitize user_id
            safe_user_id = self.user_id.lower().replace('_', '-').replace('|', '-')
            while '--' in safe_user_id:
                safe_user_id = safe_user_id.replace('--', '-')
            safe_user_id = safe_user_id.strip('-')
            return self._base_path / f"user-{safe_user_id}"
        return self._base_path / "default"

    def _get_bucket_path(self, bucket_name: str) -> Path:
        """Get full path for a bucket."""
        # Sanitize bucket name
        safe_bucket = bucket_name.lower().replace('_', '-')
        while '--' in safe_bucket:
            safe_bucket = safe_bucket.replace('--', '-')
        safe_bucket = safe_bucket.strip('-')

        return self._get_user_path() / safe_bucket

    def _get_object_path(self, bucket_name: str, object_key: str) -> Path:
        """Get full path for an object."""
        bucket_path = self._get_bucket_path(bucket_name)
        # Preserve object key path structure
        return bucket_path / object_key

    def _get_metadata_path(self, object_path: Path) -> Path:
        """Get metadata sidecar file path."""
        return object_path.parent / f"{object_path.name}.meta.json"

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self) -> Optional[Dict]:
        """Check storage health."""
        try:
            await self._ensure_connected()

            # Check base path is writable
            test_file = self._base_path / '.health_check'
            async with aiofiles.open(test_file, 'w') as f:
                await f.write('ok')
            await aiofiles.os.remove(test_file)

            # Get storage stats
            user_path = self._get_user_path()
            bucket_count = 0
            if user_path.exists():
                bucket_count = len([d for d in user_path.iterdir() if d.is_dir()])

            return {
                'healthy': True,
                'storage_type': 'local_filesystem',
                'base_path': str(self._base_path),
                'user_buckets': bucket_count
            }

        except Exception as e:
            return self.handle_error(e, "health check")

    # ============================================
    # Bucket Operations
    # ============================================

    async def create_bucket(self, bucket_name: str) -> Optional[bool]:
        """Create a bucket (directory)."""
        try:
            await self._ensure_connected()

            bucket_path = self._get_bucket_path(bucket_name)
            bucket_path.mkdir(parents=True, exist_ok=True)

            return True

        except Exception as e:
            return self.handle_error(e, "create bucket")

    async def bucket_exists(self, bucket_name: str) -> bool:
        """Check if bucket exists."""
        try:
            await self._ensure_connected()

            bucket_path = self._get_bucket_path(bucket_name)
            return bucket_path.exists() and bucket_path.is_dir()

        except Exception as e:
            self.handle_error(e, "bucket exists")
            return False

    async def delete_bucket(self, bucket_name: str) -> Optional[bool]:
        """Delete a bucket (must be empty)."""
        try:
            await self._ensure_connected()

            bucket_path = self._get_bucket_path(bucket_name)
            if not bucket_path.exists():
                return True

            # Check if empty (excluding metadata files)
            contents = [f for f in bucket_path.iterdir() if not f.name.endswith('.meta.json')]
            if contents:
                self._logger.error(f"Bucket {bucket_name} is not empty")
                return False

            # Remove metadata files and bucket
            for f in bucket_path.iterdir():
                await aiofiles.os.remove(f)
            await aiofiles.os.rmdir(bucket_path)

            return True

        except Exception as e:
            return self.handle_error(e, "delete bucket")

    async def list_buckets(self) -> List[str]:
        """List all buckets."""
        try:
            await self._ensure_connected()

            user_path = self._get_user_path()
            if not user_path.exists():
                return []

            buckets = [d.name for d in user_path.iterdir() if d.is_dir()]
            return sorted(buckets)

        except Exception as e:
            self.handle_error(e, "list buckets")
            return []

    # ============================================
    # Object Operations
    # ============================================

    async def put_object(
        self,
        bucket_name: str,
        object_key: str,
        data: bytes,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """
        Upload object to bucket.

        Args:
            bucket_name: Bucket name
            object_key: Object key (path within bucket)
            data: Object data as bytes
            content_type: MIME type
            metadata: Custom metadata

        Returns:
            ETag (MD5 hash) if successful
        """
        try:
            await self._ensure_connected()

            # Ensure bucket exists
            await self.create_bucket(bucket_name)

            object_path = self._get_object_path(bucket_name, object_key)

            # Create parent directories
            object_path.parent.mkdir(parents=True, exist_ok=True)

            # Write object data
            async with aiofiles.open(object_path, 'wb') as f:
                await f.write(data)

            # Calculate ETag (MD5)
            etag = hashlib.md5(data).hexdigest()

            # Guess content type if not provided
            if not content_type:
                content_type, _ = mimetypes.guess_type(object_key)
                content_type = content_type or 'application/octet-stream'

            # Write metadata
            meta = {
                'content_type': content_type,
                'size': len(data),
                'etag': etag,
                'last_modified': datetime.now(timezone.utc).isoformat(),
                'metadata': metadata or {}
            }

            metadata_path = self._get_metadata_path(object_path)
            async with aiofiles.open(metadata_path, 'w') as f:
                await f.write(json.dumps(meta, indent=2))

            return etag

        except Exception as e:
            return self.handle_error(e, "put object")

    async def get_object(
        self,
        bucket_name: str,
        object_key: str
    ) -> Optional[bytes]:
        """
        Download object from bucket.

        Args:
            bucket_name: Bucket name
            object_key: Object key

        Returns:
            Object data as bytes
        """
        try:
            await self._ensure_connected()

            object_path = self._get_object_path(bucket_name, object_key)

            if not object_path.exists():
                self._logger.warning(f"Object not found: {bucket_name}/{object_key}")
                return None

            async with aiofiles.open(object_path, 'rb') as f:
                return await f.read()

        except Exception as e:
            return self.handle_error(e, "get object")

    async def get_object_stream(
        self,
        bucket_name: str,
        object_key: str,
        chunk_size: int = 64 * 1024
    ) -> AsyncIterator[bytes]:
        """
        Stream object data.

        Args:
            bucket_name: Bucket name
            object_key: Object key
            chunk_size: Chunk size in bytes

        Yields:
            Chunks of object data
        """
        try:
            await self._ensure_connected()

            object_path = self._get_object_path(bucket_name, object_key)

            if not object_path.exists():
                return

            async with aiofiles.open(object_path, 'rb') as f:
                while True:
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

        except Exception as e:
            self.handle_error(e, "get object stream")

    async def delete_object(
        self,
        bucket_name: str,
        object_key: str
    ) -> Optional[bool]:
        """Delete object from bucket."""
        try:
            await self._ensure_connected()

            object_path = self._get_object_path(bucket_name, object_key)
            metadata_path = self._get_metadata_path(object_path)

            # Delete object file
            if object_path.exists():
                await aiofiles.os.remove(object_path)

            # Delete metadata file
            if metadata_path.exists():
                await aiofiles.os.remove(metadata_path)

            return True

        except Exception as e:
            return self.handle_error(e, "delete object")

    async def delete_objects(
        self,
        bucket_name: str,
        object_keys: List[str]
    ) -> Optional[int]:
        """Delete multiple objects."""
        try:
            await self._ensure_connected()

            count = 0
            for key in object_keys:
                if await self.delete_object(bucket_name, key):
                    count += 1

            return count

        except Exception as e:
            return self.handle_error(e, "delete objects")

    async def object_exists(
        self,
        bucket_name: str,
        object_key: str
    ) -> bool:
        """Check if object exists."""
        try:
            await self._ensure_connected()

            object_path = self._get_object_path(bucket_name, object_key)
            return object_path.exists()

        except Exception as e:
            self.handle_error(e, "object exists")
            return False

    async def get_object_info(
        self,
        bucket_name: str,
        object_key: str
    ) -> Optional[Dict]:
        """Get object metadata."""
        try:
            await self._ensure_connected()

            object_path = self._get_object_path(bucket_name, object_key)
            metadata_path = self._get_metadata_path(object_path)

            if not object_path.exists():
                return None

            # Read metadata file
            if metadata_path.exists():
                async with aiofiles.open(metadata_path, 'r') as f:
                    content = await f.read()
                    meta = json.loads(content)
            else:
                # Generate basic metadata
                stat = object_path.stat()
                content_type, _ = mimetypes.guess_type(object_key)
                meta = {
                    'content_type': content_type or 'application/octet-stream',
                    'size': stat.st_size,
                    'last_modified': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    'metadata': {}
                }

            return {
                'key': object_key,
                'bucket': bucket_name,
                'size': meta.get('size', 0),
                'content_type': meta.get('content_type', 'application/octet-stream'),
                'etag': meta.get('etag', ''),
                'last_modified': meta.get('last_modified', ''),
                'metadata': meta.get('metadata', {})
            }

        except Exception as e:
            return self.handle_error(e, "get object info")

    async def list_objects(
        self,
        bucket_name: str,
        prefix: str = '',
        limit: int = 1000
    ) -> List[Dict]:
        """
        List objects in bucket.

        Args:
            bucket_name: Bucket name
            prefix: Filter by key prefix
            limit: Maximum results

        Returns:
            List of object info dictionaries
        """
        try:
            await self._ensure_connected()

            bucket_path = self._get_bucket_path(bucket_name)

            if not bucket_path.exists():
                return []

            objects = []

            # Walk directory tree
            for root, dirs, files in os.walk(bucket_path):
                for filename in files:
                    # Skip metadata files
                    if filename.endswith('.meta.json'):
                        continue

                    file_path = Path(root) / filename
                    rel_path = file_path.relative_to(bucket_path)
                    object_key = str(rel_path)

                    # Apply prefix filter
                    if prefix and not object_key.startswith(prefix):
                        continue

                    # Get object info
                    info = await self.get_object_info(bucket_name, object_key)
                    if info:
                        objects.append(info)

                    if len(objects) >= limit:
                        break

                if len(objects) >= limit:
                    break

            return objects

        except Exception as e:
            self.handle_error(e, "list objects")
            return []

    # ============================================
    # Copy/Move Operations
    # ============================================

    async def copy_object(
        self,
        source_bucket: str,
        source_key: str,
        dest_bucket: str,
        dest_key: str
    ) -> Optional[str]:
        """Copy object to new location."""
        try:
            await self._ensure_connected()

            # Get source data
            data = await self.get_object(source_bucket, source_key)
            if data is None:
                return None

            # Get source metadata
            source_info = await self.get_object_info(source_bucket, source_key)
            metadata = source_info.get('metadata', {}) if source_info else {}
            content_type = source_info.get('content_type') if source_info else None

            # Write to destination
            return await self.put_object(
                dest_bucket, dest_key, data,
                content_type=content_type,
                metadata=metadata
            )

        except Exception as e:
            return self.handle_error(e, "copy object")

    async def move_object(
        self,
        source_bucket: str,
        source_key: str,
        dest_bucket: str,
        dest_key: str
    ) -> Optional[str]:
        """Move object to new location."""
        try:
            etag = await self.copy_object(source_bucket, source_key, dest_bucket, dest_key)
            if etag:
                await self.delete_object(source_bucket, source_key)
            return etag

        except Exception as e:
            return self.handle_error(e, "move object")

    # ============================================
    # Presigned URLs (Simulated)
    # ============================================

    async def get_presigned_url(
        self,
        bucket_name: str,
        object_key: str,
        expiry_seconds: int = 3600,
        method: str = 'GET'
    ) -> Optional[str]:
        """
        Get presigned URL for object.

        Note: For local storage, returns a file:// URL.
        Real presigned URL support would require a local HTTP server.
        """
        try:
            await self._ensure_connected()

            object_path = self._get_object_path(bucket_name, object_key)

            if method == 'GET' and not object_path.exists():
                return None

            # Return file:// URL
            return f"file://{object_path.absolute()}"

        except Exception as e:
            return self.handle_error(e, "get presigned url")

    # ============================================
    # Statistics
    # ============================================

    async def get_stats(self) -> Optional[Dict]:
        """Get storage statistics."""
        try:
            await self._ensure_connected()

            user_path = self._get_user_path()

            total_size = 0
            total_objects = 0
            bucket_count = 0

            if user_path.exists():
                for bucket_dir in user_path.iterdir():
                    if bucket_dir.is_dir():
                        bucket_count += 1
                        for root, dirs, files in os.walk(bucket_dir):
                            for filename in files:
                                if not filename.endswith('.meta.json'):
                                    file_path = Path(root) / filename
                                    total_size += file_path.stat().st_size
                                    total_objects += 1

            return {
                'base_path': str(self._base_path),
                'user_path': str(user_path),
                'bucket_count': bucket_count,
                'total_objects': total_objects,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2)
            }

        except Exception as e:
            return self.handle_error(e, "get stats")


# Example usage
if __name__ == '__main__':
    async def main():
        async with AsyncLocalStorageClient(
            base_path='/tmp/isa_storage_test',
            user_id='test_user'
        ) as client:
            # Health check
            health = await client.health_check()
            print(f"Health: {health}")

            # Create bucket
            await client.create_bucket('test-bucket')

            # List buckets
            buckets = await client.list_buckets()
            print(f"Buckets: {buckets}")

            # Put object
            data = b"Hello, World!"
            etag = await client.put_object(
                'test-bucket', 'hello.txt', data,
                content_type='text/plain',
                metadata={'author': 'test'}
            )
            print(f"Uploaded, ETag: {etag}")

            # Get object
            retrieved = await client.get_object('test-bucket', 'hello.txt')
            print(f"Retrieved: {retrieved.decode()}")

            # Get object info
            info = await client.get_object_info('test-bucket', 'hello.txt')
            print(f"Info: {info}")

            # List objects
            objects = await client.list_objects('test-bucket')
            print(f"Objects: {objects}")

            # Stats
            stats = await client.get_stats()
            print(f"Stats: {stats}")

            # Cleanup
            await client.delete_object('test-bucket', 'hello.txt')
            await client.delete_bucket('test-bucket')

    asyncio.run(main())
