#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MinIO gRPC Client

MinIO/S3 Object Storage Best Practices Implementation
======================================================

Naming Conventions:
-------------------
Bucket Names (S3 DNS-compliant):
    - 3-63 characters, lowercase letters, numbers, hyphens
    - Must start/end with letter or number
    - No underscores, uppercase, or IP address format
    - Examples: my-app-data, user-uploads-2024, logs-production

Object Keys (hierarchical with /):
    - Max 1024 bytes UTF-8
    - Use / as delimiter for logical folders
    - Avoid \\ and : characters
    - Avoid namespace collisions (object vs prefix)
    - Examples: uploads/2024/01/file.pdf, users/{user_id}/avatar.png

Upload Patterns:
----------------
Small Files (< 5MB):
    - Single PUT operation via streaming gRPC
    - 64KB chunks for efficient transfer

Large Files (5MB - 5TB):
    - Multipart upload recommended for files > 100MB
    - Part size: 5MB minimum, 5GB maximum
    - Parallel part uploads for better throughput
    - Resumable uploads support

Download Patterns:
------------------
Streaming Download:
    - Uses server-streaming gRPC
    - Memory-efficient for large files
    - Supports range requests for partial downloads

Presigned URLs:
---------------
Security Best Practices:
    - Short expiration (1 hour default, max 7 days)
    - Content-Type validation for uploads
    - Consider one-time use tokens for sensitive data
    - Sanitize user input for object keys (prevent path traversal)

Lifecycle & Retention:
----------------------
Lifecycle Rules:
    - Expiration: Auto-delete after N days
    - Transition: Move to different storage class
    - Filter by prefix for targeted rules

Object Lock (WORM):
    - Governance mode: Protected but deletable with permissions
    - Compliance mode: Immutable until retention expires
    - Legal holds: Indefinite protection

