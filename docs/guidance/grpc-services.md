# Infrastructure Clients (isa_common)

> **Note**: This project originally used Go gRPC wrapper services (ports 50051-50069). Those were removed in January 2026 in favor of direct Python async clients connecting to native ports. This document describes the current Python implementation.

Native async Python clients for 8 backend infrastructure systems.

## Overview

Each client extends `AsyncBaseClient` and provides:

- Direct connection to backend service on its native port
- Lazy connection management (connect on first use)
- Multi-tenancy support (automatic key/subject prefixing)
- Health checks
- Async context manager support

## Clients

| Client | Backend | Port | Driver | Key Features |
|--------|---------|------|--------|-------------|
| **AsyncPostgresClient** | PostgreSQL | 5432 | asyncpg | SQL queries, transactions, pooling |
| **AsyncRedisClient** | Redis | 6379 | redis-py async | K-V, hashes, pub/sub, locks |
| **AsyncNeo4jClient** | Neo4j | 7687 | neo4j | Cypher queries, graph ops |
| **AsyncNATSClient** | NATS | 4222 | nats-py | Pub/sub, JetStream, KV store |
| **AsyncMQTTClient** | Mosquitto | 1883 | aiomqtt | IoT messaging, QoS |
| **AsyncMinIOClient** | MinIO | 9000 | aioboto3 | Object storage, presigned URLs |
| **AsyncQdrantClient** | Qdrant | 6333 | qdrant-client | Vector search, filtering |
| **AsyncDuckDBClient** | DuckDB | embedded | duckdb | OLAP analytics, Parquet/CSV |

## PostgreSQL (5432)

```python
from isa_common import AsyncPostgresClient

async with AsyncPostgresClient(
    host="localhost", port=5432, database="mydb"
) as client:
    # Execute query
    rows = await client.query(
        "SELECT * FROM users WHERE org_id = $1", "org_123"
    )

    # Insert
    await client.insert("users", {"name": "Alice", "org_id": "org_123"})

    # Transaction
    await client.begin()
    await client.execute("UPDATE accounts SET balance = balance - $1", 100)
    await client.commit()
```

## Redis (6379)

```python
from isa_common import AsyncRedisClient

async with AsyncRedisClient(host="localhost", port=6379) as client:
    # Set with TTL
    await client.set("session:user_123", session_data, ttl=3600)

    # Get value
    session = await client.get("session:user_123")

    # Hash operations
    await client.hset("user:profile", "name", "Alice")
    name = await client.hget("user:profile", "name")

    # Pub/Sub
    await client.publish("events:user", event_data)

    # Distributed lock
    token = await client.acquire_lock("critical-section", timeout=10)
    await client.release_lock("critical-section", token)
```

### Key Isolation

Keys are automatically prefixed with `org_id:user_id`:
```
"session:token" → "org-001:user-123:session:token"
```

## Neo4j (7687)

```python
from isa_common import AsyncNeo4jClient

async with AsyncNeo4jClient(host="localhost", port=7687) as client:
    # Execute Cypher
    result = await client.query(
        "MATCH (u:User)-[:FOLLOWS]->(f) WHERE u.id = $user_id RETURN f",
        user_id="user_123"
    )

    # Create node
    await client.create_node("User", name="Alice", id="user_123")

    # Create relationship
    await client.create_relationship(
        "user_123", "FOLLOWS", "user_456"
    )
```

## NATS (4222)

```python
from isa_common import AsyncNATSClient

async with AsyncNATSClient(host="localhost", port=4222) as client:
    # Publish message
    await client.publish("user.created", {"user_id": "123"})

    # JetStream - Create stream
    await client.create_stream("USERS", subjects=["user.>"])

    # Pull messages from consumer
    messages = await client.pull_messages("USERS", "my-consumer", batch_size=10)

    # KV store
    await client.kv_put("config", "feature_flags", '{"dark_mode": true}')
    value = await client.kv_get("config", "feature_flags")
```

## MinIO (9000)

```python
from isa_common import AsyncMinIOClient

async with AsyncMinIOClient(host="localhost", port=9000) as client:
    # Upload file
    await client.upload_object("user-files", "photos/vacation.jpg", file_bytes)

    # Download file
    data = await client.download_object("user-files", "photos/vacation.jpg")

    # Generate presigned URL
    url = await client.generate_presigned_url(
        "user-files", "photos/vacation.jpg", expiry_seconds=3600
    )

    # List objects
    objects = await client.list_objects("user-files", prefix="photos/")
```

## Qdrant (6333)

```python
from isa_common import AsyncQdrantClient

async with AsyncQdrantClient(host="localhost", port=6333) as client:
    # Create collection
    await client.create_collection("memories", vector_size=768)

    # Upsert vectors
    await client.upsert_point(
        "memories", point_id="mem_123",
        vector=embedding, payload={"text": "..."}
    )

    # Search similar
    results = await client.search(
        "memories", query_vector=query_embedding, limit=10
    )
```

## Health Checks

All clients expose async health check:

```python
health = await client.health_check()
# Returns: {"connected": True, "host": "localhost", "port": 6379, ...}
```

## Service Discovery

```python
from isa_common import ConsulRegistry

registry = ConsulRegistry(service_name="my-service", service_port=8080)
await registry.register()

# Discover other services
endpoint = await registry.get_service_endpoint("auth-service")
```

## Installation

```bash
pip install isa-common
# or from source:
cd isA_common && pip install -e ".[dev]"
```

## Related Docs

- [Technical Design](../design/README.md) - Architecture overview
- [Domain Context](../domain/README.md) - Business scenarios
- [PRD](../prd/README.md) - Product requirements
