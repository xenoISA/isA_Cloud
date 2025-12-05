#!/usr/bin/env python3
"""
Async Qdrant Client - Comprehensive Functional Tests

Tests all async Qdrant operations including:
- Health check
- Collection management
- Point operations (upsert, delete, count)
- Vector search
- Filtered search
- Recommendation search
- Payload operations
- Index management
- Concurrent operations
"""

import asyncio
import os
import sys
import time
import uuid
import random

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from isa_common import AsyncQdrantClient

# Configuration
HOST = os.environ.get('HOST', 'localhost')
PORT = int(os.environ.get('PORT', '50062'))
USER_ID = os.environ.get('USER_ID', 'test-user')

# Test results
PASSED = 0
FAILED = 0

# Vector dimension for tests
VECTOR_DIM = 128


def generate_vector(dim: int = VECTOR_DIM) -> list:
    """Generate a random normalized vector."""
    vec = [random.gauss(0, 1) for _ in range(dim)]
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec]


def test_result(success: bool, test_name: str):
    """Record test result."""
    global PASSED, FAILED
    if success:
        PASSED += 1
        print(f"  \u2713 PASSED: {test_name}")
    else:
        FAILED += 1
        print(f"  \u2717 FAILED: {test_name}")


async def test_health_check(client: AsyncQdrantClient) -> bool:
    """Test 1: Service Health Check"""
    try:
        health = await client.health_check()
        success = health is not None and health.get('healthy', False)
        test_result(success, f"Health check (version: {health.get('version', 'unknown')})")
        return success
    except Exception as e:
        test_result(False, f"Health check - {e}")
        return False


async def test_create_collection(client: AsyncQdrantClient, collection_name: str):
    """Test 2: Create Collection"""
    try:
        result = await client.create_collection(
            collection_name=collection_name,
            vector_size=VECTOR_DIM,
            distance='Cosine'
        )
        test_result(result is True, f"Create collection '{collection_name}'")
    except Exception as e:
        test_result(False, f"Create collection - {e}")


async def test_list_collections(client: AsyncQdrantClient):
    """Test 3: List Collections"""
    try:
        collections = await client.list_collections()
        success = isinstance(collections, list)
        test_result(success, f"List collections ({len(collections)} found)")
    except Exception as e:
        test_result(False, f"List collections - {e}")


async def test_get_collection_info(client: AsyncQdrantClient, collection_name: str):
    """Test 4: Get Collection Info"""
    try:
        info = await client.get_collection_info(collection_name)
        success = info is not None
        test_result(success, f"Get collection info (status: {info.get('status', 'unknown') if info else 'N/A'})")
    except Exception as e:
        test_result(False, f"Get collection info - {e}")


async def test_upsert_points(client: AsyncQdrantClient, collection_name: str):
    """Test 5: Upsert Points"""
    try:
        # Note: IDs start from 1 because the Go server has a bug where ID 0
        # is treated as empty string (if id.GetNum() > 0 check fails for 0)
        points = [
            {
                'id': i,
                'vector': generate_vector(),
                'payload': {
                    'category': ['electronics', 'books', 'clothing'][i % 3],
                    'price': 10.0 + i * 5,
                    'name': f'Product {i}',
                    'in_stock': i % 2 == 0
                }
            }
            for i in range(1, 21)  # IDs 1-20 instead of 0-19
        ]

        result = await client.upsert_points(collection_name, points)
        success = result is not None
        test_result(success, f"Upsert {len(points)} points")
    except Exception as e:
        test_result(False, f"Upsert points - {e}")


async def test_count_points(client: AsyncQdrantClient, collection_name: str):
    """Test 6: Count Points"""
    try:
        count = await client.count_points(collection_name)
        success = count is not None and count >= 0
        test_result(success, f"Count points ({count} points)")
    except Exception as e:
        test_result(False, f"Count points - {e}")


async def test_search(client: AsyncQdrantClient, collection_name: str):
    """Test 7: Vector Search"""
    try:
        query_vector = generate_vector()
        results = await client.search(
            collection_name=collection_name,
            vector=query_vector,
            limit=5,
            with_payload=True
        )
        success = results is not None and len(results) > 0
        test_result(success, f"Vector search ({len(results) if results else 0} results)")
    except Exception as e:
        test_result(False, f"Search - {e}")


