# Qdrant Service - Logic Contract

> Business Rules and Edge Cases for Qdrant gRPC Service (Vector Database)

---

## Overview

This document defines the business rules for the Qdrant gRPC service, covering collection management, vector operations, and similarity search.

---

## Business Rules

### BR-001: Multi-Tenant Collection Isolation

**Description**: Collections are isolated by organization through naming prefix.

**Given**: A user creates/accesses a collection
**When**: Collection operation is performed
**Then**:
- Collection name prefixed with `{org_id}_`
- Cannot access collections from other organizations
- Audit log records all operations

**Examples**:

| Input Collection | Org ID | Actual Collection |
|------------------|--------|-------------------|
| `documents` | `org-001` | `org_001_documents` |
| `embeddings` | `org-002` | `org_002_embeddings` |

**Test Cases**:
- `TestCreateCollection_BR001_CollectionPrefixedWithOrgId`
- `TestListCollections_BR001_OnlyReturnsOrgCollections`
- `TestSearch_BR001_CannotSearchOtherOrgCollections`

---

### BR-002: Collection Configuration

**Description**: Collections must be created with vector dimension and distance metric.

**Given**: A new collection is requested
**When**: CreateCollection is called
**Then**:
- Vector dimension must be specified (e.g., 384, 768, 1536)
- Distance metric specified (Cosine, Euclidean, Dot)
- Optional: on-disk storage, HNSW parameters

**Supported Distance Metrics**:

| Metric | Use Case | Value Range |
|--------|----------|-------------|
| Cosine | Text embeddings | -1 to 1 |
| Euclidean | Image features | 0 to infinity |
| Dot | Normalized vectors | -infinity to infinity |

**Test Cases**:
- `TestCreateCollection_BR002_RequiresDimensionAndMetric`
- `TestCreateCollection_BR002_SupportsAllDistanceMetrics`

---

### BR-003: Vector Upsert with Payload

**Description**: Vectors can be stored with associated metadata (payload).

**Given**: Vectors are upserted
**When**: Upsert is called
**Then**:
- Vector stored with unique ID
- Payload (JSON) stored alongside vector
- Existing vectors with same ID are overwritten

**Payload Schema**:
```json
{
  "id": "doc-123",
  "vector": [0.1, 0.2, ...],
  "payload": {
    "title": "Document Title",
    "source": "web",
    "timestamp": "2025-01-01T00:00:00Z"
  }
}
```

**Test Cases**:
- `TestUpsert_BR003_StoresVectorWithPayload`
- `TestUpsert_BR003_OverwritesExistingVector`
- `TestUpsert_BR003_SupportsNestedPayload`

---

### BR-004: Similarity Search

**Description**: Find vectors most similar to a query vector.

**Given**: A collection with vectors
**When**: Search is called with query vector
**Then**:
- Returns top-k most similar vectors
- Results sorted by similarity score
- Includes vector ID, score, and payload

**Search Parameters**:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `top_k` | Number of results | 10 |
| `score_threshold` | Minimum similarity | None |
| `with_payload` | Include payload | true |
| `with_vectors` | Include vectors | false |

**Test Cases**:
- `TestSearch_BR004_ReturnsTopKResults`
- `TestSearch_BR004_ResultsSortedByScore`
- `TestSearch_BR004_RespectsScoreThreshold`

---

### BR-005: Payload Filtering

**Description**: Search can be filtered by payload fields.

**Given**: A search with filter conditions
**When**: Search is called
**Then**:
- Only vectors matching filter are considered
- Filter applied before similarity ranking
- Supports various filter operators

**Filter Operators**:

| Operator | Description | Example |
|----------|-------------|---------|
| `match` | Exact match | `{"source": "web"}` |
| `range` | Numeric range | `{"timestamp": {"gte": "2025-01-01"}}` |
| `must` | AND conditions | `[filter1, filter2]` |
| `should` | OR conditions | `[filter1, filter2]` |
| `must_not` | NOT condition | `{"status": "deleted"}` |

**Test Cases**:
- `TestSearch_BR005_FiltersbyPayloadMatch`
- `TestSearch_BR005_FiltersbyNumericRange`
- `TestSearch_BR005_CombinesMultipleFilters`

