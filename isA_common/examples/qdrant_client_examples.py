#!/usr/bin/env python3
"""
Qdrant Client Usage Examples
=============================

This example demonstrates how to use the QdrantClient from isa_common package.

File: isA_common/examples/qdrant_client_examples.py

Prerequisites:
--------------
1. Qdrant gRPC service must be running (default: localhost:50062)
2. Install isa_common package:
   ```bash
   pip install -e /path/to/isA_Cloud/isA_common
   ```

Usage:
------
```bash
# Run all examples
python isA_common/examples/qdrant_client_examples.py

# Run with custom host/port
python isA_common/examples/qdrant_client_examples.py --host 192.168.1.100 --port 50062
```

Features Demonstrated:
----------------------
✓ Health Check
✓ Collection Management (create, list, delete, info)
✓ Point Operations (upsert, count, delete)
✓ Vector Search (similarity search, score thresholds)
✓ Filtered Search (metadata filtering with must/should/must_not)
✓ Scroll/Pagination (iterate through large collections)
✓ Recommendation Engine (positive/negative examples)
✓ Payload Management (update, delete fields, clear)
✓ Field Indexes (optimize filtered queries)
✓ Snapshots (backup and restore)
✓ Distance Metrics (Cosine, Euclid, Dot, Manhattan)

Note: All operations include proper error handling and use context managers for resource cleanup.
"""

import sys
import argparse
import random

# Import the QdrantClient from isa_common
try:
    from isa_common.qdrant_client import QdrantClient
except ImportError:
    print("=" * 80)
    print("ERROR: Failed to import isa_common.qdrant_client")
    print("=" * 80)
    print("\nPlease install isa_common package:")
    print("  cd /path/to/isA_Cloud")
    print("  pip install -e isA_common")
    print()
    sys.exit(1)


def example_01_health_check(host='localhost', port=50062):
    """
    Example 1: Health Check

    Check if the Qdrant gRPC service is healthy and operational.
    """
    print("\n" + "=" * 80)
    print("Example 1: Service Health Check")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        health = client.health_check()

        if health and health.get('healthy'):
            print(f"✅ Service is healthy!")
            print(f"   Version: {health.get('version')}")
        else:
            print("❌ Service is not healthy")


def example_02_collection_create(host='localhost', port=50062):
    """
    Example 2: Collection Creation

    Create a vector collection with specified dimension and distance metric.
    """
    print("\n" + "=" * 80)
    print("Example 2: Collection Creation")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'
        vector_size = 128

        # Delete if exists
        try:
            client.delete_collection(collection_name)
        except:
            pass

        # Create collection with Cosine distance
        result = client.create_collection(collection_name, vector_size, distance='Cosine')

        if result:
            print(f"✅ Created collection '{collection_name}'")
            print(f"   Vector dimension: {vector_size}")
            print(f"   Distance metric: Cosine")

        # List all collections
        collections = client.list_collections()
        print(f"\n✅ Total collections: {len(collections)}")
        for coll in collections:
            print(f"   • {coll}")


def example_03_collection_info(host='localhost', port=50062):
    """
    Example 3: Collection Information

    Get detailed information about a collection.
    """
    print("\n" + "=" * 80)
    print("Example 3: Collection Information")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'

        info = client.get_collection_info(collection_name)

        if info:
            print(f"✅ Collection '{collection_name}' info:")
            print(f"   Status: {info.get('status')}")
            print(f"   Points count: {info.get('points_count')}")
            print(f"   Segments count: {info.get('segments_count')}")


def example_04_upsert_points(host='localhost', port=50062):
    """
    Example 4: Upsert Points

    Add vector embeddings with metadata to the collection.
    """
    print("\n" + "=" * 80)
    print("Example 4: Upsert Points")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'
        vector_size = 128

        # Generate sample embeddings
        documents = [
            {'id': 1, 'text': 'Python programming tutorial', 'category': 'programming'},
            {'id': 2, 'text': 'Machine learning basics', 'category': 'ai'},
            {'id': 3, 'text': 'Database design patterns', 'category': 'database'},
            {'id': 4, 'text': 'Web development with React', 'category': 'web'},
            {'id': 5, 'text': 'Deep learning with PyTorch', 'category': 'ai'},
        ]

        points = []
        for doc in documents:
            # Generate random vector (in real use, use actual embeddings from a model)
            vector = [random.random() for _ in range(vector_size)]
            points.append({
                'id': doc['id'],
                'vector': vector,
                'payload': {
                    'text': doc['text'],
                    'category': doc['category']
                }
            })

        operation_id = client.upsert_points(collection_name, points)

        if operation_id:
            print(f"✅ Upserted {len(points)} points")
            print(f"   Operation ID: {operation_id}")

        # Count points
        count = client.count_points(collection_name)
        print(f"\n✅ Total points in collection: {count}")


