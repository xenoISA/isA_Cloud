# Redis Service - Logic Contract

> Business Rules and Edge Cases for Redis gRPC Service

---

## Overview

This document defines the business rules, state transitions, and edge cases for the Redis gRPC service. Each rule maps to specific test cases.

---

## Business Rules

### BR-001: Multi-Tenant Key Isolation

**Description**: All keys must be isolated by organization and user to prevent cross-tenant data access.

**Given**: A user sets a key
**When**: The key is stored in Redis
**Then**:
- Key is prefixed with `{org_id}:{user_id}:{original_key}`
- Other tenants cannot access the key
- Audit log is recorded with original and isolated key

**Examples**:

| Input Key | User ID | Org ID | Isolated Key |
|-----------|---------|--------|--------------|
| `session:token` | `user-123` | `org-001` | `org-001:user-123:session:token` |
| `cache:profile` | `user-456` | `org-002` | `org-002:user-456:cache:profile` |

**Test Cases**:
- `TestSet_BR001_KeyIsPrefixedWithOrgAndUser`
- `TestGet_BR001_CannotAccessOtherOrgKeys`
- `TestSet_BR001_AuditLogRecordsIsolatedKey`

---

### BR-002: TTL Expiration

**Description**: Keys with TTL > 0 must automatically expire after the specified duration.

**Given**: A key is set with TTL > 0
**When**: TTL seconds have passed
**Then**:
- Key is automatically deleted by Redis
- Get returns NotFound error
- No cleanup required by service

**State Diagram**:

```
┌─────────────┐     Set(ttl=60)    ┌─────────────┐
│   No Key    │ ─────────────────▶ │   Exists    │
└─────────────┘                    └──────┬──────┘
       ▲                                  │
       │                                  │ 60 seconds
       │         Auto-expire              ▼
       └────────────────────────── ┌─────────────┐
                                   │   Expired   │
                                   └─────────────┘
```

**Test Cases**:
- `TestSet_BR002_KeyExpiresAfterTTL`
- `TestSet_BR002_TTLZeroMeansNoExpiry`
- `TestGet_BR002_ExpiredKeyReturnsNotFound`

---

### BR-003: User Authentication

**Description**: All operations must validate user credentials before execution.

**Given**: A request with user_id
**When**: Any operation is called
**Then**:
- User is validated against auth service
- Invalid user returns PermissionDenied
- Valid user proceeds with operation

**Test Cases**:
- `TestSet_BR003_InvalidUserReturnsPermissionDenied`
- `TestGet_BR003_InvalidUserReturnsPermissionDenied`
- `TestSet_BR003_ValidUserSucceeds`

---

### BR-004: Audit Logging

**Description**: All operations must be logged to Loki for audit trail.

**Given**: Any operation is performed
**When**: Operation completes (success or failure)
**Then**:
- Audit log entry sent to Loki
- Log includes: timestamp, user_id, org_id, operation, key, status
- Log does NOT include sensitive values

**Audit Log Schema**:

```json
{
  "timestamp": "2025-12-11T10:30:00Z",
  "service": "redis-grpc",
  "user_id": "user-123",
  "org_id": "org-001",
  "operation": "Set",
  "key": "session:token",
  "status": "success",
  "latency_ms": 2
}
```

**Test Cases**:
- `TestSet_BR004_AuditLogSentOnSuccess`
- `TestSet_BR004_AuditLogSentOnFailure`
- `TestSet_BR004_AuditLogDoesNotContainValue`

---

### BR-005: Hash Field Operations

**Description**: Hash operations must support partial field updates.

**Given**: A hash exists
**When**: HSet is called with new fields
**Then**:
- Only specified fields are updated
- Existing fields are preserved
- Non-existent hash is created

**Test Cases**:
- `TestHSet_BR005_UpdatesOnlySpecifiedFields`
- `TestHSet_BR005_PreservesExistingFields`
- `TestHSet_BR005_CreatesNewHashIfNotExists`

---

## Edge Cases

### EC-001: Empty Key

**Given**: User provides empty string as key
**When**: Set/Get is called
**Then**: Returns InvalidArgument error with message "key cannot be empty"

