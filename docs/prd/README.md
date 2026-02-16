# isA Cloud Platform - Product Requirements Document

> User Stories and Acceptance Criteria for Infrastructure gRPC Services

---

## Overview

This document defines the product requirements for isA Cloud's infrastructure services layer, organized by service and epic.

---

## Epic 1: Redis Service (Cache & Key-Value Store)

### E1-US1: Key-Value Operations

**As a** backend developer
**I want** to store and retrieve key-value pairs via gRPC
**So that** I can cache data without managing Redis connections directly

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Given valid credentials, when Set is called, then key-value is stored | Done |
| AC-1.2 | Given valid key, when Get is called, then value is returned | Done |
| AC-1.3 | Given TTL > 0, when Set is called, then key expires after TTL seconds | Done |
| AC-1.4 | Given non-existent key, when Get is called, then NotFound error returned | Done |
| AC-1.5 | Given invalid user_id, when any operation is called, then PermissionDenied | Done |

### E1-US2: Multi-Tenant Isolation

**As a** platform operator
**I want** each organization's data isolated
**So that** tenants cannot access each other's cached data

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | Keys are prefixed with org_id:user_id automatically | Done |
| AC-2.2 | User A cannot read User B's keys (different org) | Done |
| AC-2.3 | Audit log records all access attempts | Done |

### E1-US3: Hash Operations

**As a** backend developer
**I want** to store structured data as Redis hashes
**So that** I can efficiently update individual fields

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-3.1 | HSet stores field-value pairs in a hash | Done |
| AC-3.2 | HGet retrieves a single field from hash | Done |
| AC-3.3 | HGetAll retrieves all fields from hash | Done |
| AC-3.4 | HDel removes fields from hash | Done |

---

## Epic 2: PostgreSQL Service (Relational Database)

### E2-US1: Query Execution

**As a** backend developer
**I want** to execute SQL queries via gRPC
**So that** I can access the database without connection management

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Execute SELECT queries and return rows as JSON | Done |
| AC-1.2 | Execute INSERT/UPDATE/DELETE and return affected rows | Done |
| AC-1.3 | Support parameterized queries to prevent SQL injection | Done |
| AC-1.4 | Return meaningful error messages for invalid SQL | Done |

### E2-US2: Transaction Support

**As a** backend developer
**I want** to execute multiple queries in a transaction
**So that** I can ensure data consistency

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | BeginTx starts a transaction and returns tx_id | Planned |
| AC-2.2 | ExecuteInTx runs query within transaction | Planned |
| AC-2.3 | Commit commits the transaction | Planned |
| AC-2.4 | Rollback aborts the transaction | Planned |
| AC-2.5 | Transactions timeout after configurable period | Planned |

---

## Epic 3: NATS Service (Event Streaming)

### E3-US1: Publish/Subscribe

**As a** microservice developer
**I want** to publish and subscribe to events
**So that** services can communicate asynchronously

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Publish sends message to subject | Done |
| AC-1.2 | Subscribe receives messages from subject | Done |
| AC-1.3 | Wildcards supported (orders.*, orders.>) | Done |
| AC-1.4 | Messages include metadata (timestamp, publisher) | Done |

### E3-US2: JetStream Persistence

**As a** microservice developer
**I want** messages persisted with delivery guarantees
**So that** no events are lost during service restarts

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | Create/manage streams with retention policies | Done |
| AC-2.2 | Durable consumers for reliable delivery | Done |
| AC-2.3 | Ack/Nak for message acknowledgment | Done |
| AC-2.4 | Replay from specific sequence number | Done |

### E3-US3: Key-Value Store

**As a** microservice developer
**I want** a distributed key-value store
**So that** services can share configuration and state

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-3.1 | Create/delete KV buckets | Done |
| AC-3.2 | Put/Get/Delete keys | Done |
| AC-3.3 | Watch for key changes | Done |
| AC-3.4 | TTL support for keys | Done |

---

## Epic 4: MinIO Service (Object Storage)

### E4-US1: Bucket Management

**As a** backend developer
**I want** to create and manage storage buckets
**So that** I can organize uploaded files

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Create bucket with specified name | Done |
| AC-1.2 | List all buckets for organization | Done |
| AC-1.3 | Delete empty bucket | Done |
| AC-1.4 | Bucket names scoped to organization | Done |

### E4-US2: Object Operations

**As a** backend developer
**I want** to upload and download files
**So that** I can store binary data in the platform

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | Upload object with metadata | Done |
| AC-2.2 | Download object by key | Done |
| AC-2.3 | List objects in bucket with pagination | Done |
| AC-2.4 | Delete object | Done |
| AC-2.5 | Generate presigned URLs for direct access | Done |

---

## Epic 5: Qdrant Service (Vector Database)

### E5-US1: Collection Management

**As an** AI developer
**I want** to create vector collections
**So that** I can store embeddings for similarity search

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Create collection with dimension and distance metric | Done |
| AC-1.2 | List collections | Done |
| AC-1.3 | Delete collection | Done |
| AC-1.4 | Collections scoped to organization | Done |

### E5-US2: Vector Operations

**As an** AI developer
**I want** to upsert and search vectors
**So that** I can build semantic search features

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | Upsert vectors with payload | Done |
| AC-2.2 | Search by vector similarity (top-k) | Done |
| AC-2.3 | Filter search by payload fields | Done |
| AC-2.4 | Delete vectors by ID or filter | Done |

---

## Epic 6: Loki Service (Logging)

### E6-US1: Log Ingestion

**As a** platform operator
**I want** services to send logs to centralized storage
**So that** I can monitor and debug the platform

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Push logs with labels and timestamp | Done |
| AC-1.2 | Batch log ingestion for efficiency | Done |
| AC-1.3 | Auto-add service metadata labels | Done |

### E6-US2: Log Queries

**As a** platform operator
**I want** to query logs using LogQL
**So that** I can investigate issues

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | Query logs by label selectors | Done |
| AC-2.2 | Filter by time range | Done |
| AC-2.3 | Support regex and line filters | Done |
| AC-2.4 | Return results with pagination | Done |

---

## Epic 7: Cross-Cutting Concerns

### E7-US1: Service Discovery

**As a** platform operator
**I want** services to register with Consul
**So that** clients can discover healthy instances

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-1.1 | Services register on startup | Done |
| AC-1.2 | Health checks configured | Done |
| AC-1.3 | Deregister on shutdown | Done |

### E7-US2: Observability

**As a** platform operator
**I want** metrics and traces from all services
**So that** I can monitor performance

#### Acceptance Criteria

| ID | Criteria | Status |
|----|----------|--------|
| AC-2.1 | gRPC metrics exported (latency, errors) | Partial |
| AC-2.2 | Distributed tracing with trace IDs | Planned |
| AC-2.3 | Dashboard in Grafana | Done |

---

## Priority Matrix

| Epic | Priority | Status | Notes |
|------|----------|--------|-------|
| E1: Redis | P0 | Done | Core caching |
| E2: PostgreSQL | P0 | Partial | Transactions planned |
| E3: NATS | P0 | Done | Event backbone |
| E4: MinIO | P1 | Done | File storage |
| E5: Qdrant | P1 | Done | AI features |
| E6: Loki | P1 | Done | Observability |
| E7: Cross-cutting | P0 | Partial | Tracing planned |

---

## Related Documents

- [Domain](../domain/README.md) - Business Context
- [Design](../design/README.md) - Technical Architecture
- [CDD Guide](../cdd_guide.md) - Contract-Driven Development

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
