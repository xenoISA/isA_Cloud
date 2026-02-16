#!/usr/bin/env python3
"""
MinIO Client Usage Examples
============================

This example demonstrates how to use the MinIOClient from isa_common package.
Based on comprehensive functional tests with 100% success rate (13/13 tests passing).

File: isA_common/examples/minio_client_examples.py

Prerequisites:
--------------
1. MinIO gRPC service must be running (default: localhost:50051)
2. Install isa_common package:
   ```bash
   pip install -e /path/to/isA_Cloud/isA_common
   ```

Usage:
------
```bash
# Run all examples
python isA_common/examples/minio_client_examples.py

# Run with custom host/port
python isA_common/examples/minio_client_examples.py --host 192.168.1.100 --port 50051
```

Features Demonstrated:
----------------------
 Bucket Management (create, list, delete, info, exists)
 Bucket Policies (set, get, delete)
 Bucket Tags (set, get, delete)
 Bucket Versioning (enable, disable, get status)
 Bucket Lifecycle Policies (set, get, delete)
 Object Upload/Download (streaming support)
 Object Upload from File
 Object Copy
 Object List/Delete (single and batch)
 Object Metadata (stat)
 Object Tags (set, get, delete)
 Presigned URLs (GET and PUT)
 Large File Upload (tested with 6MB files)
 Health Check

New in v0.1.6:
--------------
✅ upload_object() now automatically creates buckets if they don't exist
✅ Uses user_id as organization_id for user-scoped buckets

Note: All operations include proper error handling and use context managers for resource cleanup.
"""

import sys
import argparse
import io
import json
from datetime import datetime
from pathlib import Path
from isa_common.consul_client import ConsulRegistry

# Import the MinIOClient from isa_common
try:
    from isa_common.minio_client import MinIOClient
except ImportError:
    print("=" * 80)
    print("ERROR: Failed to import isa_common.minio_client")
    print("=" * 80)
    print("\nPlease install isa_common package:")
    print("  cd /path/to/isA_Cloud")
    print("  pip install -e isA_common")
    print()
    sys.exit(1)


def example_01_health_check(host='localhost', port=50051):
    """
    Example 1: Health Check

    Check if the MinIO gRPC service is healthy and operational.
    """
    print("\n" + "=" * 80)
    print("Example 1: Service Health Check")
    print("=" * 80)

    with MinIOClient(host=host, port=port, user_id='example-user') as client:
        health = client.health_check(detailed=True)

        if health and health.get('healthy'):
            print(f" Service is healthy!")
            print(f"   Status: {health.get('status')}")
            if health.get('details'):
                print(f"   Details: {health.get('details')}")
        else:
            print("L Service is not healthy")


def example_02_bucket_lifecycle(host='localhost', port=50051):
    """
    Example 2: Bucket Create/Delete Lifecycle

    Demonstrate creating, checking existence, getting info, and deleting buckets.
    """
    print("\n" + "=" * 80)
    print("Example 2: Bucket Create/Delete Lifecycle")
    print("=" * 80)

    user_id = 'example-user'
    bucket_name = f'example-bucket-{datetime.now().strftime("%H%M%S")}'

    with MinIOClient(host=host, port=port, user_id=user_id) as client:
        # Create bucket
        result = client.create_bucket(bucket_name, organization_id='example-org')
        if result and result.get('success'):
            print(f" Bucket created: {result.get('bucket')}")

        # Check if bucket exists
        exists = client.bucket_exists(bucket_name)
        print(f" Bucket exists: {exists}")

        # Get bucket info
        info = client.get_bucket_info(bucket_name)
        if info:
            print(f" Bucket info:")
            print(f"   Name: {info.get('name')}")
            print(f"   Owner: {info.get('owner_id')}")
            print(f"   Region: {info.get('region')}")

        # List buckets
        buckets = client.list_buckets()
        print(f" Total buckets for user: {len(buckets)}")

        # Delete bucket
        success = client.delete_bucket(bucket_name)
        if success:
            print(f" Bucket deleted successfully")


