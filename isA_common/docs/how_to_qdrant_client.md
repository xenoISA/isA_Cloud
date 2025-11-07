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