async def test_search_with_filter(client: AsyncQdrantClient, collection_name: str):
    """Test 8: Search with Filter"""
    try:
        query_vector = generate_vector()
        filter_conditions = {
            'must': [
                {'field': 'category', 'match': {'keyword': 'electronics'}}
            ]
        }
        results = await client.search_with_filter(
            collection_name=collection_name,
            vector=query_vector,
            filter_conditions=filter_conditions,
            limit=5
        )
        success = results is not None
        test_result(success, f"Filtered search ({len(results) if results else 0} results)")
    except Exception as e:
        test_result(False, f"Search with filter - {e}")


async def test_search_with_score_threshold(client: AsyncQdrantClient, collection_name: str):
    """Test 9: Search with Score Threshold"""
    try:
        query_vector = generate_vector()
        results = await client.search(
            collection_name=collection_name,
            vector=query_vector,
            limit=10,
            score_threshold=0.5
        )
        success = results is not None
        test_result(success, f"Search with threshold ({len(results) if results else 0} results)")
    except Exception as e:
        test_result(False, f"Search with threshold - {e}")


async def test_scroll(client: AsyncQdrantClient, collection_name: str):
    """Test 10: Scroll Points"""
    try:
        result = await client.scroll(
            collection_name=collection_name,
            limit=10,
            with_payload=True
        )
        success = result is not None and 'points' in result
        test_result(success, f"Scroll ({len(result.get('points', [])) if result else 0} points)")
    except Exception as e:
        test_result(False, f"Scroll - {e}")


async def test_recommend(client: AsyncQdrantClient, collection_name: str):
    """Test 11: Recommendation Search"""
    try:
        results = await client.recommend(
            collection_name=collection_name,
            positive=[1, 2],  # Point IDs to use as positive examples (not 0 due to server bug)
            negative=[3],     # Point IDs to use as negative examples
            limit=5
        )
        success = results is not None
        test_result(success, f"Recommendation ({len(results) if results else 0} results)")
    except Exception as e:
        test_result(False, f"Recommend - {e}")


async def test_update_payload(client: AsyncQdrantClient, collection_name: str):
    """Test 12: Update Payload"""
    try:
        result = await client.update_payload(
            collection_name=collection_name,
            ids=[1, 2],  # Not using 0 due to server bug
            payload={'updated': True, 'update_time': time.time()}
        )
        success = result is not None
        test_result(success, "Update payload")
    except Exception as e:
        test_result(False, f"Update payload - {e}")


async def test_delete_payload_fields(client: AsyncQdrantClient, collection_name: str):
    """Test 13: Delete Payload Fields"""
    try:
        result = await client.delete_payload_fields(
            collection_name=collection_name,
            ids=[1],  # Not using 0 due to server bug
            keys=['updated']
        )
        success = result is not None
        test_result(success, "Delete payload fields")
    except Exception as e:
        test_result(False, f"Delete payload fields - {e}")


async def test_create_field_index(client: AsyncQdrantClient, collection_name: str):
    """Test 14: Create Field Index"""
    try:
        result = await client.create_field_index(
            collection_name=collection_name,
            field_name='category',
            field_type='keyword'
        )
        success = result is not None
        test_result(success, "Create field index")
    except Exception as e:
        test_result(False, f"Create field index - {e}")


async def test_delete_points(client: AsyncQdrantClient, collection_name: str):
    """Test 15: Delete Points"""
    try:
        result = await client.delete_points(collection_name, ids=[18, 19])
        success = result is not None
        test_result(success, "Delete points")
    except Exception as e:
        test_result(False, f"Delete points - {e}")


async def test_concurrent_searches(client: AsyncQdrantClient, collection_name: str):
    """Test 16: Concurrent Searches"""
    try:
        vectors = [generate_vector() for _ in range(10)]

        start = time.time()
        results = await client.search_many_concurrent(
            collection_name=collection_name,
            vectors=vectors,
            limit=5
        )
        elapsed = (time.time() - start) * 1000

        success_count = sum(1 for r in results if r is not None)
        success = success_count == len(vectors)
        test_result(success, f"Concurrent searches ({success_count}/{len(vectors)} in {elapsed:.1f}ms)")
    except Exception as e:
        test_result(False, f"Concurrent searches - {e}")