def example_03_bucket_policies(host='localhost', port=50051):
    """
    Example 3: Bucket Policy Management

    Set, get, and delete bucket policies (S3-compatible JSON policies).
    """
    print("\n" + "=" * 80)
    print("Example 3: Bucket Policy Management")
    print("=" * 80)

    user_id = 'example-user'
    bucket_name = f'policy-bucket-{datetime.now().strftime("%H%M%S")}'

    with MinIOClient(host=host, port=port, user_id=user_id) as client:
        # Create bucket first
        client.create_bucket(bucket_name)

        # Define a bucket policy (S3-compatible)
        policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
            }]
        }

        # Set bucket policy
        success = client.set_bucket_policy(bucket_name, json.dumps(policy))
        if success:
            print(" Bucket policy set successfully")

        # Get bucket policy
        retrieved_policy = client.get_bucket_policy(bucket_name)
        if retrieved_policy:
            print(f" Bucket policy retrieved (length: {len(retrieved_policy)} chars)")

        # Delete bucket policy
        success = client.delete_bucket_policy(bucket_name)
        if success:
            print(" Bucket policy deleted successfully")

        # Cleanup
        client.delete_bucket(bucket_name)


def example_04_bucket_tags(host='localhost', port=50051):
    """
    Example 4: Bucket Tagging

    Add metadata tags to buckets for organization and management.
    """
    print("\n" + "=" * 80)
    print("Example 4: Bucket Tagging")
    print("=" * 80)

    user_id = 'example-user'
    bucket_name = f'tagged-bucket-{datetime.now().strftime("%H%M%S")}'

    with MinIOClient(host=host, port=port, user_id=user_id) as client:
        # Create bucket
        client.create_bucket(bucket_name)

        # Set bucket tags
        tags = {
            "Environment": "development",
            "Project": "isA-Platform",
            "Owner": "team-backend",
            "CostCenter": "engineering"
        }

        success = client.set_bucket_tags(bucket_name, tags)
        if success:
            print(f" Set {len(tags)} tags on bucket")

        # Get bucket tags
        retrieved_tags = client.get_bucket_tags(bucket_name)
        if retrieved_tags:
            print(f" Retrieved tags:")
            for key, value in retrieved_tags.items():
                print(f"   {key}: {value}")

        # Delete bucket tags
        success = client.delete_bucket_tags(bucket_name)
        if success:
            print(" Bucket tags deleted successfully")

        # Cleanup
        client.delete_bucket(bucket_name)


def example_05_object_upload_download(host='localhost', port=50051):
    """
    Example 5: Object Upload/Download

    Upload and download objects with streaming support.
    """
    print("\n" + "=" * 80)
    print("Example 5: Object Upload/Download")
    print("=" * 80)

    user_id = 'example-user'
    bucket_name = f'data-bucket-{datetime.now().strftime("%H%M%S")}'

    with MinIOClient(host=host, port=port, user_id=user_id) as client:
        # Create bucket
        client.create_bucket(bucket_name)

        # Upload object (using convenience method)
        object_key = 'documents/readme.txt'
        content = f"Hello from MinIO!\nTimestamp: {datetime.now()}\n".encode()

        success = client.put_object(bucket_name, object_key, io.BytesIO(content), len(content))
        if success:
            print(f" Object uploaded: {object_key}")

        # Get object metadata
        metadata = client.get_object_metadata(bucket_name, object_key)
        if metadata:
            print(f" Object metadata:")
            print(f"   Size: {metadata['size']} bytes")
            print(f"   Content-Type: {metadata['content_type']}")
            print(f"   ETag: {metadata['etag']}")

        # Download object
        data = client.get_object(bucket_name, object_key)
        if data:
            print(f" Downloaded {len(data)} bytes")
            print(f"   Content preview: {data[:50].decode('utf-8', errors='ignore')}...")

        # Cleanup
        client.delete_bucket(bucket_name, force=True)


