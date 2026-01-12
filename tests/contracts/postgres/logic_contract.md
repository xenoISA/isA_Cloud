# PostgreSQL Service - Logic Contract

> Business Rules and Edge Cases for PostgreSQL gRPC Service

---

## Overview

This document defines the business rules, state transitions, and edge cases for the PostgreSQL gRPC service.

---

## Business Rules

### BR-001: Query Execution with Parameter Binding

**Description**: All queries must use parameterized queries to prevent SQL injection.

**Given**: A query with parameters
**When**: Execute is called
**Then**:
- Parameters are bound safely (not string concatenation)
- Query executes with bound parameters
- Results returned as JSON array

**Examples**:

| Query | Args | Safe Execution |
|-------|------|----------------|
| `SELECT * FROM users WHERE id = $1` | `["123"]` | Yes |
| `SELECT * FROM users WHERE id = '123'` | `[]` | Yes (no injection risk) |

**Test Cases**:
- `TestExecute_BR001_ParameterizedQueryPreventsInjection`
- `TestExecute_BR001_MultipleParametersBindCorrectly`

---

### BR-002: Multi-Tenant Data Isolation

**Description**: All queries must be scoped to the user's organization.

**Given**: A user executes a query
**When**: Query accesses data
**Then**:
- Query is automatically filtered by organization_id
- User cannot access other organization's data
- Audit log records the query

**Implementation Options**:
1. Row-level security (RLS)
2. Automatic WHERE clause injection
3. Schema-per-tenant

**Test Cases**:
- `TestExecute_BR002_QueryScopedToOrganization`
- `TestExecute_BR002_CannotAccessOtherOrgData`

---

### BR-003: Query Result Formatting

**Description**: Query results must be returned in consistent JSON format.

**Given**: A SELECT query executes successfully
**When**: Results are returned
**Then**:
- Rows returned as JSON array
- Column names as keys
- Proper type conversion (timestamps, numerics, etc.)
- NULL values represented as JSON null

**Result Format**:
```json
{
  "rows": [
    {"id": 1, "name": "Alice", "created_at": "2025-01-01T00:00:00Z"},
    {"id": 2, "name": "Bob", "created_at": "2025-01-02T00:00:00Z"}
  ],
  "row_count": 2,
  "columns": ["id", "name", "created_at"]
}
```

**Test Cases**:
- `TestExecute_BR003_ResultsReturnedAsJSON`
- `TestExecute_BR003_NullValuesHandledCorrectly`
- `TestExecute_BR003_TimestampsFormattedAsISO8601`

---

### BR-004: Affected Rows for Mutations

**Description**: INSERT/UPDATE/DELETE must return affected row count.

**Given**: A mutation query executes
**When**: Query completes
**Then**:
- Returns number of affected rows
- No row data returned (unless RETURNING clause)
- Audit log records the mutation

**Test Cases**:
- `TestExecute_BR004_InsertReturnsAffectedRows`
- `TestExecute_BR004_UpdateReturnsAffectedRows`
- `TestExecute_BR004_DeleteReturnsAffectedRows`

---

### BR-005: Transaction Support

**Description**: Multiple queries can be executed atomically in a transaction.

**Given**: A transaction is started
**When**: Multiple queries are executed
**Then**:
- All queries see consistent snapshot
- Commit makes all changes permanent
- Rollback undoes all changes
- Transaction times out after configured period

**State Diagram**:
```
┌─────────────┐   BeginTx()   ┌─────────────┐
│    Idle     │ ────────────▶ │   Active    │
└─────────────┘               └──────┬──────┘
       ▲                             │
       │                    ┌────────┴────────┐
       │                    ▼                 ▼
       │              ┌──────────┐      ┌──────────┐
       │              │  Commit  │      │ Rollback │
       │              └────┬─────┘      └────┬─────┘
       │                   │                 │
       └───────────────────┴─────────────────┘
```

**Test Cases**:
- `TestTransaction_BR005_CommitMakesChangesPermanent`
- `TestTransaction_BR005_RollbackUndoesChanges`
- `TestTransaction_BR005_TimeoutCausesRollback`

---

### BR-006: Audit Logging

**Description**: All queries must be logged for audit trail.

**Given**: Any query is executed
**When**: Query completes
**Then**:
- Audit log entry sent to Loki
- Log includes: timestamp, user_id, org_id, query (sanitized), status
- Sensitive data NOT logged (passwords, PII in results)

**Test Cases**:
- `TestExecute_BR006_AuditLogRecordsQuery`
- `TestExecute_BR006_SensitiveDataNotLogged`

---

## Edge Cases

### EC-001: Empty Query

**Given**: User provides empty query string
**When**: Execute is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestExecute_EC001_EmptyQueryReturnsError`

---

### EC-002: Syntax Error in Query

**Given**: User provides malformed SQL
**When**: Execute is called
**Then**: Returns InvalidArgument error with syntax details

**Test Cases**:
- `TestExecute_EC002_SyntaxErrorReturnsInvalidArgument`

---

### EC-003: Query Timeout

**Given**: Query runs longer than timeout
**When**: Timeout is exceeded
**Then**: Query is cancelled, returns DeadlineExceeded

**Test Cases**:
- `TestExecute_EC003_LongQueryTimesOut`

---

### EC-004: Connection Pool Exhausted

**Given**: All connections in pool are in use
**When**: New query is submitted
**Then**: Returns Unavailable error after wait timeout

**Test Cases**:
- `TestExecute_EC004_PoolExhaustedReturnsUnavailable`

---

### EC-005: Table Does Not Exist

**Given**: Query references non-existent table
**When**: Execute is called
**Then**: Returns NotFound error

**Test Cases**:
- `TestExecute_EC005_NonExistentTableReturnsNotFound`

---

### EC-006: Permission Denied on Table

**Given**: User lacks permission on table
**When**: Execute is called
**Then**: Returns PermissionDenied error

**Test Cases**:
- `TestExecute_EC006_NoPermissionReturnsPermissionDenied`

---

### EC-007: Large Result Set

**Given**: Query returns more than max rows (e.g., 10000)
**When**: Execute is called
**Then**: Returns first max rows with truncation warning

**Test Cases**:
- `TestExecute_EC007_LargeResultSetTruncated`

---

## Error Handling Rules

### ER-001: Error Response Mapping

| PostgreSQL Error | gRPC Code | Message |
|------------------|-----------|---------|
| Syntax error | `InvalidArgument` | "syntax error: {details}" |
| Table not found | `NotFound` | "table not found: {table}" |
| Permission denied | `PermissionDenied` | "access denied" |
| Connection error | `Unavailable` | "database unavailable" |
| Query timeout | `DeadlineExceeded` | "query timeout" |
| Other errors | `Internal` | "internal error" |

---

## Performance Expectations

| Operation | Expected Latency (p99) | Notes |
|-----------|------------------------|-------|
| Simple SELECT | < 10ms | Single row by PK |
| Complex SELECT | < 100ms | Joins, aggregations |
| INSERT single | < 10ms | Single row |
| Batch INSERT | < 100ms | Up to 1000 rows |
| Transaction | < 500ms | Multiple statements |

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
