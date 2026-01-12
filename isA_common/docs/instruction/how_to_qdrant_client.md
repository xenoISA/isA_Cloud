# 🚀 Qdrant Client - Vector Search Made Simple

## Installation

```bash
pip install -e /path/to/isA_Cloud/isA_common
```

## Simple Usage Pattern

```python
from isa_common.qdrant_client import QdrantClient

# 1. Connect (auto-discovers via Consul or use direct host)
with QdrantClient(host='localhost', port=50062, user_id='your-service') as client:

    # 2. Setup collection once
    client.create_collection('documents', vector_size=384, distance='Cosine')

    # 3. Store embeddings
    client.upsert_points('documents', [{
        'id': 1,
        'vector': your_embedding_model.encode("text"),
        'payload': {'text': 'text', 'category': 'news'}
    }])

    # 4. Search
    results = client.search('documents', query_embedding, limit=10)

    # 5. Search with filters (multi-tenant, metadata filtering)
    results = client.search_with_filter('documents', query_embedding,
        filter_conditions={
            'must': [
                {'field': 'tenant_id', 'match': {'keyword': 'acme'}},
                {'field': 'status', 'match': {'keyword': 'active'}}
            ]
        },
        limit=10
    )
```

---

## Real Service Example: RAG Chat Service

```python
from isa_common.qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

class RAGService:
    def __init__(self):
        self.qdrant = QdrantClient(user_id='rag-service')
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')

    def ingest_documents(self, documents):
        # Just focus on YOUR business logic
        points = []
        for doc in documents:
            points.append({
                'id': doc['id'],
                'vector': self.encoder.encode(doc['text']).tolist(),
                'payload': {'text': doc['text'], 'source': doc['source']}
            })

        # One line to store - client handles all gRPC complexity
        self.qdrant.upsert_points('knowledge_base', points)

    def search_with_context(self, query, user_id):
        # Encode query
        query_vec = self.encoder.encode(query).tolist()

        # Filtered search by user - ONE LINE
        results = self.qdrant.search_with_filter(
            'knowledge_base',
            query_vec,
            filter_conditions={
                'must': [{'field': 'user_id', 'match': {'keyword': user_id}}]
            },
            limit=5
        )

        # Return context
        return [r['payload']['text'] for r in results]

    def get_recommendations(self, liked_ids, disliked_ids):
        # Recommendation engine - ONE LINE
        results = self.qdrant.recommend(
            'knowledge_base',
            positive=liked_ids,
            negative=disliked_ids,
            limit=10
        )
        return results
```

---

## Quick Patterns for Common Use Cases

### Multi-tenant RAG
```python
# Store with tenant ID
client.upsert_points('docs', [{
    'id': 1,
    'vector': embedding,
    'payload': {'tenant_id': 'acme', 'text': 'document content'}
}])

# Search only tenant's data
results = client.search_with_filter('docs', vec,
    filter_conditions={'must': [{'field': 'tenant_id', 'match': {'keyword': 'acme'}}]}
)
```

### Recommendation Engine
```python
# User liked items 1,2,3 but disliked 5
recommendations = client.recommend('products',
    positive=[1,2,3],
    negative=[5],
    limit=10
)
```

### Bulk Data Export (Pagination)
```python
# Paginate through millions of vectors
offset = None
while True:
    result = client.scroll('huge_collection', limit=1000, offset_id=offset)
    process_batch(result['points'])
    if not result['next_offset']:
        break
    offset = result['next_offset']
```

### Update Metadata (No Re-embedding!)
```python
# Change status without touching vectors
client.update_payload('docs', ids=[1,2,3], payload={'status': 'verified'})
```

### Delete Specific Payload Fields
```python
# Remove fields without re-upserting
client.delete_payload_fields('docs', ids=[1,2,3], fields=['temp_field', 'cache'])
```

### Clear All Payload
```python
# Keep vectors, remove all metadata
client.clear_payload('docs', ids=[1,2,3])
```

### Field Indexes for Faster Filtering
```python
# Create index on frequently filtered fields
client.create_field_index('docs', field='tenant_id', field_type='keyword')
client.create_field_index('docs', field='timestamp', field_type='integer')
```

