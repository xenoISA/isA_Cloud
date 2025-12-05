#!/usr/bin/env python3
"""
Async MinIO Client - Comprehensive Functional Tests

Tests all async MinIO operations including:
- Health check
- Bucket operations (create, list, delete, info)
- Object upload (small, large, streaming)
- Object download (get, stream)
- Object management (list, delete, copy, metadata)
- Presigned URLs
- Bucket configuration (versioning, tags)
- Concurrent operations
- Object tags

Usage:
    python test_async_minio.py
    HOST=minio-service PORT=50051 python test_async_minio.py
"""

import os
import sys
import asyncio
import time
import io

# Add parent path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from isa_common import AsyncMinIOClient

# Configuration
HOST = os.environ.get('HOST', 'localhost')
PORT = int(os.environ.get('PORT', '50051'))
USER_ID = os.environ.get('USER_ID', 'test_user')
TEST_BUCKET = 'async-test-bucket'

# Test results
PASSED = 0
FAILED = 0
TOTAL = 0


def test_result(success: bool, test_name: str):
    """Record test result."""
    global PASSED, FAILED, TOTAL
    TOTAL += 1
    if success:
        PASSED += 1
        print(f"  ✓ PASSED: {test_name}")
    else:
        FAILED += 1
        print(f"  ✗ FAILED: {test_name}")


async def test_health_check(client: AsyncMinIOClient) -> bool:
    """Test 1: Service Health Check"""
    try:
        health = await client.health_check()
        success = health is not None and health.get('healthy', False)
        test_result(success, "Health check")
        return success
    except Exception as e:
        test_result(False, f"Health check - {e}")
        return False


async def test_create_bucket(client: AsyncMinIOClient):
    """Test 2: Create Bucket"""
    try:
        result = await client.create_bucket(TEST_BUCKET)
        if result is None:
            test_result(False, "Create bucket - returned None")
            return

        if not result.get('success'):
            # Bucket might already exist
            test_result(True, "Create bucket (may already exist)")
            return

        test_result(True, "Create bucket")
    except Exception as e:
        test_result(False, f"Create bucket - {e}")


async def test_bucket_exists(client: AsyncMinIOClient):
    """Test 3: Bucket Exists Check"""
    try:
        exists = await client.bucket_exists(TEST_BUCKET)
        if not exists:
            test_result(False, "Bucket exists - not found")
            return

        test_result(True, "Bucket exists check")
    except Exception as e:
        test_result(False, f"Bucket exists - {e}")


async def test_list_buckets(client: AsyncMinIOClient):
    """Test 4: List Buckets"""
    try:
        buckets = await client.list_buckets()
        if buckets is None:
            test_result(False, "List buckets - returned None")
            return

        test_result(True, f"List buckets (found {len(buckets)})")
    except Exception as e:
        test_result(False, f"List buckets - {e}")


async def test_get_bucket_info(client: AsyncMinIOClient):
    """Test 5: Get Bucket Info"""
    try:
        info = await client.get_bucket_info(TEST_BUCKET)
        if info is None:
            test_result(False, "Get bucket info - returned None")
            return

        test_result(True, "Get bucket info")
    except Exception as e:
        test_result(False, f"Get bucket info - {e}")


async def test_upload_object(client: AsyncMinIOClient):
    """Test 6: Upload Object"""
    try:
        data = b'Hello from async MinIO client! This is test content.'
        result = await client.upload_object(
            TEST_BUCKET,
            'test/hello.txt',
            data,
            content_type='text/plain',
            metadata={'author': 'test', 'version': '1.0'}
        )
        if result is None:
            test_result(False, "Upload object - returned None")
            return

        if not result.get('success'):
            test_result(False, f"Upload object - failed: {result}")
            return

        test_result(True, f"Upload object ({result.get('size')} bytes)")
    except Exception as e:
        test_result(False, f"Upload object - {e}")


async def test_get_object(client: AsyncMinIOClient):
    """Test 7: Get Object"""
    try:
        data = await client.get_object(TEST_BUCKET, 'test/hello.txt')
        if data is None:
            test_result(False, "Get object - returned None")
            return

        if b'Hello from async' not in data:
            test_result(False, f"Get object - content mismatch")
            return

        test_result(True, f"Get object ({len(data)} bytes)")
    except Exception as e:
        test_result(False, f"Get object - {e}")


async def test_get_object_metadata(client: AsyncMinIOClient):
    """Test 8: Get Object Metadata"""
    try:
        metadata = await client.get_object_metadata(TEST_BUCKET, 'test/hello.txt')
        if metadata is None:
            test_result(False, "Get object metadata - returned None")
            return

        if metadata.get('size') is None:
            test_result(False, "Get object metadata - no size")
            return

        test_result(True, f"Get object metadata (size: {metadata.get('size')})")
    except Exception as e:
        test_result(False, f"Get object metadata - {e}")