References:
-----------
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-keys.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html
"""

import re
import logging
from typing import List, Dict, Optional, Iterator, Callable, TYPE_CHECKING
from .base_client import BaseGRPCClient
from .proto import minio_service_pb2, minio_service_pb2_grpc

if TYPE_CHECKING:
    from .consul_client import ConsulRegistry

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Upload thresholds
SMALL_FILE_THRESHOLD = 5 * 1024 * 1024  # 5MB - below this, single upload
MULTIPART_THRESHOLD = 100 * 1024 * 1024  # 100MB - above this, strongly recommend multipart
DEFAULT_CHUNK_SIZE = 64 * 1024  # 64KB for streaming
MULTIPART_MIN_SIZE = 5 * 1024 * 1024  # 5MB minimum part size
MULTIPART_MAX_SIZE = 5 * 1024 * 1024 * 1024  # 5GB maximum part size

# Presigned URL defaults
DEFAULT_PRESIGN_EXPIRY = 3600  # 1 hour
MAX_PRESIGN_EXPIRY = 7 * 24 * 3600  # 7 days (IAM user limit)
MIN_PRESIGN_EXPIRY = 60  # 1 minute minimum

# =============================================================================
# Naming Validation Helpers
# =============================================================================

def validate_bucket_name(name: str) -> bool:
    """
    Validate bucket name follows S3/MinIO DNS-compliant naming rules.

    Rules:
        - 3-63 characters
        - Lowercase letters, numbers, hyphens only
        - Must start and end with letter or number
        - Cannot be formatted as IP address
        - Cannot start with 'xn--'

    Valid: my-bucket, data-2024, logs-prod
    Invalid: My_Bucket, 192.168.1.1, xn--bucket
    """
    if not name or len(name) < 3 or len(name) > 63:
        return False

    # Must be lowercase, alphanumeric, or hyphens
    if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$', name) and len(name) > 2:
        return False
    if len(name) <= 2 and not re.match(r'^[a-z0-9]+$', name):
        return False

    # Cannot look like IP address
    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', name):
        return False

    # Cannot start with xn--
    if name.startswith('xn--'):
        return False

    return True


def validate_object_key(key: str) -> bool:
    """
    Validate object key follows S3/MinIO naming guidelines.

    Rules:
        - Max 1024 bytes UTF-8
        - No backslash or colon characters
        - Should not create namespace collisions

    Valid: uploads/2024/file.pdf, data/users/123/avatar.png
    Invalid: uploads\\file.pdf, data:file.txt
    """
    if not key or len(key.encode('utf-8')) > 1024:
        return False

    # No backslash or colon
    if '\\' in key or ':' in key:
        return False

    return True


def sanitize_bucket_name(name: str) -> str:
    """
    Sanitize a string to be a valid bucket name.

    Transformations:
        - Lowercase
        - Replace underscores/spaces with hyphens
        - Remove invalid characters
        - Ensure starts/ends with alphanumeric
    """
    # Lowercase and replace common invalid chars
    name = name.lower()
    name = re.sub(r'[_\s]+', '-', name)
    name = re.sub(r'[^a-z0-9-]', '', name)

    # Remove leading/trailing hyphens
    name = name.strip('-')

    # Ensure minimum length
    if len(name) < 3:
        name = name + '-bucket'

    # Truncate to max length
    if len(name) > 63:
        name = name[:63].rstrip('-')

    return name


def sanitize_object_key(key: str) -> str:
    """
    Sanitize object key to prevent path traversal and invalid characters.

    Security: Removes ../, leading /, and invalid characters
    """
    # Remove path traversal attempts
    key = re.sub(r'\.\./', '', key)
    key = re.sub(r'\.\.\\', '', key)

    # Remove invalid characters
    key = key.replace('\\', '/').replace(':', '_')

    # Remove leading slashes
    key = key.lstrip('/')

    return key


def suggest_bucket_name(prefix: str, suffix: str = '') -> str:
    """
    Generate a suggested bucket name from components.

    Example: suggest_bucket_name('user', 'uploads') -> 'user-uploads'
    """
    parts = [sanitize_bucket_name(p) for p in [prefix, suffix] if p]
    return '-'.join(parts)


# =============================================================================
# MinIO Client
# =============================================================================

class MinIOClient(BaseGRPCClient):
    """
    MinIO gRPC Client with S3 best practices.

    Features:
        - Automatic naming validation with warnings
        - Streaming upload/download for memory efficiency
        - Multipart upload support for large files
        - Presigned URL generation with security defaults
        - Lifecycle and retention management

    Usage:
        ```python
        with MinIOClient(host='localhost', port=50051, user_id='user-123') as client:
            # Upload small file
            client.upload_object('my-bucket', 'data/file.txt', b'content')

            # Upload large file with progress
            with open('large.zip', 'rb') as f:
                client.upload_large_file('my-bucket', 'backups/large.zip', f)

            # Download with streaming
            for chunk in client.download_stream('my-bucket', 'data/file.txt'):
                process(chunk)

            # Generate presigned URL (1 hour expiry)
            url = client.get_presigned_url('my-bucket', 'data/file.txt')
        ```
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None,
                 user_id: Optional[str] = None,
                 lazy_connect: bool = True, enable_compression: bool = True,
                 enable_retry: bool = True,
                 consul_registry: Optional['ConsulRegistry'] = None,
                 service_name_override: Optional[str] = None,
                 validate_naming: bool = True):
        """
        Initialize MinIO client.

        Args:
            host: Service host (optional, uses Consul if not provided)
            port: Service port (optional, uses Consul if not provided)
            user_id: User ID for multi-tenant isolation
            lazy_connect: Delay connection until first use
            enable_compression: Enable gRPC compression
            enable_retry: Enable automatic retries
            consul_registry: ConsulRegistry for service discovery
            service_name_override: Override service name for Consul
            validate_naming: Warn about naming convention violations
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
        self.validate_naming = validate_naming

    def _create_stub(self):
        """Create MinIO service stub"""
        return minio_service_pb2_grpc.MinIOServiceStub(self.channel)

    def service_name(self) -> str:
        return "MinIO"

    def default_port(self) -> int:
        return 50051

    def _validate_bucket(self, bucket_name: str) -> None:
        """Validate and warn about bucket naming issues"""
        if self.validate_naming and not validate_bucket_name(bucket_name):
            suggested = sanitize_bucket_name(bucket_name)
            logger.warning(
                f"[MinIO] Bucket name '{bucket_name}' doesn't follow S3 naming rules. "
                f"Suggested: '{suggested}'"
            )

    def _validate_object_key(self, object_key: str) -> None:
        """Validate and warn about object key issues"""
        if self.validate_naming and not validate_object_key(object_key):
            sanitized = sanitize_object_key(object_key)
            logger.warning(
                f"[MinIO] Object key '{object_key}' contains invalid characters. "
                f"Sanitized: '{sanitized}'"
            )

    # =========================================================================
    # Health Check
    # =========================================================================

    def health_check(self, detailed: bool = True) -> Optional[Dict]:
        """
        Check MinIO service health.

        Args:
            detailed: Include storage details

        Returns:
            Health status dict or None on failure
        """
        try:
            self._ensure_connected()
            request = minio_service_pb2.MinIOHealthCheckRequest(detailed=detailed)
            response = self.stub.HealthCheck(request)

            return {
                'status': response.status,
                'healthy': response.healthy,
                'details': self._proto_struct_to_dict(response.details) if response.details else {}
            }

        except Exception as e:
            return self.handle_error(e, "health check")

    # =========================================================================
    # Bucket Management
    # =========================================================================

    def create_bucket(self, bucket_name: str, organization_id: str = 'default-org',
                     region: str = 'us-east-1') -> Optional[Dict]:
        """
        Create a new bucket.

        Naming Rules:
            - 3-63 characters, lowercase
            - Letters, numbers, hyphens only
            - Must start/end with letter or number

        Args:
            bucket_name: Bucket name (will be prefixed with user context by server)
            organization_id: Organization for multi-tenant isolation
            region: Storage region

        Returns:
            {'success': True, 'bucket': 'actual-bucket-name'} or None

        Example:
            result = client.create_bucket('my-data')
            # Server creates: user-{user_id}-my-data
        """
        try:
            self._validate_bucket(bucket_name)
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
                    'bucket': response.bucket_info.name if response.bucket_info else bucket_name,
                    'message': response.message
                }
            else:
                logger.warning(f"[MinIO] Create bucket failed: {response.message}")
                return None

        except Exception as e:
            return self.handle_error(e, "create bucket")

    def delete_bucket(self, bucket_name: str, force: bool = False) -> bool:
        """
        Delete a bucket.

        Args:
            bucket_name: Bucket to delete
            force: If True, delete all objects first

        Returns:
            True if deleted, False otherwise
        """
        try:
            self._ensure_connected()
            request = minio_service_pb2.DeleteBucketRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                force=force
            )

            response = self.stub.DeleteBucket(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "delete bucket")
            return False

    def list_buckets(self, organization_id: str = 'default-org') -> List[str]:
        """
        List all accessible buckets.

        Returns:
            List of bucket names
        """
        try:
            self._ensure_connected()
            request = minio_service_pb2.ListBucketsRequest(
                user_id=self.user_id,
                organization_id=organization_id
            )

            response = self.stub.ListBuckets(request)

            if response.success:
                return [bucket.name for bucket in response.buckets]
            return []

        except Exception as e:
            return self.handle_error(e, "list buckets") or []

    def bucket_exists(self, bucket_name: str) -> bool:
        """Check if bucket exists"""
        try:
            info = self.get_bucket_info(bucket_name)
            return info is not None
        except Exception:
            return False

    def get_bucket_info(self, bucket_name: str) -> Optional[Dict]:
        """
        Get bucket metadata.

        Returns:
            Bucket info dict or None
        """
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetBucketInfoRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = self.stub.GetBucketInfo(request)

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

    # =========================================================================
    # Bucket Policy
    # =========================================================================

    def set_bucket_policy(self, bucket_name: str, policy: str) -> bool:
        """Set bucket access policy (JSON)"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.SetBucketPolicyRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                policy_type=minio_service_pb2.BUCKET_POLICY_CUSTOM,
                custom_policy=policy
            )

            response = self.stub.SetBucketPolicy(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "set bucket policy")
            return False

    def get_bucket_policy(self, bucket_name: str) -> Optional[str]:
        """Get bucket access policy"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetBucketPolicyRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = self.stub.GetBucketPolicy(request)
            return response.policy_json if response.success else None

        except Exception as e:
            return self.handle_error(e, "get bucket policy")

    def delete_bucket_policy(self, bucket_name: str) -> bool:
        """Delete bucket policy"""
        return self.set_bucket_policy(bucket_name, "")

    # =========================================================================
    # Bucket Tags
    # =========================================================================

    def set_bucket_tags(self, bucket_name: str, tags: Dict[str, str]) -> bool:
        """Set bucket tags for organization/billing"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.SetBucketTagsRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                tags=tags
            )

            response = self.stub.SetBucketTags(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "set bucket tags")
            return False

    def get_bucket_tags(self, bucket_name: str) -> Optional[Dict[str, str]]:
        """Get bucket tags"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetBucketTagsRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = self.stub.GetBucketTags(request)
            return dict(response.tags) if response.success else None

        except Exception as e:
            return self.handle_error(e, "get bucket tags")

    def delete_bucket_tags(self, bucket_name: str) -> bool:
        """Delete bucket tags"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.DeleteBucketTagsRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = self.stub.DeleteBucketTags(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "delete bucket tags")
            return False

    # =========================================================================
    # Bucket Versioning
    # =========================================================================

    def set_bucket_versioning(self, bucket_name: str, enabled: bool) -> bool:
        """
        Enable/disable bucket versioning.

        Note: Once enabled, versioning cannot be disabled, only suspended.
        Required for Object Lock.
        """
        try:
            self._ensure_connected()
            request = minio_service_pb2.SetBucketVersioningRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                enabled=enabled
            )

            response = self.stub.SetBucketVersioning(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "set bucket versioning")
            return False

    def get_bucket_versioning(self, bucket_name: str) -> bool:
        """Get bucket versioning status"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetBucketVersioningRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = self.stub.GetBucketVersioning(request)
            return response.enabled if response.success else False

        except Exception as e:
            self.handle_error(e, "get bucket versioning")
            return False

    # =========================================================================
    # Bucket Lifecycle
    # =========================================================================

    def set_bucket_lifecycle(self, bucket_name: str, rules: List[Dict]) -> bool:
        """
        Set bucket lifecycle rules for automatic object management.

        Common Use Cases:
            - Auto-delete temporary files after N days
            - Transition old data to cheaper storage
            - Clean up incomplete multipart uploads

        Args:
            bucket_name: Target bucket
            rules: List of lifecycle rules

        Rule Format:
            {
                'id': 'rule-name',
                'status': 'Enabled',  # or 'Disabled'
                'filter': {'prefix': 'logs/'},
                'expiration': {'days': 30},
                'transition': {'days': 90, 'storage_class': 'GLACIER'}
            }

        Example:
            rules = [
                {
                    'id': 'delete-temp-files',
                    'status': 'Enabled',
                    'filter': {'prefix': 'temp/'},
                    'expiration': {'days': 7}
                },
                {
                    'id': 'archive-old-logs',
                    'status': 'Enabled',
                    'filter': {'prefix': 'logs/'},
                    'expiration': {'days': 365}
                }
            ]
            client.set_bucket_lifecycle('my-bucket', rules)
        """
        try:
            self._ensure_connected()

            lifecycle_rules = []
            for rule in rules:
                lifecycle_rule = minio_service_pb2.LifecycleRule()
                lifecycle_rule.id = rule.get('id', '')
                lifecycle_rule.status = rule.get('status', 'Enabled')

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
            return response.success

        except Exception as e:
            self.handle_error(e, "set bucket lifecycle")
            return False

    def get_bucket_lifecycle(self, bucket_name: str) -> Optional[List[Dict]]:
        """Get bucket lifecycle rules"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetBucketLifecycleRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = self.stub.GetBucketLifecycle(request)

            if response.success:
                from google.protobuf.json_format import MessageToDict
                return [MessageToDict(rule) for rule in response.rules]
            return None

        except Exception as e:
            return self.handle_error(e, "get bucket lifecycle")

    def delete_bucket_lifecycle(self, bucket_name: str) -> bool:
        """Delete bucket lifecycle rules"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.DeleteBucketLifecycleRequest(
                bucket_name=bucket_name,
                user_id=self.user_id
            )

            response = self.stub.DeleteBucketLifecycle(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "delete bucket lifecycle")
            return False

    # =========================================================================
    # Object Upload - Standard (< 100MB)
    # =========================================================================

    def upload_object(self, bucket_name: str, object_key: str, data: bytes,
                     content_type: str = 'application/octet-stream',
                     metadata: Optional[Dict[str, str]] = None,
                     auto_create_bucket: bool = True) -> Optional[Dict]:
        """
        Upload object using streaming gRPC.

        Best for files < 100MB. For larger files, use upload_large_file().

        Args:
            bucket_name: Target bucket
            object_key: Object path (e.g., 'uploads/2024/file.pdf')
            data: File content as bytes
            content_type: MIME type
            metadata: Custom metadata dict
            auto_create_bucket: Create bucket if not exists

        Returns:
            {'success': True, 'object_key': '...', 'size': N, 'etag': '...'}
        """
        try:
            self._validate_bucket(bucket_name)
            self._validate_object_key(object_key)
            self._ensure_connected()

            # Recommend multipart for large files
            if len(data) > MULTIPART_THRESHOLD:
                logger.info(
                    f"[MinIO] File size {len(data)} bytes > {MULTIPART_THRESHOLD}. "
                    "Consider using upload_large_file() for better reliability."
                )

            # Auto-create bucket if needed
            if auto_create_bucket and not self.bucket_exists(bucket_name):
                create_result = self.create_bucket(bucket_name)
                if not create_result or not create_result.get('success'):
                    return {
                        'success': False,
                        'error': f"Failed to create bucket '{bucket_name}'"
                    }

            def request_generator():
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

            response = self.stub.PutObject(request_generator())

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

    def upload_file(self, bucket_name: str, object_key: str, file_path: str,
                   content_type: str = 'application/octet-stream') -> bool:
        """
        Upload file from filesystem.

        For large files, reads in chunks to avoid memory issues.
        """
        try:
            import os
            file_size = os.path.getsize(file_path)

            if file_size > MULTIPART_THRESHOLD:
                # Use streaming upload for large files
                with open(file_path, 'rb') as f:
                    return self.upload_large_file(
                        bucket_name, object_key, f,
                        file_size=file_size, content_type=content_type
                    )
            else:
                with open(file_path, 'rb') as f:
                    data = f.read()
                result = self.upload_object(
                    bucket_name, object_key, data, content_type=content_type
                )
                return result is not None

        except Exception as e:
            self.handle_error(e, "upload file")
            return False

    def upload_large_file(self, bucket_name: str, object_key: str,
                          file_obj, file_size: int = None,
                          content_type: str = 'application/octet-stream',
                          chunk_size: int = MULTIPART_MIN_SIZE,
                          progress_callback: Optional[Callable[[int, int], None]] = None) -> bool:
        """
        Upload large file using streaming with progress support.

        Best Practices for Large Files (> 100MB):
            - Uses chunked streaming to minimize memory usage
            - Supports progress callbacks for UI feedback
            - Chunk size defaults to 5MB (minimum for S3 multipart)

        Args:
            bucket_name: Target bucket
            object_key: Object path
            file_obj: File-like object with read() method
            file_size: Total size (optional, for progress reporting)
            content_type: MIME type
            chunk_size: Chunk size (default 5MB)
            progress_callback: func(bytes_sent, total_bytes)

        Returns:
            True if uploaded successfully

        Example:
            def on_progress(sent, total):
                print(f"Uploaded {sent}/{total} bytes ({100*sent/total:.1f}%)")

            with open('large.zip', 'rb') as f:
                client.upload_large_file(
                    'backups', 'archive.zip', f,
                    file_size=os.path.getsize('large.zip'),
                    progress_callback=on_progress
                )
        """
        try:
            self._validate_bucket(bucket_name)
            self._validate_object_key(object_key)
            self._ensure_connected()

            if not self.bucket_exists(bucket_name):
                create_result = self.create_bucket(bucket_name)
                if not create_result:
                    return False

            bytes_sent = 0

            def request_generator():
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

            response = self.stub.PutObject(request_generator())
            return response.success

        except Exception as e:
            self.handle_error(e, "upload large file")
            return False

    # =========================================================================
    # Object Download
    # =========================================================================

    def get_object(self, bucket_name: str, object_key: str) -> Optional[bytes]:
        """
        Download object to memory.

        For large files, use download_stream() or download_to_file().
        """
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
                    continue
                elif response.HasField('chunk'):
                    data.extend(response.chunk)

            return bytes(data)

        except Exception as e:
            return self.handle_error(e, "get object")

    def download_stream(self, bucket_name: str, object_key: str) -> Iterator[bytes]:
        """
        Stream download for memory-efficient large file handling.

        Yields chunks as they arrive, no full file buffering.

        Example:
            with open('output.bin', 'wb') as f:
                for chunk in client.download_stream('bucket', 'large.bin'):
                    f.write(chunk)
        """
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetObjectRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            for response in self.stub.GetObject(request):
                if response.HasField('chunk'):
                    yield response.chunk

        except Exception as e:
            self.handle_error(e, "download stream")

    def download_to_file(self, bucket_name: str, object_key: str,
                         file_path: str,
                         progress_callback: Optional[Callable[[int, int], None]] = None) -> bool:
        """
        Download object directly to file with progress support.

        Args:
            bucket_name: Source bucket
            object_key: Object path
            file_path: Local destination path
            progress_callback: func(bytes_received, total_bytes)

        Returns:
            True if downloaded successfully
        """
        try:
            # Get size first for progress reporting
            metadata = self.get_object_metadata(bucket_name, object_key)
            total_size = metadata.get('size', 0) if metadata else 0

            bytes_received = 0
            with open(file_path, 'wb') as f:
                for chunk in self.download_stream(bucket_name, object_key):
                    f.write(chunk)
                    bytes_received += len(chunk)

                    if progress_callback and total_size:
                        progress_callback(bytes_received, total_size)

            return True

        except Exception as e:
            self.handle_error(e, "download to file")
            return False

    # =========================================================================
    # Object Management
    # =========================================================================

    def list_objects(self, bucket_name: str, prefix: str = '',
                    max_keys: int = 1000, recursive: bool = True) -> List[Dict]:
        """
        List objects in bucket.

        Args:
            bucket_name: Target bucket
            prefix: Filter by prefix (e.g., 'uploads/2024/')
            max_keys: Maximum results
            recursive: Include objects in sub-prefixes

        Returns:
            List of object info dicts
        """
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
                return [
                    {
                        'name': obj.key,
                        'key': obj.key,
                        'size': obj.size,
                        'content_type': obj.content_type,
                        'etag': obj.etag,
                        'last_modified': obj.last_modified if hasattr(obj, 'last_modified') else None
                    }
                    for obj in response.objects
                ]
            return []

        except Exception as e:
            return self.handle_error(e, "list objects") or []

    def delete_object(self, bucket_name: str, object_key: str) -> bool:
        """Delete single object"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.DeleteObjectRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            response = self.stub.DeleteObject(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "delete object")
            return False

    def delete_objects(self, bucket_name: str, object_keys: List[str]) -> bool:
        """Batch delete objects"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.DeleteObjectsRequest(
                bucket_name=bucket_name,
                user_id=self.user_id,
                object_keys=object_keys,
                quiet=False
            )

            response = self.stub.DeleteObjects(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "delete objects")
            return False

    def copy_object(self, dest_bucket: str, dest_key: str,
                   source_bucket: str, source_key: str) -> bool:
        """Copy object between buckets or within bucket"""
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
            return response.success

        except Exception as e:
            self.handle_error(e, "copy object")
            return False

    def get_object_metadata(self, bucket_name: str, object_key: str) -> Optional[Dict]:
        """Get object metadata without downloading content"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.StatObjectRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            response = self.stub.StatObject(request)

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

    # =========================================================================
    # Object Tags
    # =========================================================================

    def set_object_tags(self, bucket_name: str, object_key: str,
                       tags: Dict[str, str]) -> bool:
        """Set object tags"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.SetObjectTagsRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id,
                tags=tags
            )

            response = self.stub.SetObjectTags(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "set object tags")
            return False

    def get_object_tags(self, bucket_name: str, object_key: str) -> Optional[Dict[str, str]]:
        """Get object tags"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.GetObjectTagsRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            response = self.stub.GetObjectTags(request)
            return dict(response.tags) if response.success else None

        except Exception as e:
            return self.handle_error(e, "get object tags")

    def delete_object_tags(self, bucket_name: str, object_key: str) -> bool:
        """Delete object tags"""
        try:
            self._ensure_connected()
            request = minio_service_pb2.DeleteObjectTagsRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id
            )

            response = self.stub.DeleteObjectTags(request)
            return response.success

        except Exception as e:
            self.handle_error(e, "delete object tags")
            return False

    # =========================================================================
    # Presigned URLs
    # =========================================================================

    def get_presigned_url(self, bucket_name: str, object_key: str,
                         expiry_seconds: int = DEFAULT_PRESIGN_EXPIRY) -> Optional[str]:
        """
        Generate presigned URL for download (GET).

        Security Best Practices:
            - Use shortest expiry that meets your needs
            - Default: 1 hour, Max: 7 days
            - URLs are reusable until expiry
            - Consider server-side validation for sensitive data

        Args:
            bucket_name: Target bucket
            object_key: Object path
            expiry_seconds: URL validity period (default 1 hour)

        Returns:
            Presigned URL string or None
        """
        try:
            # Enforce limits
            expiry_seconds = max(MIN_PRESIGN_EXPIRY,
                               min(expiry_seconds, MAX_PRESIGN_EXPIRY))

            self._ensure_connected()
            request = minio_service_pb2.GetPresignedURLRequest(
                bucket_name=bucket_name,
                object_key=object_key,
                user_id=self.user_id,
                expiry_seconds=expiry_seconds
            )

            response = self.stub.GetPresignedURL(request)
            return response.url if response.success else None

        except Exception as e:
            return self.handle_error(e, "get presigned URL")

    def get_presigned_put_url(self, bucket_name: str, object_key: str,
                              expiry_seconds: int = DEFAULT_PRESIGN_EXPIRY,
                              content_type: str = 'application/octet-stream') -> Optional[str]:
        """
        Generate presigned URL for upload (PUT).

        Security Considerations:
            - Specify content_type to restrict file types
            - Sanitize object_key to prevent path traversal
            - Consider adding content-length limits via bucket policy

        Args:
            bucket_name: Target bucket
            object_key: Destination path (sanitize user input!)
            expiry_seconds: URL validity period
            content_type: Required content type for upload

        Returns:
            Presigned URL string or None
        """
        try:
            # Sanitize object key for security
            safe_key = sanitize_object_key(object_key)
            if safe_key != object_key:
                logger.warning(f"[MinIO] Object key sanitized: '{object_key}' -> '{safe_key}'")

            expiry_seconds = max(MIN_PRESIGN_EXPIRY,
                               min(expiry_seconds, MAX_PRESIGN_EXPIRY))

            self._ensure_connected()
            request = minio_service_pb2.GetPresignedPutURLRequest(
                bucket_name=bucket_name,
                object_key=safe_key,
                user_id=self.user_id,
                expiry_seconds=expiry_seconds,
                content_type=content_type
            )

            response = self.stub.GetPresignedPutURL(request)
            return response.url if response.success else None

        except Exception as e:
            return self.handle_error(e, "get presigned PUT URL")

    def generate_presigned_url(self, bucket_name: str, object_key: str,
                               expiry_seconds: int = DEFAULT_PRESIGN_EXPIRY,
                               method: str = 'GET',
                               content_type: str = 'application/octet-stream') -> Optional[str]:
        """
        Generate presigned URL (compatibility method).

        Args:
            method: 'GET' for download, 'PUT' for upload
        """
        if method.upper() == 'PUT':
            return self.get_presigned_put_url(bucket_name, object_key,
                                              expiry_seconds, content_type)
        return self.get_presigned_url(bucket_name, object_key, expiry_seconds)

    # =========================================================================
    # Compatibility Methods
    # =========================================================================

    def put_object(self, bucket_name: str, object_key: str, data,
                  size: int, metadata: Optional[Dict] = None) -> bool:
        """Compatibility method for put_object"""
        import io
        if isinstance(data, io.BytesIO):
            data = data.read()
        elif not isinstance(data, bytes):
            data = bytes(data)

        result = self.upload_object(bucket_name, object_key, data, metadata=metadata or {})
        return result is not None

    def list_object_versions(self, bucket_name: str, object_key: str) -> Optional[List[Dict]]:
        """List object versions (requires versioning enabled)"""
        # Not implemented in current gRPC service
        return None