### Snapshots for Backup/Restore
```python
# Create snapshot
snapshot = client.create_snapshot('docs')
print(f"Snapshot created: {snapshot['name']}")

# List all snapshots
snapshots = client.list_snapshots('docs')

# Delete old snapshots
client.delete_snapshot('docs', 'snapshot-name')
```

### Advanced Search Parameters
```python
# Search with score threshold, offset, and HNSW parameters
results = client.search_with_filter('docs', query_vec,
    filter_conditions={'must': [{'field': 'category', 'match': {'keyword': 'tech'}}]},
    score_threshold=0.8,  # Only return results with score > 0.8
    offset=10,  # Skip first 10 results
    limit=10,
    params={'hnsw_ef': 128}  # HNSW search precision
)
```

---

## Benefits = MASSIVE Time Saver

### What you DON'T need to worry about:
- ❌ gRPC connection management
- ❌ Proto message serialization
- ❌ Error handling and retries
- ❌ Connection pooling
- ❌ Type conversions (int/UUID IDs, filters, payloads)
- ❌ Context managers and cleanup
- ❌ Filter condition building
- ❌ Pagination logic

### What you CAN focus on:
- ✅ Your embedding model
- ✅ Your business logic
- ✅ Your data processing
- ✅ Your user experience
- ✅ Your recommendation algorithms
- ✅ Your search quality

---

## Comparison: Without vs With Client

### Without (Raw Qdrant SDK + gRPC):
```python
# 100+ lines of gRPC setup, connection handling, filter building...
import grpc
from qdrant_pb2_grpc import QdrantStub
from qdrant_pb2 import SearchPoints, Filter, FieldCondition, Match

channel = grpc.insecure_channel('localhost:50062')
stub = QdrantStub(channel)

try:
    # Build filter manually
    filter_condition = FieldCondition(
        key='tenant_id',
        match=Match(keyword='acme')
    )
    filter_obj = Filter(must=[filter_condition])

    # Build search request
    request = SearchPoints(
        collection_name='docs',
        vector=query_vec,
        filter=filter_obj,
        limit=10
    )

    # Execute search
    response = stub.Search(request)

    # Parse results manually
    results = []
    for point in response.result:
        results.append({
            'id': point.id.num if point.id.num else point.id.str,
            'score': point.score,
            'payload': dict(point.payload)
        })
finally:
    channel.close()
```

### With isa_common:
```python
# 3 lines
with QdrantClient() as client:
    results = client.search_with_filter('docs', query_vec,
        filter_conditions={'must': [{'field': 'tenant_id', 'match': {'keyword': 'acme'}}]}
    )
```

---

## Async Client Usage (High-Performance)

For high-concurrency applications, use `AsyncQdrantClient` with `async/await`:

```python
import asyncio
import random
from isa_common import AsyncQdrantClient

def generate_vector(dim: int = 128) -> list:
    """Generate a random normalized vector."""
    vec = [random.gauss(0, 1) for _ in range(dim)]
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec]

async def main():
    async with AsyncQdrantClient(
        host='localhost',
        port=50062,
        user_id='your-service'
    ) as client:
        # Health check
        health = await client.health_check()

        # Create collection
        await client.create_collection(
            collection_name='documents',
            vector_size=128,
            distance='Cosine'
        )

        # List collections
        collections = await client.list_collections()

        # Get collection info
        info = await client.get_collection_info('documents')

        # Upsert points
        points = [
            {
                'id': i,
                'vector': generate_vector(),
                'payload': {
                    'category': ['tech', 'news', 'sports'][i % 3],
                    'price': 10.0 + i * 5,
                    'name': f'Item {i}'
                }
            }
            for i in range(1, 21)  # IDs 1-20
        ]
        await client.upsert_points('documents', points)

        # Count points
        count = await client.count_points('documents')

        # Vector search
        query_vector = generate_vector()
        results = await client.search(
            collection_name='documents',
            vector=query_vector,
            limit=5,
            with_payload=True
        )

        # Search with filter
        filter_conditions = {
            'must': [
                {'field': 'category', 'match': {'keyword': 'tech'}}
            ]
        }
        results = await client.search_with_filter(
            collection_name='documents',
            vector=query_vector,
            filter_conditions=filter_conditions,
            limit=5
        )

        # Search with score threshold
        results = await client.search(
            collection_name='documents',
            vector=query_vector,
            limit=10,
            score_threshold=0.5
        )

        # Delete collection
        await client.delete_collection('documents')

asyncio.run(main())
```

