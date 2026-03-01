# isA Common

Shared async Python client library for the isA platform.

## Overview

`isa-common` provides async Python clients for interacting with isA Cloud infrastructure services. All clients use `async with` context managers and share a common base class (`AsyncBaseClient`).

### Infrastructure Clients (require running services)

| Client | Service | Default Port | Protocol |
|--------|---------|-------------|----------|
| `AsyncRedisClient` | Redis | 6379 | gRPC proxy |
| `AsyncPostgresClient` | PostgreSQL | 5432 | gRPC proxy |
| `AsyncNeo4jClient` | Neo4j | 7687 | gRPC proxy |
| `AsyncNATSClient` | NATS | 4222 | gRPC proxy |
| `AsyncMQTTClient` | MQTT | 1883 | gRPC proxy |
| `AsyncMinioClient` | MinIO | 9000 | gRPC proxy |
| `AsyncQdrantClient` | Qdrant | 6333 | gRPC proxy |
| `AsyncDuckDBClient` | DuckDB | embedded | native |

### Local-Mode Clients (no external services needed)

Drop-in alternatives for desktop/offline use. Same API surface, backed by local storage:

| Local Client | Replaces | Backed By |
|-------------|----------|-----------|
| `AsyncSQLiteClient` | `AsyncPostgresClient` | SQLite file |
| `AsyncLocalStorageClient` | `AsyncMinioClient` | Local filesystem |
| `AsyncChromaClient` | `AsyncQdrantClient` | ChromaDB (embedded) |
| `AsyncMemoryClient` | `AsyncRedisClient` | In-memory dict |

**When to use local clients:** Use local-mode clients when running on desktop/ICP without cloud infrastructure, for development/testing without Docker, or when you need offline-capable storage.

## Installation

```bash
pip install isa-common
```

## Quick Start

```python
from isa_common import AsyncRedisClient

async with AsyncRedisClient(host="localhost", port=6379, user_id="my-user") as client:
    health = await client.health_check()
    await client.set("key", "value")
    value = await client.get("key")
```

### Using Local-Mode Clients

```python
from isa_common import AsyncSQLiteClient, AsyncLocalStorageClient

# SQLite instead of PostgreSQL
async with AsyncSQLiteClient(database="app.db", user_id="my-user") as db:
    await db.query("SELECT * FROM users")

# Local filesystem instead of MinIO
async with AsyncLocalStorageClient(base_path="./storage", user_id="my-user") as storage:
    await storage.put_object("my-bucket", "file.txt", b"contents")
```

## Development

Run tests (requires services or use local clients):

```bash
# Run individual service tests
python tests/redis/test_async_redis.py
python tests/duck/test_async_duckdb.py

# Run all tests via Makefile
make test
```

## Contract Coverage

See [tests/contract_coverage.md](tests/contract_coverage.md) for the mapping between CDD contract IDs (BR/EC/ER) and test functions.

## License

Copyright © 2024 isA Platform