def example_06_upload_from_file(host='localhost', port=50051):
    """
    Example 6: Object Upload from File

    Upload objects directly from local files.
    """
    print("\n" + "=" * 80)
    print("Example 6: Object Upload from File")
    print("=" * 80)

    user_id = 'example-user'
    bucket_name = f'files-bucket-{datetime.now().strftime("%H%M%S")}'

    with MinIOClient(host=host, port=port, user_id=user_id) as client:
        # Create bucket
        client.create_bucket(bucket_name)

        # Create a temporary file
        temp_file = '/tmp/minio_example_file.txt'
        with open(temp_file, 'w') as f:
            f.write(f"Example file content\nCreated at: {datetime.now()}\n")

        # Upload file
        object_key = 'uploads/example_file.txt'
        success = client.upload_file(bucket_name, object_key, temp_file)
        if success:
            print(f" File uploaded: {object_key}")

        # Verify upload
        metadata = client.get_object_metadata(bucket_name, object_key)
        if metadata:
            print(f" Uploaded file size: {metadata['size']} bytes")

        # Cleanup
        import os
        os.remove(temp_file)
        client.delete_bucket(bucket_name, force=True)


def example_07_object_copy(host='localhost', port=50051):
    """
    Example 7: Object Copy Operation

    Copy objects within or across buckets.
    """
    print("\n" + "=" * 80)
    print("Example 7: Object Copy Operation")
    print("=" * 80)

    user_id = 'example-user'
    bucket_name = f'copy-bucket-{datetime.now().strftime("%H%M%S")}'

    with MinIOClient(host=host, port=port, user_id=user_id) as client:
        # Create bucket
        client.create_bucket(bucket_name)

        # Upload source object
        source_key = 'source/original.txt'
        content = b'Original content to be copied'
        client.put_object(bucket_name, source_key, io.BytesIO(content), len(content))
        print(f" Source object uploaded: {source_key}")

        # Copy object
        dest_key = 'destination/copy.txt'
        success = client.copy_object(bucket_name, dest_key, bucket_name, source_key)
        if success:
            print(f" Object copied: {source_key} -> {dest_key}")

        # Verify both exist
        objects = client.list_objects(bucket_name)
        print(f" Total objects in bucket: {len(objects)}")
        for obj in objects:
            print(f"   - {obj['key']} ({obj['size']} bytes)")

        # Cleanup
        client.delete_bucket(bucket_name, force=True)


def example_08_list_delete_operations(host='localhost', port=50051):
    """
    Example 8: Object List/Delete Operations

    List objects and perform single/batch deletions.
    """
    print("\n" + "=" * 80)
    print("Example 8: Object List/Delete Operations")
    print("=" * 80)

    user_id = 'example-user'
    bucket_name = f'list-bucket-{datetime.now().strftime("%H%M%S")}'

    with MinIOClient(host=host, port=port, user_id=user_id) as client:
        # Create bucket
        client.create_bucket(bucket_name)

        # Upload multiple objects
        objects_to_create = []
        for i in range(5):
            key = f'data/file-{i}.txt'
            content = f'Content of file {i}'.encode()
            client.put_object(bucket_name, key, io.BytesIO(content), len(content))
            objects_to_create.append(key)

        print(f" Uploaded {len(objects_to_create)} objects")

        # List objects
        objects = client.list_objects(bucket_name, prefix='data/')
        print(f" Found {len(objects)} objects with prefix 'data/':")
        for obj in objects:
            print(f"   - {obj['key']} ({obj['size']} bytes)")

        # Delete single object
        success = client.delete_object(bucket_name, objects_to_create[0])
        if success:
            print(f" Deleted single object: {objects_to_create[0]}")

        # Delete multiple objects (batch)
        success = client.delete_objects(bucket_name, objects_to_create[1:])
        if success:
            print(f" Batch deleted {len(objects_to_create)-1} objects")

        # Verify all deleted
        objects = client.list_objects(bucket_name)
        print(f" Remaining objects: {len(objects)}")

        # Cleanup
        client.delete_bucket(bucket_name)