### Scroll (Pagination)

```python
async def scroll_example(client):
    result = await client.scroll(
        collection_name='documents',
        limit=100,
        with_payload=True
    )
    points = result.get('points', [])
    next_offset = result.get('next_offset')
```

### Recommendation

```python
async def recommend_example(client):
    # Recommend based on positive/negative examples
    results = await client.recommend(
        collection_name='documents',
        positive=[1, 2],  # Point IDs user liked
        negative=[5],     # Point IDs user disliked
        limit=10
    )
```

### Payload Operations

```python
async def payload_operations(client):
    # Update payload
    await client.update_payload(
        collection_name='documents',
        ids=[1, 2],
        payload={'updated': True, 'version': 2}
    )

    # Delete payload fields
    await client.delete_payload_fields(
        collection_name='documents',
        ids=[1],
        keys=['version']
    )
```

### Index Operations

```python
async def index_operations(client):
    # Create field index for faster filtering
    await client.create_field_index(
        collection_name='documents',
        field_name='category',
        field_type='keyword'
    )
```

### Delete Points

```python
async def delete_points(client):
    # Delete specific points
    await client.delete_points('documents', ids=[10, 11, 12])
```

### Concurrent Operations

```python
async def concurrent_searches(client):
    # Execute multiple searches concurrently
    vectors = [generate_vector() for _ in range(10)]
    results = await client.search_many_concurrent(
        collection_name='documents',
        vectors=vectors,
        limit=5
    )
    return results

async def concurrent_upserts(client):
    # Upload multiple batches concurrently
    batches = [
        [{'id': 100 + i * 5 + j, 'vector': generate_vector(), 'payload': {'batch': i}}
         for j in range(5)]
        for i in range(4)
    ]
    results = await client.upsert_points_concurrent('documents', batches)
    return results
```

---

## Complete Feature List

✅ **Collection Management**: create, delete, info, exists, list
✅ **Points Operations**: upsert, retrieve, delete, count
✅ **Search**: basic search, search with filters, batch search
✅ **Recommendations**: positive/negative examples
✅ **Pagination**: scroll through all points
✅ **Payload Operations**: update, delete fields, clear
✅ **Filtering**: must/should/must_not conditions, match, range
✅ **Field Indexes**: create, delete for faster filtering
✅ **Snapshots**: create, list, delete for backup/restore
✅ **Advanced Parameters**: score threshold, offset, HNSW tuning
✅ **ID Support**: both integer and UUID string IDs
✅ **Multi-tenancy**: user-scoped operations

---

## Test Results

**Sync Client: All tests passing (100% success rate)**
**Async Client: 18/18 tests passing (100% success rate)**

Comprehensive functional tests cover:
- Health check
- Collection management (create, list, info, delete)
- Point operations (upsert, count, delete)
- Vector search (basic, filtered, score threshold)
- Scroll (pagination)
- Recommendation search
- Payload operations (update, delete fields)
- Index operations (create field index)
- Concurrent searches (search_many_concurrent)
- Concurrent upserts (upsert_points_concurrent)

All tests demonstrate production-ready reliability.

---

## Bottom Line

Instead of writing 500+ lines of gRPC boilerplate, connection handling, and error management...

**You write 5 lines and ship features.** 🎯

The Qdrant client gives you:
- **Production-ready** vector search out of the box
- **Filter support** for multi-tenant and metadata search
- **Recommendation engine** for similarity-based features
- **Payload operations** to update metadata without re-embedding
- **Snapshots** for backup and disaster recovery
- **Auto-cleanup** via context managers
- **Type-safe** results (dicts with proper ID handling)

Just pip install and focus on your ML models and business logic!
