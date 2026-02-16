# DuckDB Service - Logic Contract

> Business Rules and Edge Cases for DuckDB gRPC Service (Analytics Database)

---

## Overview

This document defines the business rules for the DuckDB gRPC service, covering OLAP queries, data import/export, and analytics operations.

---

## Business Rules

### BR-001: Multi-Tenant Data Isolation

**Description**: Data is isolated by organization through schema or table prefix.

**Given**: A user executes a query
**When**: Query is processed
**Then**:
- Tables scoped to organization schema
- Cannot access other org's data
- Audit log records all queries

**Schema Pattern**:
```sql
-- Each org gets its own schema
CREATE SCHEMA IF NOT EXISTS org_001;
CREATE TABLE org_001.sales (...);

-- Queries automatically scoped
SELECT * FROM org_001.sales;
```

**Test Cases**:
- `TestQuery_BR001_QueryScopedToOrgSchema`
- `TestQuery_BR001_CannotAccessOtherOrgSchema`

---

### BR-002: OLAP Query Execution

**Description**: Execute analytical queries optimized for aggregations.

**Given**: An analytical query
**When**: Query is executed
**Then**:
- Columnar execution for efficiency
- Aggregations computed in parallel
- Results returned as JSON or Arrow format

**Typical Queries**:
```sql
-- Aggregation
SELECT product_id, SUM(quantity), AVG(price)
FROM sales
GROUP BY product_id;

-- Window function
SELECT *,
  ROW_NUMBER() OVER (PARTITION BY category ORDER BY sales DESC) as rank
FROM products;

-- Time series
SELECT DATE_TRUNC('month', order_date), COUNT(*)
FROM orders
GROUP BY 1
ORDER BY 1;
```

**Test Cases**:
- `TestQuery_BR002_AggregationQueryExecutes`
- `TestQuery_BR002_WindowFunctionExecutes`
- `TestQuery_BR002_TimeSeriesQueryExecutes`

---

### BR-003: Data Import from External Sources

**Description**: Import data from various file formats.

**Given**: External data source (CSV, Parquet, JSON)
**When**: Import is called
**Then**:
- Data loaded into organization's schema
- Schema inferred or specified
- Large files streamed efficiently

**Supported Formats**:

| Format | Read | Write | Notes |
|--------|------|-------|-------|
| CSV | Yes | Yes | Auto-detect delimiter |
| Parquet | Yes | Yes | Best for large data |
| JSON | Yes | Yes | NDJSON supported |
| Arrow | Yes | Yes | Native format |

**Test Cases**:
- `TestImport_BR003_CSVImportSucceeds`
- `TestImport_BR003_ParquetImportSucceeds`
- `TestImport_BR003_SchemaInferredCorrectly`

---

### BR-004: Data Export

**Description**: Export query results to various formats.

**Given**: A query result
**When**: Export is called
**Then**:
- Results written to specified format
- Can export to file or stream
- Large results paginated

**Test Cases**:
- `TestExport_BR004_ExportToCSV`
- `TestExport_BR004_ExportToParquet`
- `TestExport_BR004_LargeResultStreamedExport`

---

### BR-005: Query Result Pagination

**Description**: Large results are paginated for efficiency.

**Given**: Query returns many rows
**When**: Query is executed
**Then**:
- First N rows returned with cursor
- Subsequent pages fetched with cursor
- Total count optionally provided

**Pagination Parameters**:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `limit` | Max rows per page | 10000 |
| `offset` | Skip rows | 0 |
| `cursor` | Continuation token | None |

**Test Cases**:
- `TestQuery_BR005_PaginatesLargeResults`
- `TestQuery_BR005_CursorFetchesNextPage`

---

### BR-006: Query Caching

**Description**: Frequent queries cached for performance.

**Given**: A query is executed
**When**: Same query is executed again
**Then**:
- Results served from cache if valid
- Cache invalidated on data changes
- Cache scoped to organization