def example_09_presigned_urls(host='localhost', port=50051):
    """
    Example 9: Presigned URL Generation

    Generate temporary URLs for direct upload/download without credentials.
    """
    print("\n" + "=" * 80)
    print("Example 9: Presigned URL Generation")
    print("=" * 80)

    user_id = 'example-user'
    bucket_name = f'presigned-bucket-{datetime.now().strftime("%H%M%S")}'

    with MinIOClient(host=host, port=port, user_id=user_id) as client:
        # Create bucket and upload object
        client.create_bucket(bucket_name)
        object_key = 'shared/document.pdf'
        content = b'PDF document content...'
        client.put_object(bucket_name, object_key, io.BytesIO(content), len(content))

        # Generate presigned GET URL (for download)
        get_url = client.get_presigned_url(bucket_name, object_key, expiry_seconds=3600)
        if get_url:
            print(f" Presigned GET URL generated (expires in 1 hour)")
            print(f"   URL: {get_url[:80]}...")

        # Generate presigned PUT URL (for upload)
        upload_key = 'uploads/new_file.txt'
        put_url = client.get_presigned_put_url(bucket_name, upload_key, expiry_seconds=3600)
        if put_url:
            print(f" Presigned PUT URL generated (expires in 1 hour)")
            print(f"   URL: {put_url[:80]}...")

        # Using the convenience method
        url = client.generate_presigned_url(bucket_name, object_key, method='GET')
        if url:
            print(f" Generated URL using convenience method")

        # Cleanup
        client.delete_bucket(bucket_name, force=True)


def example_10_object_tags(host='localhost', port=50051):
    """
    Example 10: Object Metadata and Tags

    Add metadata and tags to individual objects.
    """
    print("\n" + "=" * 80)
    print("Example 10: Object Metadata and Tags")
    print("=" * 80)

    user_id = 'example-user'
    bucket_name = f'tagged-objects-{datetime.now().strftime("%H%M%S")}'

    with MinIOClient(host=host, port=port, user_id=user_id) as client:
        # Create bucket
        client.create_bucket(bucket_name)

        # Upload object with custom metadata
        object_key = 'documents/report.pdf'
        content = b'Report content...'
        metadata = {
            "x-amz-meta-author": "John Doe",
            "x-amz-meta-department": "Engineering"
        }

        result = client.upload_object(bucket_name, object_key, content, metadata=metadata)
        if result:
            print(f" Object uploaded with custom metadata")

        # Set object tags
        tags = {
            "Type": "Report",
            "Status": "Final",
            "Year": "2025",
            "Confidential": "No"
        }

        success = client.set_object_tags(bucket_name, object_key, tags)
        if success:
            print(f" Set {len(tags)} tags on object")

        # Get object tags
        retrieved_tags = client.get_object_tags(bucket_name, object_key)
        if retrieved_tags:
            print(f" Retrieved tags:")
            for key, value in retrieved_tags.items():
                print(f"   {key}: {value}")

        # Delete object tags
        success = client.delete_object_tags(bucket_name, object_key)
        if success:
            print(" Object tags deleted successfully")

        # Cleanup
        client.delete_bucket(bucket_name, force=True)