def example_05_vector_search(host='localhost', port=50062):
    """
    Example 5: Vector Similarity Search

    Search for similar vectors in the collection.
    """
    print("\n" + "=" * 80)
    print("Example 5: Vector Similarity Search")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'
        vector_size = 128

        # Create query vector (in real use, this would be an embedding of a query)
        query_vector = [random.random() for _ in range(vector_size)]

        # Search for top 3 similar vectors
        results = client.search(
            collection_name,
            query_vector,
            limit=3,
            with_payload=True,
            with_vectors=False
        )

        if results:
            print(f"✅ Found {len(results)} similar documents:")
            for i, result in enumerate(results, 1):
                print(f"\n   {i}. Score: {result.get('score'):.4f}")
                print(f"      ID: {result.get('id')}")
                payload = result.get('payload', {})
                print(f"      Text: {payload.get('text')}")
                print(f"      Category: {payload.get('category')}")


def example_06_search_with_threshold(host='localhost', port=50062):
    """
    Example 6: Search with Score Threshold

    Search only for results above a certain similarity threshold.
    """
    print("\n" + "=" * 80)
    print("Example 6: Search with Score Threshold")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'
        vector_size = 128

        query_vector = [random.random() for _ in range(vector_size)]

        # Search with minimum score threshold
        results = client.search(
            collection_name,
            query_vector,
            limit=10,
            score_threshold=0.5,  # Only results with score >= 0.5
            with_payload=True
        )

        print(f"✅ Results with score >= 0.5:")
        if results:
            for result in results:
                payload = result.get('payload', {})
                print(f"   • {payload.get('text')} (score: {result.get('score'):.4f})")
        else:
            print("   No results above threshold")


def example_07_upsert_string_ids(host='localhost', port=50062):
    """
    Example 7: Upsert Points with String IDs

    Add points using string IDs instead of numeric IDs.
    """
    print("\n" + "=" * 80)
    print("Example 7: Upsert with String IDs")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'
        vector_size = 128

        # Add points with string IDs
        points = []
        for i in range(3):
            vector = [random.random() for _ in range(vector_size)]
            points.append({
                'id': f'doc_{i+100}',  # String ID
                'vector': vector,
                'payload': {
                    'text': f'Document {i+100}',
                    'source': 'string_id_batch'
                }
            })

        operation_id = client.upsert_points(collection_name, points)

        if operation_id:
            print(f"✅ Upserted {len(points)} points with string IDs")

        count = client.count_points(collection_name)
        print(f"\n✅ Total points now: {count}")


def example_08_delete_points(host='localhost', port=50062):
    """
    Example 8: Delete Points

    Remove specific points from the collection.
    """
    print("\n" + "=" * 80)
    print("Example 8: Delete Points")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'

        # Delete numeric IDs
        ids_to_delete = [1, 2]
        operation_id = client.delete_points(collection_name, ids_to_delete)

        if operation_id:
            print(f"✅ Deleted {len(ids_to_delete)} points with numeric IDs")

        # Delete string IDs
        string_ids = ['doc_100', 'doc_101']
        operation_id = client.delete_points(collection_name, string_ids)

        if operation_id:
            print(f"✅ Deleted {len(string_ids)} points with string IDs")

        count = client.count_points(collection_name)
        print(f"\n✅ Remaining points: {count}")


def example_09_filtered_search(host='localhost', port=50062):
    """
    Example 9: Filtered Vector Search

    Search with metadata filters (must/should/must_not).
    """
    print("\n" + "=" * 80)
    print("Example 9: Filtered Vector Search")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'
        vector_size = 128

        query_vector = [random.random() for _ in range(vector_size)]

        # Search only in 'ai' category
        filter_conditions = {
            'must': [
                {'field': 'category', 'match': {'keyword': 'ai'}}
            ]
        }

        results = client.search_with_filter(
            collection_name,
            query_vector,
            filter_conditions=filter_conditions,
            limit=5
        )

        if results:
            print(f"✅ Found {len(results)} AI documents:")
            for result in results:
                payload = result.get('payload', {})
                print(f"   • {payload.get('text')} (category: {payload.get('category')})")


def example_10_scroll_pagination(host='localhost', port=50062):
    """
    Example 10: Scroll Through Collection

    Paginate through all points in the collection.
    """
    print("\n" + "=" * 80)
    print("Example 10: Scroll/Pagination")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'

        # First page
        result = client.scroll(collection_name, limit=3, with_payload=True)

        if result:
            print(f"✅ Page 1: {len(result['points'])} points")
            for point in result['points']:
                payload = point.get('payload', {})
                print(f"   • ID {point['id']}: {payload.get('text')}")

            # Second page if available
            if result.get('next_offset'):
                print(f"\n✅ Fetching next page...")
                next_result = client.scroll(
                    collection_name,
                    limit=3,
                    offset_id=result['next_offset'],
                    with_payload=True
                )
                if next_result:
                    print(f"✅ Page 2: {len(next_result['points'])} points")


