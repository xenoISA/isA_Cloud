# gRPC Services

Unified gRPC interface to 9 backend infrastructure systems.

## Overview

Each gRPC service wraps a backend system with:

- Clean Architecture (handler → service → repository)
- Multi-tenancy support
- Audit logging
- Health checks
- Automatic Consul registration

## Services

| Service | Port | Backend | Purpose |
|---------|------|---------|---------|
| **postgres-grpc** | 50061 | PostgreSQL:5432 | SQL database operations |
| **redis-grpc** | 50055 | Redis:6379 | Cache and sessions |
| **neo4j-grpc** | 50063 | Neo4j:7687 | Graph database |
| **nats-grpc** | 50056 | NATS:4222 | Messaging and streaming |
| **mqtt-grpc** | 50053 | MQTT:1883 | IoT messaging |
| **minio-grpc** | 50051 | MinIO:9000 | Object storage |
| **qdrant-grpc** | 50062 | Qdrant:6333 | Vector search |
| **duckdb-grpc** | 50052 | DuckDB | Analytics |
| **loki-grpc** | 50054 | Loki:3100 | Log aggregation |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    gRPC Handler Layer                       │
│         Request validation • Response mapping               │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Service Layer                            │
│         Business logic • Multi-tenancy • Audit              │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Repository Layer                         │
│         Data access abstraction • Query building            │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Infrastructure Layer                     │
│         Database clients • Connection pooling               │
└─────────────────────────────────────────────────────────────┘
```

## PostgreSQL gRPC (50061)

### Execute Query

```protobuf
rpc ExecuteQuery(QueryRequest) returns (QueryResponse);

message QueryRequest {
  string query = 1;
  repeated Value params = 2;
  string org_id = 3;
}
```

### Python Client

```python
from isa_common import AsyncPostgresClient

client = AsyncPostgresClient(host="localhost", port=50061)

# Execute query
result = await client.execute(
    query="SELECT * FROM users WHERE org_id = $1",
    params=["org_123"]
)
```

## Redis gRPC (50055)

### Operations

```protobuf
rpc Get(GetRequest) returns (GetResponse);
rpc Set(SetRequest) returns (SetResponse);
rpc Delete(DeleteRequest) returns (DeleteResponse);
rpc Publish(PublishRequest) returns (PublishResponse);
```

### Python Client

```python
from isa_common import AsyncRedisClient

client = AsyncRedisClient(host="localhost", port=50055)

# Set with TTL
await client.set("session:user_123", session_data, ttl=3600)

# Get value
session = await client.get("session:user_123")

# Publish event
await client.publish("events:user", event_data)
```

### Key Isolation

Keys are automatically prefixed with org_id:
```
{org_id}:{key} → org_123:session:user_456
```

## Neo4j gRPC (50063)

### Operations

```protobuf
rpc ExecuteCypher(CypherRequest) returns (CypherResponse);
rpc CreateNode(CreateNodeRequest) returns (NodeResponse);
rpc CreateRelationship(RelationshipRequest) returns (RelationshipResponse);
```

### Python Client

```python
from isa_common import AsyncNeo4jClient

client = AsyncNeo4jClient(host="localhost", port=50063)

# Execute Cypher
result = await client.execute_cypher(
    query="MATCH (u:User)-[:FOLLOWS]->(f) WHERE u.id = $user_id RETURN f",
    params={"user_id": "user_123"}
)

# Create relationship
await client.create_relationship(
    from_id="user_123",
    to_id="user_456",
    relationship_type="FOLLOWS"
)
```

## NATS gRPC (50056)

### Operations

```protobuf
rpc Publish(PublishRequest) returns (PublishResponse);
rpc Subscribe(SubscribeRequest) returns (stream Message);
rpc CreateStream(StreamRequest) returns (StreamResponse);
```

### Python Client

```python
from isa_common import AsyncNatsClient

client = AsyncNatsClient(host="localhost", port=50056)

# Publish message
await client.publish(
    subject="user.created",
    data={"user_id": "user_123", "email": "user@example.com"}
)

# Subscribe to subject
async for msg in client.subscribe("user.*"):
    print(f"Received: {msg.data}")

# JetStream - Create stream
await client.create_stream(
    name="USERS",
    subjects=["user.>"]
)
```

## MinIO gRPC (50051)

### Operations

```protobuf
rpc PutObject(PutObjectRequest) returns (PutObjectResponse);
rpc GetObject(GetObjectRequest) returns (stream ObjectChunk);
rpc DeleteObject(DeleteObjectRequest) returns (DeleteObjectResponse);
rpc ListObjects(ListObjectsRequest) returns (ListObjectsResponse);
```

### Python Client

```python
from isa_common import AsyncMinioClient

client = AsyncMinioClient(host="localhost", port=50051)

# Upload file
await client.put_object(
    bucket="user-files",
    key="photos/vacation.jpg",
    data=file_bytes,
    content_type="image/jpeg"
)

# Download file
data = await client.get_object(
    bucket="user-files",
    key="photos/vacation.jpg"
)

# Generate presigned URL
url = await client.presigned_url(
    bucket="user-files",
    key="photos/vacation.jpg",
    expires=3600
)
```

## Qdrant gRPC (50062)

### Operations

```protobuf
rpc Upsert(UpsertRequest) returns (UpsertResponse);
rpc Search(SearchRequest) returns (SearchResponse);
rpc Delete(DeleteRequest) returns (DeleteResponse);
```

### Python Client

```python
from isa_common import AsyncQdrantClient

client = AsyncQdrantClient(host="localhost", port=50062)

# Upsert vectors
await client.upsert(
    collection="memories",
    points=[
        {"id": "mem_123", "vector": embedding, "payload": {"text": "..."}}
    ]
)

# Search similar
results = await client.search(
    collection="memories",
    query_vector=query_embedding,
    limit=10
)
```

## Health Checks

All services expose health endpoints:

```protobuf
rpc Health(HealthRequest) returns (HealthResponse);
```

```bash
grpcurl -plaintext localhost:50061 grpc.health.v1.Health/Check
```

## Building Services

```bash
# Build all
make build

# Build specific service
cd services/postgres-grpc
go build -o ../../bin/postgres-service ./cmd/server

# Run locally
./bin/postgres-service --config configs/development.yaml
```

## Next Steps

- [Gateway](./gateway) - APISIX routing
- [Discovery](./discovery) - Consul registration
- [SDK](./sdk) - Python client library