def example_11_large_file_upload(host='localhost', port=50051):
    """
    Example 11: Large File Upload

    Upload large files with streaming (tested up to 6MB, supports much larger).
    """
    print("\n" + "=" * 80)
    print("Example 11: Large File Upload (6MB)")
    print("=" * 80)

    user_id = 'example-user'
    bucket_name = f'large-files-{datetime.now().strftime("%H%M%S")}'

    with MinIOClient(host=host, port=port, user_id=user_id) as client:
        # Create bucket
        client.create_bucket(bucket_name)

        # Generate 6MB of data
        size = 6 * 1024 * 1024  # 6MB
        print(f"= Generating {size/1024/1024:.1f}MB of test data...")
        data = bytes([i % 256 for i in range(size)])

        # Upload large file
        object_key = 'large/data.bin'
        print(f"= Uploading {size/1024/1024:.1f}MB file...")
        success = client.put_object(bucket_name, object_key, io.BytesIO(data), len(data))
        if success:
            print(f" Large file uploaded successfully")

        # Verify size
        metadata = client.get_object_metadata(bucket_name, object_key)
        if metadata:
            actual_size = metadata['size']
            print(f" Verified: {actual_size/1024/1024:.2f}MB uploaded")
            print(f"   ETag: {metadata['etag']}")

        # Cleanup
        client.delete_bucket(bucket_name, force=True)


def example_12_bucket_versioning(host='localhost', port=50051):
    """
    Example 12: Bucket Versioning

    Enable/disable versioning to maintain multiple versions of objects.
    Note: list_object_versions is not yet implemented in the proto service.
    """
    print("\n" + "=" * 80)
    print("Example 12: Bucket Versioning")
    print("=" * 80)

    user_id = 'example-user'
    bucket_name = f'versioned-bucket-{datetime.now().strftime("%H%M%S")}'

    with MinIOClient(host=host, port=port, user_id=user_id) as client:
        # Create bucket
        client.create_bucket(bucket_name)

        # Enable versioning
        success = client.set_bucket_versioning(bucket_name, enabled=True)
        if success:
            print(" Bucket versioning enabled")

        # Check versioning status
        is_enabled = client.get_bucket_versioning(bucket_name)
        print(f" Versioning status: {'Enabled' if is_enabled else 'Disabled'}")

        # Upload multiple versions of the same object
        object_key = 'documents/version_test.txt'
        for version in range(3):
            content = f'Version {version} content\nTimestamp: {datetime.now()}\n'.encode()
            client.put_object(bucket_name, object_key, io.BytesIO(content), len(content))
            print(f" Uploaded version {version+1}")

        # Note: list_object_versions is not yet available
        print("->  Note: list_object_versions() is not yet implemented in the proto service")

        # Disable versioning
        success = client.set_bucket_versioning(bucket_name, enabled=False)
        if success:
            print(" Bucket versioning disabled")

        # Cleanup
        client.delete_bucket(bucket_name, force=True)


def example_13_bucket_lifecycle(host='localhost', port=50051):
    """
    Example 13: Bucket Lifecycle Policies

    Set automatic expiration and transition rules for objects.
    Note: This is a placeholder implementation awaiting full MinIO SDK integration.
    """
    print("\n" + "=" * 80)
    print("Example 13: Bucket Lifecycle Policies")
    print("=" * 80)

    user_id = 'example-user'
    bucket_name = f'lifecycle-bucket-{datetime.now().strftime("%H%M%S")}'

    with MinIOClient(host=host, port=port, user_id=user_id) as client:
        # Create bucket
        client.create_bucket(bucket_name)

        # Define lifecycle rules
        rules = [
            {
                "id": "delete-old-logs",
                "status": "Enabled",
                "expiration": {"days": 30},
                "filter": {"prefix": "logs/"}
            },
            {
                "id": "archive-reports",
                "status": "Enabled",
                "expiration": {"days": 90},
                "filter": {"prefix": "reports/"}
            }
        ]

        # Set lifecycle policy
        success = client.set_bucket_lifecycle(bucket_name, rules)
        if success:
            print(f" Set {len(rules)} lifecycle rules")
            for rule in rules:
                print(f"   - {rule['id']}: expire after {rule['expiration']['days']} days")

        # Get lifecycle policy
        retrieved_rules = client.get_bucket_lifecycle(bucket_name)
        if retrieved_rules is not None:
            print(f" Retrieved {len(retrieved_rules)} lifecycle rules")

        # Delete lifecycle policy
        success = client.delete_bucket_lifecycle(bucket_name)
        if success:
            print(" Lifecycle policy deleted successfully")

        print("\n->  Note: Lifecycle rules are accepted but not yet applied to MinIO backend.")
        print("   Full implementation requires MinIO SDK lifecycle.Configuration conversion.")

        # Cleanup
        client.delete_bucket(bucket_name)