# =============================================================================
# Module Usage Example
# =============================================================================

if __name__ == '__main__':
    """Example usage demonstrating best practices"""

    with MinIOClient(host='localhost', port=50051, user_id='test-user') as client:
        # Health check
        health = client.health_check()
        print(f"Health: {health}")

        # Create bucket with valid name
        result = client.create_bucket('my-data-bucket')
        print(f"Create bucket: {result}")

        # Upload small file
        result = client.upload_object(
            'my-data-bucket',
            'uploads/2024/01/report.pdf',
            b'PDF content here',
            content_type='application/pdf',
            metadata={'author': 'system', 'version': '1.0'}
        )
        print(f"Upload: {result}")

        # Set lifecycle for auto-cleanup
        lifecycle_rules = [
            {
                'id': 'cleanup-temp',
                'status': 'Enabled',
                'filter': {'prefix': 'temp/'},
                'expiration': {'days': 7}
            }
        ]
        client.set_bucket_lifecycle('my-data-bucket', lifecycle_rules)

        # Generate presigned URL (1 hour expiry)
        url = client.get_presigned_url('my-data-bucket', 'uploads/2024/01/report.pdf')
        print(f"Download URL: {url}")

        # List objects
        objects = client.list_objects('my-data-bucket', prefix='uploads/')
        print(f"Objects: {objects}")