async def test_concurrent_upserts(client: AsyncQdrantClient, collection_name: str):
    """Test 17: Concurrent Upserts"""
    try:
        batches = [
            [{'id': 100 + i * 5 + j, 'vector': generate_vector(), 'payload': {'batch': i}}
             for j in range(5)]
            for i in range(4)
        ]

        start = time.time()
        results = await client.upsert_points_concurrent(collection_name, batches)
        elapsed = (time.time() - start) * 1000

        success_count = sum(1 for r in results if r is not None)
        success = success_count == len(batches)
        test_result(success, f"Concurrent upserts ({success_count}/{len(batches)} batches in {elapsed:.1f}ms)")
    except Exception as e:
        test_result(False, f"Concurrent upserts - {e}")


async def test_delete_collection(client: AsyncQdrantClient, collection_name: str):
    """Test 18: Delete Collection"""
    try:
        result = await client.delete_collection(collection_name)
        test_result(result is True, f"Delete collection '{collection_name}'")
    except Exception as e:
        test_result(False, f"Delete collection - {e}")


async def run_tests():
    """Run all tests."""
    print("=" * 70)
    print("     ASYNC QDRANT CLIENT - COMPREHENSIVE FUNCTIONAL TESTS")
    print("=" * 70)
    print()
    print(f"Configuration:")
    print(f"  Host: {HOST}")
    print(f"  Port: {PORT}")
    print(f"  User: {USER_ID}")
    print(f"  Vector Dimension: {VECTOR_DIM}")
    print()

    # Test identifiers
    test_id = uuid.uuid4().hex[:8]
    collection_name = f"async_test_collection_{test_id}"

    async with AsyncQdrantClient(
        host=HOST,
        port=PORT,
        user_id=USER_ID
    ) as client:
        # Health check first
        print("--- Health Check ---")
        health_ok = await test_health_check(client)

        if not health_ok:
            print("\nHealth check failed - skipping remaining tests")
            print("Make sure the Qdrant gRPC service is running and accessible")
            return

        # Collection Management
        print("\n--- Collection Management ---")
        await test_create_collection(client, collection_name)
        await test_list_collections(client)
        await test_get_collection_info(client, collection_name)

        # Point Operations
        print("\n--- Point Operations ---")
        await test_upsert_points(client, collection_name)
        await test_count_points(client, collection_name)

        # Search Operations
        print("\n--- Search Operations ---")
        await test_search(client, collection_name)
        await test_search_with_filter(client, collection_name)
        await test_search_with_score_threshold(client, collection_name)
        await test_scroll(client, collection_name)
        await test_recommend(client, collection_name)

        # Payload Operations
        print("\n--- Payload Operations ---")
        await test_update_payload(client, collection_name)
        await test_delete_payload_fields(client, collection_name)

        # Index Operations
        print("\n--- Index Operations ---")
        await test_create_field_index(client, collection_name)

        # Delete Points
        print("\n--- Delete Points ---")
        await test_delete_points(client, collection_name)

        # Concurrent Operations
        print("\n--- Concurrent Operations ---")
        await test_concurrent_searches(client, collection_name)
        await test_concurrent_upserts(client, collection_name)

        # Cleanup
        print("\n--- Cleanup ---")
        await test_delete_collection(client, collection_name)

    # Summary
    print()
    print("=" * 70)
    print("                         TEST SUMMARY")
    print("=" * 70)
    print(f"Total Tests: {PASSED + FAILED}")
    print(f"Passed: {PASSED}")
    print(f"Failed: {FAILED}")
    print(f"Success Rate: {PASSED/(PASSED+FAILED)*100:.1f}%")
    print()

    if FAILED == 0:
        print("\u2713 ALL TESTS PASSED! ({}/{})".format(PASSED, PASSED + FAILED))
    else:
        print("\u2717 SOME TESTS FAILED ({}/{})".format(PASSED, PASSED + FAILED))
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(run_tests())