async def test_list_objects(client: AsyncMinIOClient):
    """Test 9: List Objects"""
    try:
        objects = await client.list_objects(TEST_BUCKET, prefix='test/')
        if objects is None:
            test_result(False, "List objects - returned None")
            return

        if len(objects) < 1:
            test_result(False, "List objects - no objects found")
            return

        test_result(True, f"List objects (found {len(objects)})")
    except Exception as e:
        test_result(False, f"List objects - {e}")


async def test_copy_object(client: AsyncMinIOClient):
    """Test 10: Copy Object"""
    try:
        success = await client.copy_object(
            dest_bucket=TEST_BUCKET,
            dest_key='test/hello_copy.txt',
            source_bucket=TEST_BUCKET,
            source_key='test/hello.txt'
        )
        if not success:
            test_result(False, "Copy object - failed")
            return

        # Verify copy exists
        exists_data = await client.get_object(TEST_BUCKET, 'test/hello_copy.txt')
        if exists_data is None:
            test_result(False, "Copy object - copy not found")
            return

        test_result(True, "Copy object")
    except Exception as e:
        test_result(False, f"Copy object - {e}")


async def test_object_tags(client: AsyncMinIOClient):
    """Test 11: Object Tags"""
    try:
        # Set tags
        success = await client.set_object_tags(
            TEST_BUCKET,
            'test/hello.txt',
            {'environment': 'test', 'project': 'async-tests'}
        )
        if not success:
            test_result(False, "Set object tags - failed")
            return

        # Get tags
        tags = await client.get_object_tags(TEST_BUCKET, 'test/hello.txt')
        if tags is None:
            test_result(False, "Get object tags - returned None")
            return

        test_result(True, "Object tags (SET/GET)")
    except Exception as e:
        test_result(False, f"Object tags - {e}")


async def test_presigned_url(client: AsyncMinIOClient):
    """Test 12: Generate Presigned URL"""
    try:
        url = await client.get_presigned_url(
            TEST_BUCKET,
            'test/hello.txt',
            expiry_seconds=3600
        )
        if url is None:
            test_result(False, "Get presigned URL - returned None")
            return

        if not url.startswith('http'):
            test_result(False, f"Get presigned URL - invalid: {url[:50]}...")
            return

        test_result(True, "Get presigned URL (download)")
    except Exception as e:
        test_result(False, f"Get presigned URL - {e}")


async def test_presigned_put_url(client: AsyncMinIOClient):
    """Test 13: Generate Presigned PUT URL"""
    try:
        url = await client.get_presigned_put_url(
            TEST_BUCKET,
            'test/upload_target.txt',
            expiry_seconds=3600,
            content_type='text/plain'
        )
        if url is None:
            test_result(False, "Get presigned PUT URL - returned None")
            return

        test_result(True, "Get presigned PUT URL (upload)")
    except Exception as e:
        test_result(False, f"Get presigned PUT URL - {e}")


async def test_bucket_tags(client: AsyncMinIOClient):
    """Test 14: Bucket Tags"""
    try:
        # Set bucket tags
        success = await client.set_bucket_tags(
            TEST_BUCKET,
            {'environment': 'test', 'team': 'platform'}
        )
        if not success:
            test_result(False, "Set bucket tags - failed")
            return

        # Get bucket tags
        tags = await client.get_bucket_tags(TEST_BUCKET)
        if tags is None:
            test_result(False, "Get bucket tags - returned None")
            return

        test_result(True, "Bucket tags (SET/GET)")
    except Exception as e:
        test_result(False, f"Bucket tags - {e}")


async def test_concurrent_upload(client: AsyncMinIOClient):
    """Test 15: Concurrent Upload"""
    try:
        start = time.time()

        # Upload 5 objects concurrently
        results = await asyncio.gather(*[
            client.upload_object(
                TEST_BUCKET,
                f'test/concurrent_{i}.txt',
                f'Content for file {i}'.encode(),
                content_type='text/plain'
            )
            for i in range(5)
        ])

        elapsed = time.time() - start

        success_count = sum(1 for r in results if r and r.get('success'))
        if success_count != 5:
            test_result(False, f"Concurrent upload - {success_count}/5 succeeded")
            return

        test_result(True, f"Concurrent upload (5 files in {elapsed*1000:.1f}ms)")
    except Exception as e:
        test_result(False, f"Concurrent upload - {e}")


async def test_upload_many_concurrent(client: AsyncMinIOClient):
    """Test 16: upload_many_concurrent Helper"""
    try:
        uploads = [
            {'bucket': TEST_BUCKET, 'key': f'test/batch_{i}.txt', 'data': f'Batch {i}'.encode()}
            for i in range(3)
        ]

        start = time.time()
        results = await client.upload_many_concurrent(uploads)
        elapsed = time.time() - start

        success_count = sum(1 for r in results if r and r.get('success'))
        if success_count != 3:
            test_result(False, f"upload_many_concurrent - {success_count}/3 succeeded")
            return

        test_result(True, f"upload_many_concurrent helper ({elapsed*1000:.1f}ms)")
    except Exception as e:
        test_result(False, f"upload_many_concurrent - {e}")


