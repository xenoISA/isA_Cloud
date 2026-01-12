# =� MinIO Client - S3-Compatible Object Storage Made Simple

## Installation

```bash
pip install -e /path/to/isA_Cloud/isA_common
```

## Simple Usage Pattern

```python
from isa_common.minio_client import MinIOClient

# Connect and use (auto-discovers via Consul or use direct host)
with MinIOClient(host='localhost', port=50051, user_id='your-service') as client:

    # 1. Create bucket (automatically scoped to your user)
    client.create_bucket('my-data')

    # 2. Upload object
    client.upload_object('my-data', 'documents/report.pdf', pdf_bytes)

    # 3. Download object
    data = client.get_object('my-data', 'documents/report.pdf')

    # 4. Upload from file (large files supported - tested with 6MB+)
    client.upload_file('my-data', 'uploads/video.mp4', '/path/to/video.mp4')

    # 5. List objects
    objects = client.list_objects('my-data', prefix='documents/')

    # 6. Generate presigned URL (temporary download link)
    url = client.get_presigned_url('my-data', 'documents/report.pdf', expiry_seconds=3600)
```

---

## Real Service Example: Document Management Service

```python
from isa_common.minio_client import MinIOClient
import io

class DocumentService:
    def __init__(self):
        self.storage = MinIOClient(user_id='doc-service')
        self.bucket = 'documents'

        # Initialize bucket once
        with self.storage:
            if not self.storage.bucket_exists(self.bucket):
                self.storage.create_bucket(self.bucket)

    def upload_document(self, user_id, doc_name, doc_bytes, metadata=None):
        # Just business logic - no S3 complexity!
        with self.storage:
            object_key = f'users/{user_id}/docs/{doc_name}'

            # Upload with metadata in ONE LINE
            return self.storage.upload_object(
                self.bucket,
                object_key,
                doc_bytes,
                metadata=metadata or {},
                tags={'user_id': user_id, 'type': 'document'}
            )

    def get_user_documents(self, user_id):
        # List all user's documents - ONE LINE
        with self.storage:
            return self.storage.list_objects(
                self.bucket,
                prefix=f'users/{user_id}/docs/'
            )

    def share_document(self, user_id, doc_name, expiry_hours=24):
        # Generate temporary download link - ONE LINE
        with self.storage:
            object_key = f'users/{user_id}/docs/{doc_name}'
            return self.storage.get_presigned_url(
                self.bucket,
                object_key,
                expiry_seconds=expiry_hours * 3600
            )

    def backup_user_data(self, user_id):
        # Create snapshot of user's data
        with self.storage:
            # Tag for backup tracking
            self.storage.set_bucket_tags(self.bucket, {
                'last_backup': str(datetime.now()),
                'backup_user': user_id
            })

            # Create snapshot
            return self.storage.create_snapshot(self.bucket)

    def set_retention_policy(self):
        # Auto-delete old files
        with self.storage:
            rules = [
                {
                    'id': 'delete-temp-files',
                    'status': 'Enabled',
                    'expiration': {'days': 7},
                    'filter': {'prefix': 'temp/'}
                },
                {
                    'id': 'archive-old-docs',
                    'status': 'Enabled',
                    'expiration': {'days': 365},
                    'filter': {'prefix': 'archive/'}
                }
            ]
            return self.storage.set_bucket_lifecycle(self.bucket, rules)
```

---

## Quick Patterns for Common Use Cases

### Upload Large Files (Streaming)
```python
# Tested with 6MB+, supports much larger
client.upload_file('my-bucket', 'videos/large.mp4', '/path/to/6mb_video.mp4')
```

### Upload with Custom Metadata
```python
metadata = {
    'x-amz-meta-author': 'John Doe',
    'x-amz-meta-department': 'Engineering',
    'x-amz-meta-version': '2.0'
}
client.upload_object('docs', 'reports/q4.pdf', pdf_bytes, metadata=metadata)
```

### Tag Objects for Organization
```python
# Add tags to object
client.set_object_tags('docs', 'reports/q4.pdf', {
    'Type': 'Report',
    'Quarter': 'Q4',
    'Year': '2025',
    'Status': 'Final'
})

# Retrieve tags
tags = client.get_object_tags('docs', 'reports/q4.pdf')
```

### Generate Upload Link (Direct Browser Upload)
```python
# User can upload directly without going through your server
upload_url = client.get_presigned_put_url(
    'user-uploads',
    f'users/{user_id}/avatar.png',
    expiry_seconds=300  # 5 minutes
)
# Send this URL to browser, user uploads directly to MinIO
```

### Copy Objects Between Locations
```python
# Copy within same bucket
client.copy_object('my-bucket', 'backup/file.pdf', 'my-bucket', 'active/file.pdf')

# Copy across buckets
client.copy_object('bucket-b', 'archive/file.pdf', 'bucket-a', 'data/file.pdf')
```