**Test Cases**:
- `TestSet_EC001_EmptyKeyReturnsInvalidArgument`
- `TestGet_EC001_EmptyKeyReturnsInvalidArgument`

---

### EC-002: Key Too Long

**Given**: User provides key longer than 1024 characters
**When**: Set is called
**Then**: Returns InvalidArgument error with message "key exceeds maximum length"

**Test Cases**:
- `TestSet_EC002_KeyTooLongReturnsInvalidArgument`

---

### EC-003: Empty Value

**Given**: User provides empty string as value
**When**: Set is called
**Then**: Operation succeeds (empty string is valid value)

**Test Cases**:
- `TestSet_EC003_EmptyValueIsAllowed`

---

### EC-004: Non-Existent Key

**Given**: Key does not exist
**When**: Get is called
**Then**: Returns NotFound error with message "key not found"

**Test Cases**:
- `TestGet_EC004_NonExistentKeyReturnsNotFound`

---

### EC-005: Negative TTL

**Given**: User provides TTL < 0
**When**: Set is called
**Then**: Returns InvalidArgument error with message "TTL cannot be negative"

**Test Cases**:
- `TestSet_EC005_NegativeTTLReturnsInvalidArgument`

---

### EC-006: Redis Connection Failure

**Given**: Redis backend is unavailable
**When**: Any operation is called
**Then**: Returns Unavailable error with message "redis unavailable"

**Test Cases**:
- `TestSet_EC006_RedisUnavailableReturnsError`
- `TestGet_EC006_RedisUnavailableReturnsError`

---

### EC-007: Concurrent Updates

**Given**: Two users update the same key simultaneously
**When**: Both Set operations complete
**Then**: Last write wins (Redis default behavior)

**Test Cases**:
- `TestSet_EC007_ConcurrentUpdatesLastWriteWins`

---

## Error Handling Rules

### ER-001: Error Response Format

All errors must return consistent gRPC status codes:

| Condition | gRPC Code | Message Pattern |
|-----------|-----------|-----------------|
| Empty/invalid input | `InvalidArgument` | "{field} {issue}" |
| Auth failure | `PermissionDenied` | "unauthorized" |
| Key not found | `NotFound` | "key not found" |
| Redis error | `Internal` | "internal error" |
| Redis unavailable | `Unavailable` | "redis unavailable" |

**Test Cases**:
- `TestErrorFormat_ER001_ConsistentErrorCodes`

---

### ER-002: Error Logging

All errors must be logged before returning:

**Given**: An error occurs
**When**: Error is returned to client
**Then**:
- Error logged with stack trace (internal errors)
- Error logged without stack trace (client errors)
- Audit log updated with failure status

**Test Cases**:
- `TestErrorLogging_ER002_InternalErrorsLoggedWithStack`
- `TestErrorLogging_ER002_ClientErrorsLoggedWithoutStack`

---

## State Machines

### Key Lifecycle

```
                    ┌─────────────────────────────────┐
                    │                                 │
                    ▼                                 │
┌──────────┐     Set()    ┌──────────┐    Delete()   │
│   None   │ ───────────▶ │  Exists  │ ──────────────┤
└──────────┘              └────┬─────┘               │
     ▲                         │                     │
     │                         │ TTL expires         │
     │                         ▼                     │
     │                    ┌──────────┐               │
     └────────────────────│  Expired │───────────────┘
                          └──────────┘
```

### Hash Field Lifecycle

```
┌────────────────┐     HSet(field)    ┌────────────────┐
│  Field None    │ ─────────────────▶ │  Field Exists  │
└────────────────┘                    └───────┬────────┘
        ▲                                     │
        │              HDel(field)            │
        └─────────────────────────────────────┘
```

---

## Performance Expectations

| Operation | Expected Latency (p99) | Notes |
|-----------|------------------------|-------|
| Set | < 5ms | Single key |
| Get | < 2ms | Single key |
| MGet | < 10ms | Up to 100 keys |
| HSet | < 5ms | Up to 10 fields |
| HGetAll | < 5ms | Up to 100 fields |

---

## Related Documents

- [Data Contract](../../../api/proto/redis_service.proto) - Proto definitions
- [System Contract](../shared_system_contract.md) - Testing methodology
- [Fixtures](./fixtures.go) - Test data factories

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