**Test Cases**:
- `TestQuery_BR006_RepeatedQueryServedFromCache`
- `TestQuery_BR006_CacheInvalidatedOnInsert`

---

### BR-007: Temporary Tables

**Description**: Create temporary tables for complex analysis.

**Given**: User needs intermediate results
**When**: Temporary table is created
**Then**:
- Table exists only for session
- Automatically cleaned up
- Scoped to organization

**Test Cases**:
- `TestTempTable_BR007_CreatedSuccessfully`
- `TestTempTable_BR007_CleanedUpAfterSession`

---

### BR-008: Audit Logging

**Description**: All queries logged for audit trail.

**Given**: Any query is executed
**When**: Query completes
**Then**:
- Audit log sent to Loki
- Includes: timestamp, user_id, org_id, query, duration
- Results NOT logged

**Test Cases**:
- `TestQuery_BR008_AuditLogRecorded`
- `TestImport_BR008_AuditLogRecorded`

---

## Edge Cases

### EC-001: Empty Query

**Given**: User provides empty query string
**When**: Query is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestQuery_EC001_EmptyQueryReturnsError`

---

### EC-002: Syntax Error

**Given**: User provides malformed SQL
**When**: Query is called
**Then**: Returns InvalidArgument error with details

**Test Cases**:
- `TestQuery_EC002_SyntaxErrorReturnsError`

---

### EC-003: Table Not Found

**Given**: Query references non-existent table
**When**: Query is called
**Then**: Returns NotFound error

**Test Cases**:
- `TestQuery_EC003_TableNotFoundReturnsError`

---

### EC-004: Query Timeout

**Given**: Query runs longer than timeout
**When**: Timeout is exceeded
**Then**: Query cancelled, returns DeadlineExceeded

**Test Cases**:
- `TestQuery_EC004_TimeoutReturnsDeadlineExceeded`

---

### EC-005: Memory Limit Exceeded

**Given**: Query requires more memory than allowed
**When**: Query is executed
**Then**: Returns ResourceExhausted error

**Test Cases**:
- `TestQuery_EC005_MemoryLimitReturnsResourceExhausted`

---

### EC-006: Invalid File Format

**Given**: Import file is corrupted or wrong format
**When**: Import is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestImport_EC006_InvalidFormatReturnsError`

---

### EC-007: File Not Found

**Given**: Import file path doesn't exist
**When**: Import is called
**Then**: Returns NotFound error

**Test Cases**:
- `TestImport_EC007_FileNotFoundReturnsError`

---

### EC-008: DuckDB Unavailable

**Given**: DuckDB instance is down
**When**: Any operation is called
**Then**: Returns Unavailable error

**Test Cases**:
- `TestQuery_EC008_DuckDBUnavailableReturnsError`

---

### EC-009: Division by Zero

**Given**: Query contains division by zero
**When**: Query is executed
**Then**: Returns error or NULL based on setting

**Test Cases**:
- `TestQuery_EC009_DivisionByZeroHandled`

---

## Error Handling Rules

### ER-001: Error Response Mapping

| DuckDB Error | gRPC Code | Message |
|--------------|-----------|---------|
| Syntax error | `InvalidArgument` | "syntax error: {details}" |
| Table not found | `NotFound` | "table not found" |
| Permission denied | `PermissionDenied` | "access denied" |
| Out of memory | `ResourceExhausted` | "memory limit exceeded" |
| Connection error | `Unavailable` | "duckdb unavailable" |
| Timeout | `DeadlineExceeded` | "query timeout" |

---

## Performance Expectations

| Operation | Expected Latency (p99) | Notes |
|-----------|------------------------|-------|
| Simple SELECT | < 10ms | Small table |
| Aggregation (1M rows) | < 500ms | Single group by |
| Join (2 tables) | < 1s | Indexed |
| Full table scan | < 5s | Depends on size |
| CSV import (100K rows) | < 2s | |
| Parquet import (1M rows) | < 5s | |
| Export to CSV | < 2s | Per 100K rows |

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