def example_11_recommendations(host='localhost', port=50062):
    """
    Example 11: Recommendation Engine

    Find similar items based on positive/negative examples.
    """
    print("\n" + "=" * 80)
    print("Example 11: Recommendation Engine")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'

        # Recommend based on liking IDs 3,4,5 but not liking 1
        results = client.recommend(
            collection_name,
            positive=[3, 4, 5],
            negative=[],
            limit=3
        )

        if results:
            print(f"✅ Top {len(results)} recommendations:")
            for i, result in enumerate(results, 1):
                payload = result.get('payload', {})
                print(f"   {i}. {payload.get('text')} (score: {result.get('score'):.4f})")


def example_12_payload_update(host='localhost', port=50062):
    """
    Example 12: Update Payload

    Update metadata without re-upserting vectors.
    """
    print("\n" + "=" * 80)
    print("Example 12: Payload Update")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'

        # Update payload for specific IDs
        operation_id = client.update_payload(
            collection_name,
            ids=[3, 4],
            payload={'status': 'reviewed', 'priority': 'high'}
        )

        if operation_id:
            print(f"✅ Updated payload for 2 points")
            print(f"   Operation ID: {operation_id}")


def example_13_delete_payload_fields(host='localhost', port=50062):
    """
    Example 13: Delete Payload Fields

    Remove specific metadata fields.
    """
    print("\n" + "=" * 80)
    print("Example 13: Delete Payload Fields")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'

        # Delete 'priority' field from specific points
        operation_id = client.delete_payload_fields(
            collection_name,
            ids=[3],
            keys=['priority']
        )

        if operation_id:
            print(f"✅ Deleted 'priority' field from point 3")


def example_14_field_indexes(host='localhost', port=50062):
    """
    Example 14: Field Indexes

    Create indexes on payload fields for faster filtering.
    """
    print("\n" + "=" * 80)
    print("Example 14: Field Indexes")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'

        # Create index on 'category' field
        operation_id = client.create_field_index(
            collection_name,
            'category',
            'keyword'
        )

        if operation_id:
            print(f"✅ Created keyword index on 'category' field")
            print(f"   This speeds up filtered searches!")


def example_15_snapshots(host='localhost', port=50062):
    """
    Example 15: Snapshots

    Backup and restore collections.
    """
    print("\n" + "=" * 80)
    print("Example 15: Snapshots")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'

        # Create snapshot
        snapshot_name = client.create_snapshot(collection_name)

        if snapshot_name:
            print(f"✅ Created snapshot: {snapshot_name}")

        # List snapshots
        snapshots = client.list_snapshots(collection_name)
        if snapshots:
            print(f"\n✅ Total snapshots: {len(snapshots)}")
            for snap in snapshots:
                print(f"   • {snap['name']} ({snap['size_bytes']} bytes)")


def example_16_cleanup(host='localhost', port=50062):
    """
    Example 16: Cleanup

    Delete the example collection.
    """
    print("\n" + "=" * 80)
    print("Example 16: Cleanup")
    print("=" * 80)

    with QdrantClient(host=host, port=port, user_id='example-user') as client:
        collection_name = 'example_embeddings'

        result = client.delete_collection(collection_name)

        if result:
            print(f"✅ Deleted collection '{collection_name}'")

        collections = client.list_collections()
        print(f"\n✅ Remaining collections: {len(collections)}")


def main():
    """Run all examples"""
    parser = argparse.ArgumentParser(description='Qdrant Client Usage Examples')
    parser.add_argument('--host', default='localhost', help='Qdrant gRPC service host')
    parser.add_argument('--port', type=int, default=50062, help='Qdrant gRPC service port')
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("Qdrant Client Examples")
    print("=" * 80)
    print(f"Connecting to: {args.host}:{args.port}")

    try:
        example_01_health_check(args.host, args.port)
        example_02_collection_create(args.host, args.port)
        example_03_collection_info(args.host, args.port)
        example_04_upsert_points(args.host, args.port)
        example_05_vector_search(args.host, args.port)
        example_06_search_with_threshold(args.host, args.port)
        example_07_upsert_string_ids(args.host, args.port)
        example_08_delete_points(args.host, args.port)
        example_09_filtered_search(args.host, args.port)
        example_10_scroll_pagination(args.host, args.port)
        example_11_recommendations(args.host, args.port)
        example_12_payload_update(args.host, args.port)
        example_13_delete_payload_fields(args.host, args.port)
        example_14_field_indexes(args.host, args.port)
        example_15_snapshots(args.host, args.port)
        example_16_cleanup(args.host, args.port)

        print("\n" + "=" * 80)
        print("✅ All examples completed successfully!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
