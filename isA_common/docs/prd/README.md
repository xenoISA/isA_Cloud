# ISA Common - PRD Contract

**Product Requirements for Shared Infrastructure Clients**

This document defines the product requirements and user stories for the `isa_common` library.

---

## Overview

### Product Vision

Provide a **reliable, efficient, and consistent** way for ISA platform services to communicate with infrastructure services via gRPC, with automatic connection management and health checking.

### Key Stakeholders

| Role | Needs |
|------|-------|
| **MCP Service** | Vector search, storage, caching |
| **Model Service** | Database access, graph queries |
| **User Service** | User data persistence, sessions |
| **Cloud Service** | Infrastructure orchestration |

---

## Epics

### E1: Connection Management

Manage gRPC connections to infrastructure services reliably.

### E2: Health Monitoring

Monitor and maintain healthy connections automatically.

### E3: Error Recovery

Handle connection failures gracefully with automatic recovery.

### E4: Resource Efficiency

Optimize connection resources through pooling and sharing.

---

## User Stories

### E1: Connection Management

#### E1-US1: Connect to Infrastructure Service

**As a** Platform Service Developer
**I want** to connect to an infrastructure service (Qdrant, PostgreSQL, etc.)
**So that** I can perform data operations

**Acceptance Criteria**:
- [x] Given valid host/port, connection succeeds
- [x] Given invalid host, returns clear error
- [x] Connection uses global pool for efficiency
- [x] Connection is async (non-blocking)

**Priority**: P0 (Critical)

---

#### E1-US2: Lazy Connection Initialization

**As a** Platform Service Developer
**I want** connections to be established on first use
**So that** startup is fast and resources aren't wasted

**Acceptance Criteria**:
- [x] Client can be instantiated without connecting
- [x] First operation triggers connection
- [x] Subsequent operations reuse connection
- [x] Connection is thread/async-safe

**Priority**: P0 (Critical)

---

### E2: Health Monitoring

#### E2-US1: Channel Health Check Before Operations

**As a** Platform Service
**I want** the client to verify channel health before operations
**So that** I don't get "Channel is closed" errors

**Acceptance Criteria**:
- [ ] **Before each operation, channel state is checked**
- [ ] Healthy states (IDLE, READY, CONNECTING) proceed
- [ ] **Unhealthy states (SHUTDOWN, TRANSIENT_FAILURE) trigger reconnection**
- [ ] Health check is fast (no network call if healthy)

**Priority**: P0 (Critical) - **BUG FIX REQUIRED**

**Current Bug**:
```
_ensure_connected() only checks _connected flag, not actual channel state.
This causes "Channel is closed" errors when channel becomes SHUTDOWN.
```

---

#### E2-US2: Proactive Health Check Method

**As a** Platform Service Developer
**I want** to check channel health proactively
**So that** I can make informed decisions about reconnection

**Acceptance Criteria**:
- [x] `is_channel_healthy()` returns True for healthy channels
- [x] Returns False for unhealthy channels
- [x] Does NOT trigger reconnection (read-only check)
- [x] Works even when channel is None

**Priority**: P1 (High)

---

### E3: Error Recovery

#### E3-US1: Automatic Reconnection on Unhealthy Channel

**As a** Platform Service
**I want** the client to automatically reconnect when channel is unhealthy
**So that** operations can continue after transient failures

**Acceptance Criteria**:
- [ ] **SHUTDOWN channel triggers automatic reconnection**
- [ ] **TRANSIENT_FAILURE channel triggers automatic reconnection**
- [ ] Reconnection creates new healthy channel
- [ ] Reconnection increments counter for monitoring

**Priority**: P0 (Critical) - **BUG FIX REQUIRED**

---

#### E3-US2: Concurrent Reconnection Safety

**As a** Platform Service
**I want** concurrent operations to safely share reconnection
**So that** we don't create multiple connections simultaneously