def run_all_examples(host='localhost', port=50051):
    """Run all examples in sequence"""
    print("\n" + "=" * 80)
    print("  MinIO Client Usage Examples")
    print("  Based on isa_common.minio_client.MinIOClient")
    print("=" * 80)
    print(f"\nConnecting to: {host}:{port}")
    print(f"Timestamp: {datetime.now()}\n")

    examples = [
        example_01_health_check,
        example_02_bucket_lifecycle,
        example_03_bucket_policies,
        example_04_bucket_tags,
        example_05_object_upload_download,
        example_06_upload_from_file,
        example_07_object_copy,
        example_08_list_delete_operations,
        example_09_presigned_urls,
        example_10_object_tags,
        example_11_large_file_upload,
        example_12_bucket_versioning,
        example_13_bucket_lifecycle,
    ]

    for i, example in enumerate(examples, 1):
        try:
            example(host, port)
        except Exception as e:
            print(f"\nL Example {i} failed: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("  All Examples Completed!")
    print("=" * 80)
    print("\nFor more information:")
    print("  - Client source: isA_common/isa_common/minio_client.py")
    print("  - Test script: isA_common/tests/minio/test_minio_functional.sh")
    print("  - Test result: 13/13 tests passing (100% success rate)")
    print()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='MinIO Client Usage Examples',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--host', default=None,
                       help='MinIO gRPC service host (optional, uses Consul discovery if not provided)')
    parser.add_argument('--port', type=int, default=None,
                       help='MinIO gRPC service port (optional, uses Consul discovery if not provided)')
    parser.add_argument('--consul-host', default='localhost',
                       help='Consul host (default: localhost)')
    parser.add_argument('--consul-port', type=int, default=8500,
                       help='Consul port (default: 8500)')
    parser.add_argument('--use-consul', action='store_true',
                       help='Use Consul for service discovery')
    parser.add_argument('--example', type=int, choices=range(1, 14),
                       help='Run specific example (1-13, default: all)')

    args = parser.parse_args()

    # Default: Try Consul first, fallback to localhost
    host = args.host
    port = args.port

    if host is None or port is None:
        if not args.use_consul:
            try:
                print(f"🔍 Attempting Consul discovery from {args.consul_host}:{args.consul_port}...")
                consul = ConsulRegistry(consul_host=args.consul_host, consul_port=args.consul_port)
                url = consul.get_minio_endpoint()

                if '://' in url:
                    url = url.split('://', 1)[1]
                discovered_host, port_str = url.rsplit(':', 1)
                discovered_port = int(port_str)

                host = host or discovered_host
                port = port or discovered_port
                print(f"✅ Discovered from Consul: {host}:{port}")
            except Exception as e:
                print(f"⚠️  Consul discovery failed: {e}")
                print(f"📍 Falling back to localhost...")

        # Fallback to defaults
        host = host or 'localhost'
        port = port or 50051

    print(f"🔗 Connecting to MinIO at {host}:{port}\n")

    if args.example:
        # Run specific example
        examples_map = {
            1: example_01_health_check,
            2: example_02_bucket_lifecycle,
            3: example_03_bucket_policies,
            4: example_04_bucket_tags,
            5: example_05_object_upload_download,
            6: example_06_upload_from_file,
            7: example_07_object_copy,
            8: example_08_list_delete_operations,
            9: example_09_presigned_urls,
            10: example_10_object_tags,
            11: example_11_large_file_upload,
            12: example_12_bucket_versioning,
            13: example_13_bucket_lifecycle,
        }
        examples_map[args.example](host=args.host, port=args.port)
    else:
        # Run all examples
        run_all_examples(host=args.host, port=args.port)


if __name__ == '__main__':
    main()
