# SDK (isA_common)

Shared Python client library for infrastructure services.

## Overview

`isa-common` provides async clients for all infrastructure services:

- Database clients (PostgreSQL, Neo4j, DuckDB, SQLite)
- Cache clients (Redis, in-memory)
- Storage clients (MinIO, local filesystem)
- Messaging clients (NATS, MQTT)
- Vector clients (Qdrant, Chroma)
- Service discovery (Consul)

## Installation

```bash
pip install isa-common

# Or from source
cd isA_common
pip install -e .
```

## Requirements

- Python 3.8+
- asyncio support
- gRPC dependencies

## Async Clients

### PostgreSQL Client

```python
from isa_common import AsyncPostgresClient

client = AsyncPostgresClient(
    host="localhost",
    port=50061,  # gRPC port
    database="isa_db"
)

# Execute query
result = await client.execute(
    query="SELECT * FROM users WHERE org_id = $1",
    params=["org_123"]
)

# Execute with transaction
async with client.transaction() as tx:
    await tx.execute("INSERT INTO users (id, name) VALUES ($1, $2)", ["u1", "John"])
    await tx.execute("INSERT INTO profiles (user_id) VALUES ($1)", ["u1"])

# Close connection
await client.close()
```

### Redis Client

```python
from isa_common import AsyncRedisClient

client = AsyncRedisClient(host="localhost", port=50055)

# Basic operations
await client.set("key", "value", ttl=3600)
value = await client.get("key")
await client.delete("key")

# Hash operations
await client.hset("user:123", {"name": "John", "email": "john@example.com"})
user = await client.hgetall("user:123")

# Pub/Sub
await client.publish("events:user", {"action": "created", "user_id": "123"})

async for message in client.subscribe("events:*"):
    print(f"Received: {message}")
```

### Neo4j Client

```python
from isa_common import AsyncNeo4jClient

client = AsyncNeo4jClient(host="localhost", port=50063)

# Execute Cypher query
result = await client.execute_cypher(
    query="""
        MATCH (u:User)-[:FOLLOWS]->(f:User)
        WHERE u.id = $user_id
        RETURN f.name as name
    """,
    params={"user_id": "user_123"}
)

# Create node
await client.create_node(
    labels=["User"],
    properties={"id": "user_123", "name": "John"}
)

# Create relationship
await client.create_relationship(
    from_id="user_123",
    to_id="user_456",
    relationship_type="FOLLOWS",
    properties={"since": "2024-01-01"}
)
```

### NATS Client

```python
from isa_common import AsyncNatsClient

client = AsyncNatsClient(host="localhost", port=50056)

# Publish message
await client.publish(
    subject="user.created",
    data={"user_id": "123", "email": "user@example.com"}
)

# Subscribe to subject
async for msg in client.subscribe("user.*"):
    print(f"Subject: {msg.subject}, Data: {msg.data}")

# JetStream - Create stream
await client.create_stream(
    name="USERS",
    subjects=["user.>"],
    retention="limits",
    max_msgs=1000000
)

# JetStream - Publish with ack
ack = await client.jetstream_publish("user.created", data)
print(f"Sequence: {ack.sequence}")

# JetStream - Consumer
async for msg in client.jetstream_subscribe("USERS", "user-processor"):
    await process_message(msg)
    await msg.ack()
```

### MinIO Client

```python
from isa_common import AsyncMinioClient

client = AsyncMinioClient(host="localhost", port=50051)

# Upload file
await client.put_object(
    bucket="user-files",
    key="photos/vacation.jpg",
    data=file_bytes,
    content_type="image/jpeg",
    metadata={"user_id": "123"}
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
    expires=3600,
    method="GET"
)

# List objects
async for obj in client.list_objects(bucket="user-files", prefix="photos/"):
    print(f"{obj.key}: {obj.size} bytes")

# Delete object
await client.delete_object(bucket="user-files", key="photos/old.jpg")
```

### Qdrant Client

```python
from isa_common import AsyncQdrantClient

client = AsyncQdrantClient(host="localhost", port=50062)

# Create collection
await client.create_collection(
    name="memories",
    vector_size=1536,
    distance="Cosine"
)

# Upsert vectors
await client.upsert(
    collection="memories",
    points=[
        {
            "id": "mem_123",
            "vector": embedding,  # List[float]
            "payload": {"text": "User completed project", "importance": 0.8}
        }
    ]
)

# Search similar vectors
results = await client.search(
    collection="memories",
    query_vector=query_embedding,
    limit=10,
    filter={"importance": {"$gte": 0.5}}
)

for result in results:
    print(f"Score: {result.score}, Text: {result.payload['text']}")
```

### MQTT Client

```python
from isa_common import AsyncMqttClient

client = AsyncMqttClient(host="localhost", port=50053)

# Publish message
await client.publish(
    topic="devices/device_123/telemetry",
    payload={"temperature": 25.5, "humidity": 60},
    qos=1
)

# Subscribe to topic
async for msg in client.subscribe("devices/+/telemetry"):
    print(f"Topic: {msg.topic}, Payload: {msg.payload}")
```

### DuckDB Client

```python
from isa_common import AsyncDuckdbClient

client = AsyncDuckdbClient(host="localhost", port=50052)

# Execute analytics query
result = await client.execute(
    query="""
        SELECT
            date_trunc('day', created_at) as day,
            COUNT(*) as count
        FROM events
        WHERE org_id = $1
        GROUP BY 1
        ORDER BY 1
    """,
    params=["org_123"]
)
```

### Consul Client

```python
from isa_common import ConsulClient

consul = ConsulClient(host="localhost", port=8500)

# Register service
await consul.register_service(
    name="my_service",
    port=8080,
    tags=["api", "v1"],
    health_check={
        "http": "http://localhost:8080/health",
        "interval": "10s"
    }
)

# Discover services
services = await consul.get_service("auth_service")
for svc in services:
    print(f"Address: {svc.address}:{svc.port}")

# KV operations
await consul.kv_put("config/key", "value")
value = await consul.kv_get("config/key")
```

## Event System

### Event Publisher

```python
from isa_common.events import BaseEventPublisher, UserCreatedEvent

publisher = BaseEventPublisher(nats_client)

# Publish event
await publisher.publish(
    UserCreatedEvent(
        user_id="user_123",
        email="user@example.com",
        timestamp=datetime.utcnow()
    )
)
```

### Event Subscriber

```python
from isa_common.events import BaseEventSubscriber

subscriber = BaseEventSubscriber(nats_client)

@subscriber.on("user.created")
async def handle_user_created(event: UserCreatedEvent):
    print(f"User created: {event.user_id}")

# Start listening
await subscriber.start()
```

## Configuration

```python
from isa_common import AsyncClientConfig

config = AsyncClientConfig(
    host="localhost",
    port=50061,
    timeout=30,
    retry_attempts=3,
    retry_delay=1.0
)

client = AsyncPostgresClient(config=config)
```

## Error Handling

```python
from isa_common.exceptions import (
    ConnectionError,
    TimeoutError,
    NotFoundError
)

try:
    result = await client.get("nonexistent")
except NotFoundError:
    print("Key not found")
except ConnectionError:
    print("Failed to connect")
except TimeoutError:
    print("Request timed out")
```

## Next Steps

- [gRPC Services](./grpc-services) - Backend services
- [Discovery](./discovery) - Consul integration
- [Deployment](./deployment) - Production setup
