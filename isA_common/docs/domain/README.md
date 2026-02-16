# ISA Common - Domain Contract

**Business Context for Shared Infrastructure Clients**

This document defines the business domain for the `isa_common` library - the shared infrastructure client layer for the ISA platform.

---

## What is ISA Common?

ISA Common is a **shared Python library** providing async gRPC clients for infrastructure services used across all ISA platform services (MCP, Model, User, Cloud).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ISA PLATFORM ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   isA_MCP   │  │  isA_Model  │  │  isA_User   │  │  isA_Cloud  │        │
│  │   Service   │  │   Service   │  │   Service   │  │   Service   │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                │               │
│         └────────────────┴────────────────┴────────────────┘               │
│                                   │                                         │
│                                   ▼                                         │
│                        ┌──────────────────┐                                 │
│                        │    isa_common    │ ◄── Shared Infrastructure       │
│                        │ (gRPC Clients)   │      Client Library             │
│                        └────────┬─────────┘                                 │
│                                 │                                           │
│         ┌───────────────────────┼───────────────────────┐                   │
│         │           │           │           │           │                   │
│         ▼           ▼           ▼           ▼           ▼                   │
│    ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐             │
│    │ Qdrant  │ │Postgres │ │  Redis  │ │  MinIO  │ │  Neo4j  │             │
│    │ gRPC    │ │  gRPC   │ │  gRPC   │ │  gRPC   │ │  gRPC   │             │
│    └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘             │
│                                                                             │
│    + DuckDB, Loki, NATS, MQTT, Consul                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Domain Taxonomy

### Service Categories

```
Infrastructure Services
├── Storage Services
│   ├── PostgreSQL (Relational data, user management)
│   ├── MinIO (Object storage, files, images)
│   └── DuckDB (Analytics, OLAP queries)
│
├── Search & Vector Services
│   ├── Qdrant (Vector search, embeddings, RAG)
│   └── Elasticsearch (Full-text search) [Future]
│
├── Graph Services
│   └── Neo4j (Knowledge graphs, relationships)
│
├── Cache & Session Services
│   └── Redis (Caching, sessions, rate limiting)
│
├── Messaging Services
│   ├── NATS (Event streaming, pub/sub)
│   └── MQTT (IoT device communication)
│
└── Observability Services
    ├── Loki (Log aggregation)
    └── Consul (Service discovery)
```

### Client Architecture

```
gRPC Client Hierarchy
├── AsyncBaseGRPCClient (Abstract base)
│   ├── Connection management
│   ├── Channel health checking
│   ├── Reconnection logic
│   └── Pool integration
│
├── AsyncGlobalChannelPool (Singleton)
│   ├── Shared channel management
│   ├── Connection pooling
│   └── Resource optimization
│
└── Service-Specific Clients
    ├── AsyncQdrantClient (Vector operations)
    ├── AsyncPostgresClient (SQL operations)
    ├── AsyncRedisClient (Cache operations)
    ├── AsyncMinioClient (Object operations)
    ├── AsyncNeo4jClient (Graph operations)
    ├── AsyncDuckDBClient (Analytics operations)
    ├── AsyncLokiClient (Logging operations)
    ├── AsyncNatsClient (Messaging operations)
    └── AsyncMqttClient (IoT operations)
```

---

## Business Scenarios

### Scenario 1: Vector Search for RAG

**Actor**: MCP Service (handling user query)

**Flow**:
1. User submits a search query via MCP
2. MCP's VectorRepository needs to search Qdrant
3. AsyncQdrantClient connects to Qdrant gRPC service
4. Channel health is verified before operation
5. Search results returned with embeddings

**Critical Requirements**:
- Channel must be healthy (IDLE, READY, CONNECTING)
- Automatic reconnection on SHUTDOWN/TRANSIENT_FAILURE
- Connection pooling for efficiency

### Scenario 2: User Data Persistence

**Actor**: User Service (saving user profile)

**Flow**:
1. User updates their profile
2. User Service's Repository needs to save to PostgreSQL
3. AsyncPostgresClient executes the update
4. Transaction commits successfully

**Critical Requirements**:
- Atomic transactions
- Connection retry on failure
- Proper error propagation

### Scenario 3: File Upload

**Actor**: MCP Service (handling file upload)

**Flow**:
1. User uploads a file via MCP
2. MCP's StorageRepository needs to store in MinIO
3. AsyncMinioClient uploads object to bucket
4. Returns object URL

**Critical Requirements**:
- Streaming for large files
- Retry on network failure
- Proper cleanup on failure

### Scenario 4: Knowledge Graph Query

**Actor**: Model Service (context retrieval)

**Flow**:
1. Model needs context from knowledge graph
2. Graph Repository queries Neo4j
3. AsyncNeo4jClient executes Cypher query
4. Returns related entities

**Critical Requirements**:
- Complex query support
- Relationship traversal
- Connection pooling

---

## Key Domain Concepts

### Connection Lifecycle

```
Connection States (gRPC ChannelConnectivity)
├── IDLE          → Not actively connecting, ready to connect
├── CONNECTING    → Actively trying to establish connection
├── READY         → Connection established and healthy
├── TRANSIENT_FAILURE → Connection failed, will retry
└── SHUTDOWN      → Connection permanently closed

Healthy States: IDLE, READY, CONNECTING
Unhealthy States: SHUTDOWN, TRANSIENT_FAILURE
```

### Channel Pool Pattern

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ASYNC GLOBAL CHANNEL POOL                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     Singleton Instance                                │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │   │
│  │  │ qdrant:50062    │  │ postgres:50061  │  │ redis:50055     │      │   │
│  │  │ ┌─────────────┐ │  │ ┌─────────────┐ │  │ ┌─────────────┐ │      │   │
│  │  │ │  Channel 1  │ │  │ │  Channel 1  │ │  │ │  Channel 1  │ │      │   │
│  │  │ └─────────────┘ │  │ └─────────────┘ │  │ └─────────────┘ │      │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Benefits:                                                                  │
│  - Shared connections across all clients                                    │
│  - Reduced connection overhead                                              │
│  - Centralized health management                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Bounded Contexts

| Context | Description | Key Entities |
|---------|-------------|--------------|
| **Connection Management** | Managing gRPC channel lifecycle | Channel, Pool, Health State |
| **Service Communication** | Protocol buffers & service calls | Request, Response, Stub |
| **Error Handling** | Connection failures & retries | ConnectionError, RetryPolicy |
| **Configuration** | Host/port/timeout settings | ServiceConfig, PoolConfig |

---

## Glossary

| Term | Definition |
|------|------------|
| **Channel** | gRPC connection to a service endpoint |
| **Stub** | Generated client interface for calling service methods |
| **Pool** | Collection of reusable channels |
| **Health Check** | Verification of channel connectivity state |
| **Reconnection** | Process of establishing new connection after failure |
| **Protobuf** | Protocol Buffers - serialization format for gRPC |

---

## Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| PRD | [docs/prd/README.md](../prd/README.md) | Requirements |
| Design | [docs/design/README.md](../design/README.md) | Architecture |
| ENV | [docs/env/README.md](../env/README.md) | Configuration |
| System Contract | [tests/TDD_CONTRACT.md](../../tests/TDD_CONTRACT.md) | Test methodology |

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
**Owner**: ISA Platform Team