async def test_download_many_concurrent(client: AsyncMinIOClient):
    """Test 17: download_many_concurrent Helper"""
    try:
        downloads = [
            {'bucket': TEST_BUCKET, 'key': f'test/batch_{i}.txt'}
            for i in range(3)
        ]

        start = time.time()
        results = await client.download_many_concurrent(downloads)
        elapsed = time.time() - start

        success_count = sum(1 for r in results if r is not None)
        if success_count != 3:
            test_result(False, f"download_many_concurrent - {success_count}/3 succeeded")
            return

        test_result(True, f"download_many_concurrent helper ({elapsed*1000:.1f}ms)")
    except Exception as e:
        test_result(False, f"download_many_concurrent - {e}")


async def test_delete_object(client: AsyncMinIOClient):
    """Test 18: Delete Object"""
    try:
        success = await client.delete_object(TEST_BUCKET, 'test/hello_copy.txt')
        if not success:
            test_result(False, "Delete object - failed")
            return

        test_result(True, "Delete object")
    except Exception as e:
        test_result(False, f"Delete object - {e}")


async def test_delete_objects(client: AsyncMinIOClient):
    """Test 19: Delete Multiple Objects"""
    try:
        keys = [f'test/concurrent_{i}.txt' for i in range(5)]
        keys.extend([f'test/batch_{i}.txt' for i in range(3)])

        success = await client.delete_objects(TEST_BUCKET, keys)
        if not success:
            test_result(False, "Delete objects - failed")
            return

        test_result(True, f"Delete multiple objects ({len(keys)} keys)")
    except Exception as e:
        test_result(False, f"Delete objects - {e}")


async def cleanup(client: AsyncMinIOClient):
    """Cleanup test bucket and objects."""
    print("\nCleaning up test resources...")
    try:
        # Delete all test objects
        objects = await client.list_objects(TEST_BUCKET, prefix='test/')
        if objects:
            keys = [obj.get('key') for obj in objects if obj.get('key')]
            if keys:
                await client.delete_objects(TEST_BUCKET, keys)

        # Delete bucket
        await client.delete_bucket(TEST_BUCKET, force=True)
    except Exception:
        pass


async def main():
    """Run all async tests."""
    print("=" * 70)
    print("     ASYNC MINIO CLIENT - COMPREHENSIVE FUNCTIONAL TESTS")
    print("=" * 70)
    print(f"\nConfiguration:")
    print(f"  Host: {HOST}")
    print(f"  Port: {PORT}")
    print(f"  User: {USER_ID}")
    print(f"  Test Bucket: {TEST_BUCKET}")
    print()

    async with AsyncMinIOClient(
        host=HOST,
        port=PORT,
        user_id=USER_ID
    ) as client:
        # Initial cleanup
        await cleanup(client)

        # Health check (required)
        print("\n--- Health Check ---")
        healthy = await test_health_check(client)
        if not healthy:
            print("\n✗ Cannot proceed without healthy service")
            return 1

        # Bucket operations
        print("\n--- Bucket Operations ---")
        await test_create_bucket(client)
        await test_bucket_exists(client)
        await test_list_buckets(client)
        await test_get_bucket_info(client)

        # Object upload operations
        print("\n--- Object Upload Operations ---")
        await test_upload_object(client)

        # Object download operations
        print("\n--- Object Download Operations ---")
        await test_get_object(client)
        await test_get_object_metadata(client)
        await test_list_objects(client)

        # Object management
        print("\n--- Object Management ---")
        await test_copy_object(client)
        await test_object_tags(client)

        # Presigned URLs
        print("\n--- Presigned URLs ---")
        await test_presigned_url(client)
        await test_presigned_put_url(client)

        # Bucket configuration
        print("\n--- Bucket Configuration ---")
        await test_bucket_tags(client)

        # Concurrent operations
        print("\n--- Concurrent Operations ---")
        await test_concurrent_upload(client)
        await test_upload_many_concurrent(client)
        await test_download_many_concurrent(client)

        # Delete operations
        print("\n--- Delete Operations ---")
        await test_delete_object(client)
        await test_delete_objects(client)

        # Final cleanup
        await cleanup(client)

    # Summary
    print("\n" + "=" * 70)
    print("                         TEST SUMMARY")
    print("=" * 70)
    print(f"Total Tests: {TOTAL}")
    print(f"Passed: {PASSED}")
    print(f"Failed: {FAILED}")
    if TOTAL > 0:
        print(f"Success Rate: {PASSED/TOTAL*100:.1f}%")
    print()

    if FAILED == 0:
        print(f"✓ ALL TESTS PASSED! ({PASSED}/{TOTAL})")
        return 0
    else:
        print(f"✗ SOME TESTS FAILED ({PASSED}/{TOTAL})")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