**Acceptance Criteria**:
- [x] Multiple coroutines detecting unhealthy channel
- [x] Only ONE reconnection happens (via _connect_lock)
- [x] Other coroutines wait and use the new connection
- [x] No race conditions

**Priority**: P1 (High)

---

#### E3-US3: Manual Reconnection

**As a** Platform Service Developer
**I want** to manually trigger reconnection
**So that** I can recover from specific error conditions

**Acceptance Criteria**:
- [x] `reconnect()` creates new channel
- [x] Old channel is properly cleaned up
- [x] New stub is created
- [x] _connected flag is updated

**Priority**: P2 (Medium)

---

### E4: Resource Efficiency

#### E4-US1: Connection Pooling

**As a** Platform Service
**I want** connections to be pooled and shared
**So that** we minimize connection overhead

**Acceptance Criteria**:
- [x] Global channel pool is singleton
- [x] Same address returns same channel
- [x] Pool manages lifecycle
- [x] Proper cleanup on shutdown

**Priority**: P1 (High)

---

#### E4-US2: Graceful Shutdown

**As a** Platform Service
**I want** connections to be closed properly on shutdown
**So that** resources are released cleanly

**Acceptance Criteria**:
- [x] `close()` resets _connected flag
- [x] `close()` sets stub to None
- [x] Pool handles channel cleanup
- [x] No resource leaks

**Priority**: P1 (High)

---

## Non-Functional Requirements

### NFR-001: Performance

| Metric | Requirement |
|--------|-------------|
| Connection time | < 1 second |
| Health check time | < 1 ms (local state check) |
| Reconnection time | < 2 seconds |

### NFR-002: Reliability

| Metric | Requirement |
|--------|-------------|
| Connection success rate | > 99.9% (when service available) |
| Automatic recovery rate | > 95% (for transient failures) |
| No "Channel is closed" errors | 100% (with health checking) |

### NFR-003: Resource Usage

| Metric | Requirement |
|--------|-------------|
| Connections per service | 1 (via pool) |
| Memory per connection | < 1 MB |
| File descriptors | Minimal (pooled) |

---

## Release Criteria

### Version 0.2.1 (Bug Fix Release)

**Must Fix**:
- [ ] E2-US1: Channel health check before operations
- [ ] E3-US1: Automatic reconnection on unhealthy channel

**Test Coverage**:
- [ ] Golden tests document current behavior
- [ ] TDD tests define expected behavior
- [ ] All TDD tests pass after fix
- [ ] No regression in golden tests

**Deployment**:
- [ ] All tests pass locally
- [ ] Package published to PyPI
- [ ] Dependent services (MCP, Model, User) tested

---

## Tracking

### Bug Status

| ID | Description | Status | Priority |
|----|-------------|--------|----------|
| BUG-001 | _ensure_connected() doesn't check channel state | In Progress | P0 |
| BUG-002 | SHUTDOWN channel not triggering reconnect | In Progress | P0 |

### User Story Status

| ID | Story | Status |
|----|-------|--------|
| E1-US1 | Connect to infrastructure service | Done |
| E1-US2 | Lazy connection initialization | Done |
| E2-US1 | Channel health check before ops | **In Progress** |
| E2-US2 | Proactive health check method | Done |
| E3-US1 | Automatic reconnection | **In Progress** |
| E3-US2 | Concurrent reconnection safety | Done |
| E3-US3 | Manual reconnection | Done |
| E4-US1 | Connection pooling | Done |
| E4-US2 | Graceful shutdown | Done |

---

## Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| Domain | [docs/domain/README.md](../domain/README.md) | Business context |
| Design | [docs/design/README.md](../design/README.md) | Architecture |
| ENV | [docs/env/README.md](../env/README.md) | Configuration |
| Logic Contract | [tests/contracts/grpc_client/logic_contract.md](../../tests/contracts/grpc_client/logic_contract.md) | Business rules |

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
**Owner**: ISA Platform Team