---

### BR-006: Batch Operations

**Description**: Support batch upsert and delete for efficiency.

**Given**: Multiple vectors to process
**When**: Batch operation is called
**Then**:
- All vectors processed atomically
- Returns count of affected vectors
- Partial failure returns error with details

**Test Cases**:
- `TestBatchUpsert_BR006_InsertsMultipleVectors`
- `TestBatchDelete_BR006_DeletesMultipleVectors`
- `TestBatchUpsert_BR006_PartialFailureReturnsError`

---

### BR-007: Point Retrieval by ID

**Description**: Retrieve specific vectors by their IDs.

**Given**: Vector IDs
**When**: Get is called
**Then**:
- Returns vectors with matching IDs
- Non-existent IDs omitted from results
- Includes payload and optionally vector data

**Test Cases**:
- `TestGet_BR007_ReturnsVectorById`
- `TestGet_BR007_OmitsNonExistentIds`

---

### BR-008: Audit Logging

**Description**: All operations logged for audit trail.

**Given**: Any operation is performed
**When**: Operation completes
**Then**:
- Audit log sent to Loki
- Includes: timestamp, user_id, org_id, operation, collection
- Does NOT include vector data (too large)

**Test Cases**:
- `TestUpsert_BR008_AuditLogRecorded`
- `TestSearch_BR008_AuditLogRecorded`

---

## Edge Cases

### EC-001: Invalid Vector Dimension

**Given**: Vector dimension doesn't match collection
**When**: Upsert is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestUpsert_EC001_WrongDimensionReturnsError`

---

### EC-002: Collection Does Not Exist

**Given**: Collection name not found
**When**: Any operation is called
**Then**: Returns NotFound error

**Test Cases**:
- `TestSearch_EC002_NonExistentCollectionReturnsNotFound`

---

### EC-003: Collection Already Exists

**Given**: Collection with same name exists
**When**: CreateCollection is called
**Then**: Returns AlreadyExists error

**Test Cases**:
- `TestCreateCollection_EC003_DuplicateReturnsAlreadyExists`

---

### EC-004: Empty Query Vector

**Given**: Empty or null query vector
**When**: Search is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestSearch_EC004_EmptyVectorReturnsError`

---

### EC-005: Invalid Filter Syntax

**Given**: Malformed filter JSON
**When**: Search is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestSearch_EC005_InvalidFilterReturnsError`

---

### EC-006: Top-K Too Large

**Given**: top_k exceeds maximum (e.g., 10000)
**When**: Search is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestSearch_EC006_TopKTooLargeReturnsError`

---

### EC-007: Qdrant Unavailable

**Given**: Qdrant server is down
**When**: Any operation is called
**Then**: Returns Unavailable error

**Test Cases**:
- `TestSearch_EC007_QdrantUnavailableReturnsError`

---

### EC-008: Vector ID Conflict in Batch

**Given**: Batch contains duplicate IDs
**When**: BatchUpsert is called
**Then**: Last vector with duplicate ID wins

**Test Cases**:
- `TestBatchUpsert_EC008_DuplicateIdLastWins`

---

## Error Handling Rules

### ER-001: Error Response Mapping

| Qdrant Error | gRPC Code | Message |
|--------------|-----------|---------|
| Collection not found | `NotFound` | "collection not found" |
| Collection exists | `AlreadyExists` | "collection already exists" |
| Dimension mismatch | `InvalidArgument` | "vector dimension mismatch" |
| Invalid filter | `InvalidArgument` | "invalid filter syntax" |
| Connection error | `Unavailable` | "qdrant unavailable" |
| Timeout | `DeadlineExceeded` | "operation timeout" |

---

## Performance Expectations

| Operation | Expected Latency (p99) | Notes |
|-----------|------------------------|-------|
| CreateCollection | < 100ms | |
| Upsert (single) | < 10ms | |
| Upsert (batch 100) | < 100ms | |
| Search (top-10) | < 50ms | Depends on collection size |
| Search with filter | < 100ms | |
| Delete (single) | < 10ms | |
| Get by ID | < 10ms | |

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
