# isA Cloud Platform - Domain Context

> Business Domain Documentation for Infrastructure gRPC Services

---

## Overview

isA Cloud provides a unified **gRPC service layer** that abstracts infrastructure components (databases, caches, message queues, storage) behind consistent, multi-tenant, audited APIs.

---

## Domain Taxonomy

```
isA Cloud Infrastructure Services
│
├── Data Storage Services
│   ├── PostgreSQL Service      # Relational database operations
│   │   ├── Query execution
│   │   ├── Transaction management
│   │   └── Schema operations
│   │
│   ├── Redis Service           # Key-value cache operations
│   │   ├── String operations
│   │   ├── Hash operations
│   │   ├── List/Set operations
│   │   └── Pub/Sub messaging
│   │
│   ├── DuckDB Service          # Analytics database
│   │   ├── OLAP queries
│   │   └── Data export
│   │
│   └── Neo4j Service           # Graph database
│       ├── Node operations
│       ├── Relationship queries
│       └── Graph traversal
│
├── Messaging Services
│   ├── NATS Service            # Event streaming
│   │   ├── Publish/Subscribe
│   │   ├── Request/Reply
│   │   ├── JetStream (persistence)
│   │   └── Key-Value store
│   │
│   └── MQTT Service            # IoT messaging
│       ├── Topic publish
│       ├── Topic subscribe
│       └── QoS management
│
├── Storage Services
│   ├── MinIO Service           # Object storage
│   │   ├── Bucket operations
│   │   ├── Object upload/download
│   │   └── Presigned URLs
│   │
│   └── Qdrant Service          # Vector database
│       ├── Collection management
│       ├── Vector upsert
│       └── Similarity search
│
└── Observability Services
    └── Loki Service            # Log aggregation
        ├── Log ingestion
        ├── Log queries
        └── Audit trails
```

---

## Core Domain Concepts

### 1. Multi-Tenancy

All services implement **organization-level isolation**:

```
┌─────────────────────────────────────────────────────┐
│                    Request                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │   user_id   │  │   org_id    │  │   payload   │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│              Key/Namespace Isolation                 │
│                                                     │
│   Isolated Key = {org_id}:{user_id}:{original_key} │
│                                                     │
│   Example:                                          │
│   org-001:user-123:session:token                   │
└─────────────────────────────────────────────────────┘
```

### 2. Authentication & Authorization

```
┌──────────────────┐     ┌──────────────────┐
│  gRPC Request    │────▶│  Auth Interceptor │
└──────────────────┘     └────────┬─────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
              ┌─────────┐  ┌───────────┐  ┌─────────┐
              │ Validate│  │  Check    │  │  Rate   │
              │  Token  │  │  Permissions│ │  Limit  │
              └─────────┘  └───────────┘  └─────────┘
```

### 3. Audit Logging

Every operation is logged to Loki:

| Field | Description |
|-------|-------------|
| `timestamp` | When the operation occurred |
| `user_id` | Who performed the operation |
| `org_id` | Which organization |
| `service` | Which service (redis, postgres, etc.) |
| `operation` | What operation (Set, Get, Query, etc.) |
| `status` | Success or failure |
| `details` | Operation-specific metadata |

---

## Business Scenarios

### Scenario 1: Application Cache

**Actor**: Application Service
**Goal**: Cache frequently accessed data to reduce database load

```
1. App calls Redis.Set(key="user:profile:123", value=json, ttl=3600)
2. Redis Service:
   - Validates user permissions
   - Isolates key: "org-001:app-svc:user:profile:123"
   - Stores in Redis with TTL
   - Logs audit event
3. Later, App calls Redis.Get(key="user:profile:123")
4. Redis Service returns cached value (or cache miss)
```

### Scenario 2: Event-Driven Communication

**Actor**: Microservice
**Goal**: Publish domain events for other services to consume

```
1. Order Service calls NATS.Publish(subject="orders.created", data=order_json)
2. NATS Service:
   - Validates publisher permissions
   - Publishes to JetStream
   - Ensures delivery guarantees
   - Logs audit event
3. Inventory Service has subscribed to "orders.created"
4. NATS Service delivers message to subscriber
```

### Scenario 3: File Upload

**Actor**: User via API Gateway
**Goal**: Upload a file to object storage

```
1. API Gateway requests presigned URL from MinIO Service
2. MinIO Service:
   - Validates user permissions
   - Generates presigned PUT URL (expires in 15 min)
   - Returns URL to client
3. Client uploads directly to MinIO using presigned URL
4. MinIO Service logs the upload event
```

### Scenario 4: Semantic Search

**Actor**: AI Application
**Goal**: Find similar documents using vector embeddings

```
1. App generates embedding vector for query
2. App calls Qdrant.Search(collection="docs", vector=[...], top_k=10)
3. Qdrant Service:
   - Validates permissions
   - Performs ANN search
   - Returns top 10 similar documents with scores
4. App presents results to user
```

---

## Service Interactions

```
┌─────────────────────────────────────────────────────────────────┐
│                        API Gateway (APISIX)                      │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
            ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
            │   Agent     │ │    MCP      │ │   Model     │
            │  Service    │ │  Service    │ │  Service    │
            └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
                   │               │               │
     ┌─────────────┴───────────────┴───────────────┴─────────────┐
     │                    gRPC Service Layer                      │
     ├─────────┬─────────┬─────────┬─────────┬─────────┬─────────┤
     │ Redis   │Postgres │  NATS   │  MinIO  │ Qdrant  │  Loki   │
     │ Service │ Service │ Service │ Service │ Service │ Service │
     └────┬────┴────┬────┴────┬────┴────┬────┴────┬────┴────┬────┘
          │         │         │         │         │         │
     ┌────▼────┐┌───▼───┐┌────▼────┐┌───▼───┐┌────▼────┐┌───▼───┐
     │  Redis  ││Postgres││  NATS   ││ MinIO ││ Qdrant  ││ Loki  │
     │(Backend)││(Backend)│(Backend)││(Backend)│(Backend)││(Backend)│
     └─────────┘└────────┘└─────────┘└────────┘└─────────┘└────────┘
```

---

## Glossary

| Term | Definition |
|------|------------|
| **gRPC** | High-performance RPC framework using Protocol Buffers |
| **Proto** | Protocol Buffer definition file (.proto) |
| **Multi-tenant** | Single deployment serving multiple isolated organizations |
| **JetStream** | NATS persistent streaming feature |
| **Presigned URL** | Time-limited URL for direct object storage access |
| **ANN** | Approximate Nearest Neighbor (vector search algorithm) |
| **Audit Log** | Immutable record of all operations for compliance |

---

## Related Documents

- [PRD](../prd/README.md) - Product Requirements
- [Design](../design/README.md) - Technical Architecture
- [CDD Guide](../cdd_guide.md) - Contract-Driven Development

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