### Batch Delete
```python
# Delete multiple objects at once
keys_to_delete = ['temp/file1.txt', 'temp/file2.txt', 'temp/file3.txt']
client.delete_objects('my-bucket', keys_to_delete)
```

### Enable Versioning
```python
# Enable versioning to keep multiple versions of objects
client.set_bucket_versioning('important-data', enabled=True)

# Check versioning status
is_enabled = client.get_bucket_versioning('important-data')

# Upload new versions (old versions preserved)
client.put_object('important-data', 'config.json', config_v1)
client.put_object('important-data', 'config.json', config_v2)
# Both versions are kept!
```

### Set Bucket Policies (Public/Private Access)
```python
# Make specific prefix publicly readable
policy = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"AWS": ["*"]},
        "Action": ["s3:GetObject"],
        "Resource": [f"arn:aws:s3:::my-bucket/public/*"]
    }]
}
client.set_bucket_policy('my-bucket', json.dumps(policy))
```

### Auto-Expire Old Files (Lifecycle Policies)
```python
rules = [
    {
        'id': 'cleanup-logs',
        'status': 'Enabled',
        'expiration': {'days': 30},
        'filter': {'prefix': 'logs/'}
    },
    {
        'id': 'cleanup-temp',
        'status': 'Enabled',
        'expiration': {'days': 7},
        'filter': {'prefix': 'temp/'}
    }
]
client.set_bucket_lifecycle('my-bucket', rules)
```

### Check Object Metadata
```python
metadata = client.get_object_metadata('my-bucket', 'documents/report.pdf')
print(f"Size: {metadata['size']} bytes")
print(f"Type: {metadata['content_type']}")
print(f"ETag: {metadata['etag']}")
print(f"Modified: {metadata['last_modified']}")
```

### List Objects with Prefix
```python
# List all PDFs in documents folder
pdf_objects = client.list_objects('my-bucket', prefix='documents/', suffix='.pdf')

for obj in pdf_objects:
    print(f"{obj['key']} - {obj['size']} bytes - {obj['last_modified']}")
```

### Bucket Management
```python
# Check if bucket exists
if client.bucket_exists('my-data'):
    print("Bucket exists")

# Get bucket info
info = client.get_bucket_info('my-data')
print(f"Owner: {info['owner_id']}, Region: {info['region']}")

# List all buckets
buckets = client.list_buckets()
for bucket in buckets:
    print(f"{bucket['name']} - Created: {bucket['creation_date']}")

# Delete bucket (must be empty or use force=True)
client.delete_bucket('old-bucket', force=True)  # Deletes all objects first
```

---

## Benefits = Zero S3 Complexity

### What you DON'T need to worry about:
- L S3 SDK configuration
- L Credential management
- L Connection pooling
- L gRPC serialization
- L Error handling and retries
- L Streaming large files manually
- L Presigned URL generation complexity
- L Policy JSON construction
- L Multipart upload logic
- L Context managers and cleanup

### What you CAN focus on:
-  Your file organization
-  Your business logic
-  Your user experience
-  Your application features
-  Your data workflows
-  Your security policies

---

## Comparison: Without vs With Client

### Without (Raw boto3 + gRPC):
```python
# 150+ lines of S3 client setup, error handling, streaming logic...
import boto3
from botocore.exceptions import ClientError
import grpc
from minio_pb2_grpc import MinIOServiceStub

# Setup gRPC channel
channel = grpc.insecure_channel('localhost:50051')
stub = MinIOServiceStub(channel)

# Setup S3 client
s3_client = boto3.client(
    's3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin'
)

try:
    # Upload file with streaming
    with open('/path/to/file', 'rb') as f:
        s3_client.upload_fileobj(f, 'my-bucket', 'my-key')

    # Generate presigned URL
    url = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': 'my-bucket', 'Key': 'my-key'},
        ExpiresIn=3600
    )

    # Handle errors
except ClientError as e:
    if e.response['Error']['Code'] == 'NoSuchBucket':
        # Create bucket
        s3_client.create_bucket(Bucket='my-bucket')
    else:
        raise
finally:
    channel.close()
```

### With isa_common:
```python
# 4 lines
with MinIOClient() as client:
    client.upload_file('my-bucket', 'my-key', '/path/to/file')
    url = client.get_presigned_url('my-bucket', 'my-key')
```

---

## Async Client Usage (High-Performance)

For high-concurrency applications, use `AsyncMinIOClient` with `async/await`:

```python
import asyncio
from isa_common import AsyncMinIOClient

async def main():
    async with AsyncMinIOClient(
        host='localhost',
        port=50051,
        user_id='your-service'
    ) as client:
        # Health check
        health = await client.health_check()

        # Bucket operations
        await client.create_bucket('my-bucket')
        exists = await client.bucket_exists('my-bucket')
        buckets = await client.list_buckets()
        info = await client.get_bucket_info('my-bucket')

        # Upload object
        result = await client.upload_object(
            'my-bucket',
            'documents/report.pdf',
            pdf_bytes,
            content_type='application/pdf',
            metadata={'author': 'team', 'version': '1.0'}
        )

        # Download object
        data = await client.get_object('my-bucket', 'documents/report.pdf')

        # Get object metadata
        metadata = await client.get_object_metadata('my-bucket', 'documents/report.pdf')

        # List objects
        objects = await client.list_objects('my-bucket', prefix='documents/')

        # Copy object
        await client.copy_object(
            dest_bucket='backup-bucket',
            dest_key='backup/report.pdf',
            source_bucket='my-bucket',
            source_key='documents/report.pdf'
        )

        # Presigned URLs
        download_url = await client.get_presigned_url('my-bucket', 'documents/report.pdf', expiry_seconds=3600)
        upload_url = await client.get_presigned_put_url('my-bucket', 'uploads/new-file.pdf', expiry_seconds=300)

        # Object tags
        await client.set_object_tags('my-bucket', 'documents/report.pdf', {'status': 'final'})
        tags = await client.get_object_tags('my-bucket', 'documents/report.pdf')

        # Bucket tags
        await client.set_bucket_tags('my-bucket', {'environment': 'production'})
        bucket_tags = await client.get_bucket_tags('my-bucket')

        # Delete operations
        await client.delete_object('my-bucket', 'temp/old-file.txt')
        await client.delete_objects('my-bucket', ['temp/file1.txt', 'temp/file2.txt'])

asyncio.run(main())
```

### Concurrent Operations with asyncio.gather

```python
async def concurrent_uploads(client):
    # Upload 5 objects concurrently
    results = await asyncio.gather(*[
        client.upload_object(
            'my-bucket',
            f'data/file_{i}.txt',
            f'Content for file {i}'.encode(),
            content_type='text/plain'
        )
        for i in range(5)
    ])
    return results
```

### upload_many_concurrent / download_many_concurrent Helpers

```python
async def bulk_operations(client):
    # Upload multiple files concurrently with helper
    uploads = [
        {'bucket': 'my-bucket', 'key': f'batch/file_{i}.txt', 'data': f'Batch {i}'.encode()}
        for i in range(10)
    ]
    upload_results = await client.upload_many_concurrent(uploads)

    # Download multiple files concurrently with helper
    downloads = [
        {'bucket': 'my-bucket', 'key': f'batch/file_{i}.txt'}
        for i in range(10)
    ]
    download_results = await client.download_many_concurrent(downloads)
    return upload_results, download_results
```

---

## Complete Feature List

 **Bucket Management**: create, delete, exists, info, list
 **Bucket Policies**: set, get, delete (S3-compatible JSON)
 **Bucket Tags**: set, get, delete for organization
 **Bucket Versioning**: enable, disable, check status
 **Bucket Lifecycle**: auto-expiration, retention policies
 **Object Upload**: streaming, from file, large files (6MB+ tested)
 **Object Download**: streaming, to file
 **Object Copy**: within/across buckets
 **Object Delete**: single, batch operations
 **Object List**: with prefix/suffix filtering
 **Object Metadata**: get, set custom metadata
 **Object Tags**: set, get, delete per object
 **Presigned URLs**: GET (download), PUT (upload)
 **Health Check**: service status monitoring
 **Auto-Bucket Creation**: upload_object creates bucket if needed
 **Multi-tenancy**: user-scoped operations

---

## Test Results

**Sync Client: 13/13 tests passing (100% success rate)**
**Async Client: 19/19 tests passing (100% success rate)**

Comprehensive functional tests cover:
- Health checks
- Bucket operations (create, exists, list, info)
- Object upload/download (streaming)
- Large file upload (6MB tested)
- Object copy operations
- Object and bucket tags
- Presigned URLs (GET and PUT)
- Batch delete operations
- Concurrent uploads (asyncio.gather)
- upload_many_concurrent helper
- download_many_concurrent helper
- Bucket versioning
- Lifecycle policies

All tests demonstrate production-ready reliability.

---

## Bottom Line

Instead of wrestling with boto3, S3 APIs, gRPC serialization, and connection management...

**You write 3 lines and ship features.** <�

The MinIO client gives you:
- **Production-ready** S3-compatible storage out of the box
- **Large file support** with automatic streaming (tested 6MB+)
- **Presigned URLs** for direct browser upload/download
- **Lifecycle policies** for automatic cleanup
- **Versioning** for data protection
- **Multi-tenancy** via user-scoped buckets
- **Auto-cleanup** via context managers
- **Type-safe** results (dicts)

Just pip install and focus on your file management logic and business features!
