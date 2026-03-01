# Contract Coverage Report

> Auto-generated mapping of logic contract IDs to test functions.
> See `tests/contracts/{service}/logic_contract.md` for full contract definitions.
> See `isA_common/tests/{service}/test_async_{service}.py` for test implementations.

## Summary

| Service    | BR Covered | BR Total | EC Covered | EC Total | ER Covered | ER Total | Coverage |
|------------|-----------|----------|-----------|----------|-----------|----------|----------|
| Redis      | 4/5       | 80%      | 2/7       | 29%      | 0/2       | 0%       | **43%**  |
| PostgreSQL | 3/6       | 50%      | 1/7       | 14%      | 0/1       | 0%       | **29%**  |
| Neo4j      | 4/7       | 57%      | 0/8       | 0%       | 0/1       | 0%       | **25%**  |
| NATS       | 5/6       | 83%      | 0/8       | 0%       | 0/1       | 0%       | **33%**  |
| MQTT       | 3/7       | 43%      | 0/7       | 0%       | 0/1       | 0%       | **20%**  |
| MinIO      | 3/7       | 43%      | 1/8       | 13%      | 0/1       | 0%       | **25%**  |
| Qdrant     | 5/8       | 63%      | 1/8       | 13%      | 0/1       | 0%       | **35%**  |
| DuckDB     | 2/8       | 25%      | 0/9       | 0%       | 0/1       | 0%       | **11%**  |
| **Total**  | **29/54** | **54%**  | **5/62**  | **8%**   | **0/9**   | **0%**   | **27%**  |

## Detailed Mapping

### Redis

| Contract ID | Description | Test Function(s) | Status |
|------------|-------------|------------------|--------|
| BR-001 | Multi-Tenant Key Isolation | `test_string_operations` | Covered |
| BR-002 | TTL Expiration | `test_ttl_expiration` | Covered |
| BR-003 | User Authentication | `test_string_operations` | Covered |
| BR-004 | Audit Logging | — | Missing |
| BR-005 | Hash Field Operations | `test_hash_operations` | Covered |
| EC-001 | Empty Key | — | Missing |
| EC-002 | Key Too Long | — | Missing |
| EC-003 | Empty Value | `test_string_operations` | Covered |
| EC-004 | Non-Existent Key | `test_string_operations` | Covered |
| EC-005 | Negative TTL | — | Missing |
| EC-006 | Redis Connection Failure | — | Missing |
| EC-007 | Concurrent Updates | `test_concurrent_operations`, `test_get_many_concurrent` | Covered |
| ER-001 | Error Response Format | — | Missing |
| ER-002 | Error Logging | — | Missing |

### PostgreSQL

| Contract ID | Description | Test Function(s) | Status |
|------------|-------------|------------------|--------|
| BR-001 | Query Execution with Parameter Binding | `test_query_with_params` | Covered |
| BR-002 | Multi-Tenant Data Isolation | — | Missing |
| BR-003 | Query Result Formatting | `test_simple_query`, `test_query_row`, `test_select_from_table` | Covered |
| BR-004 | Affected Rows for Mutations | `test_execute_insert`, `test_execute_update`, `test_execute_delete` | Covered |
| BR-005 | Transaction Support | — | Missing |
| BR-006 | Audit Logging | — | Missing |
| EC-001 | Empty Query | — | Missing |
| EC-002 | Syntax Error in Query | — | Missing |
| EC-003 | Query Timeout | — | Missing |
| EC-004 | Connection Pool Exhausted | — | Missing |
| EC-005 | Table Does Not Exist | `test_table_exists`, `test_select_from_table` | Covered |
| EC-006 | Permission Denied on Table | — | Missing |
| EC-007 | Large Result Set | — | Missing |
| ER-001 | Error Response Mapping | — | Missing |

### Neo4j

| Contract ID | Description | Test Function(s) | Status |
|------------|-------------|------------------|--------|
| BR-001 | Multi-Tenant Graph Isolation | — | Missing |
| BR-002 | Node Operations | `test_create_node`, `test_get_node`, `test_update_node`, `test_create_second_node`, `test_find_nodes`, `test_delete_node` | Covered |
| BR-003 | Relationship Operations | `test_create_relationship`, `test_get_relationship`, `test_delete_relationship` | Covered |
| BR-004 | Cypher Query Execution | `test_run_cypher`, `test_cypher_with_params` | Covered |
| BR-005 | Graph Traversal | `test_get_path`, `test_shortest_path` | Covered |
| BR-006 | Index and Constraint Support | — | Missing |
| BR-007 | Audit Logging | — | Missing |
| EC-001 | Empty Query | — | Missing |
| EC-002 | Syntax Error in Cypher | — | Missing |
| EC-003 | Node Not Found | — | Missing |
| EC-004 | Relationship Node Not Found | — | Missing |
| EC-005 | Unique Constraint Violation | — | Missing |
| EC-006 | Query Timeout | — | Missing |
| EC-007 | Neo4j Unavailable | — | Missing |
| EC-008 | Invalid Label Name | — | Missing |
| ER-001 | Error Response Mapping | — | Missing |

### NATS

| Contract ID | Description | Test Function(s) | Status |
|------------|-------------|------------------|--------|
| BR-001 | Subject-Based Publish/Subscribe | `test_publish`, `test_publish_with_headers` | Covered |
| BR-002 | Multi-Tenant Subject Isolation | — | Missing |
| BR-003 | JetStream Persistence | `test_create_stream`, `test_publish_to_stream` | Covered |
| BR-004 | Consumer Acknowledgment | `test_create_consumer`, `test_pull_messages` | Covered |
| BR-005 | Key-Value Store | `test_kv_operations` | Covered |
| BR-006 | Request-Reply Pattern | `test_request_reply` | Covered |
| EC-001 | Empty Subject | — | Missing |
| EC-002 | Invalid Subject Characters | — | Missing |
| EC-003 | Message Too Large | — | Missing |
| EC-004 | Stream Does Not Exist | — | Missing |
| EC-005 | Consumer Does Not Exist | — | Missing |
| EC-006 | KV Bucket Does Not Exist | — | Missing |
| EC-007 | Duplicate Durable Consumer | — | Missing |
| EC-008 | NATS Unavailable | — | Missing |
| ER-001 | Error Response Mapping | — | Missing |

### MQTT

| Contract ID | Description | Test Function(s) | Status |
|------------|-------------|------------------|--------|
| BR-001 | Multi-Tenant Topic Isolation | — | Missing |
| BR-002 | Topic Wildcards | — | Missing |
| BR-003 | Quality of Service (QoS) | `test_publish`, `test_publish_batch` | Covered |
| BR-004 | Retained Messages | `test_set_retained_message`, `test_get_retained_message`, `test_delete_retained_message` | Covered |
| BR-005 | Last Will and Testament (LWT) | — | Missing |
| BR-006 | Message Payload | `test_publish`, `test_publish_json` | Covered |
| BR-007 | Audit Logging | — | Missing |
| EC-001 | Empty Topic | — | Missing |
| EC-002 | Invalid Topic Characters | — | Missing |
| EC-003 | Topic Too Long | — | Missing |
| EC-004 | Invalid QoS Level | — | Missing |
| EC-005 | Wildcard in Publish Topic | — | Missing |
| EC-006 | Broker Unavailable | — | Missing |
| EC-007 | Connection Timeout | — | Missing |
| ER-001 | Error Response Mapping | — | Missing |

### MinIO

| Contract ID | Description | Test Function(s) | Status |
|------------|-------------|------------------|--------|
| BR-001 | Multi-Tenant Bucket Isolation | — | Missing |
| BR-002 | Object Key Namespacing | — | Missing |
| BR-003 | Presigned URL Generation | `test_presigned_url`, `test_presigned_put_url` | Covered |
| BR-004 | Object Metadata | `test_upload_object`, `test_get_object_metadata` | Covered |
| BR-005 | Object Listing with Pagination | `test_list_objects` | Covered |
| BR-006 | Object Versioning | — | Missing |
| BR-007 | Audit Logging | — | Missing |
| EC-001 | Invalid Bucket Name | — | Missing |
| EC-002 | Bucket Already Exists | `test_create_bucket` | Covered |
| EC-003 | Bucket Not Empty | — | Missing |
| EC-004 | Object Not Found | — | Missing |
| EC-005 | Empty Object Key | — | Missing |
| EC-006 | Object Too Large | — | Missing |
| EC-007 | MinIO Unavailable | — | Missing |
| EC-008 | Presigned URL Expired | — | Missing |
| ER-001 | Error Response Mapping | — | Missing |

### Qdrant

| Contract ID | Description | Test Function(s) | Status |
|------------|-------------|------------------|--------|
| BR-001 | Multi-Tenant Collection Isolation | — | Missing |
| BR-002 | Collection Configuration | `test_create_collection` | Covered |
| BR-003 | Vector Upsert with Payload | `test_upsert_points` | Covered |
| BR-004 | Similarity Search | `test_search` | Covered |
| BR-005 | Payload Filtering | `test_search_with_filter` | Covered |
| BR-006 | Batch Operations | `test_upsert_points`, `test_delete_points` | Covered |
| BR-007 | Point Retrieval by ID | `test_update_payload` | Covered |
| BR-008 | Audit Logging | — | Missing |
| EC-001 | Invalid Vector Dimension | — | Missing |
| EC-002 | Collection Does Not Exist | — | Missing |
| EC-003 | Collection Already Exists | — | Missing |
| EC-004 | Empty Query Vector | — | Missing |
| EC-005 | Invalid Filter Syntax | — | Missing |
| EC-006 | Top-K Too Large | — | Missing |
| EC-007 | Qdrant Unavailable | — | Missing |
| EC-008 | Vector ID Conflict in Batch | `test_upsert_points` | Covered |
| ER-001 | Error Response Mapping | — | Missing |

### DuckDB

| Contract ID | Description | Test Function(s) | Status |
|------------|-------------|------------------|--------|
| BR-001 | Multi-Tenant Data Isolation | — | Missing |
| BR-002 | OLAP Query Execution | `test_simple_query`, `test_query_with_params`, `test_query_data`, `test_aggregate_functions` | Covered |
| BR-003 | Data Import from External Sources | — | Missing |
| BR-004 | Data Export | `test_csv_export` | Covered |
| BR-005 | Query Result Pagination | — | Missing |
| BR-006 | Query Caching | — | Missing |
| BR-007 | Temporary Tables | — | Missing |
| BR-008 | Audit Logging | — | Missing |
| EC-001 | Empty Query | — | Missing |
| EC-002 | Syntax Error | — | Missing |
| EC-003 | Table Not Found | — | Missing |
| EC-004 | Query Timeout | — | Missing |
| EC-005 | Memory Limit Exceeded | — | Missing |
| EC-006 | Invalid File Format | — | Missing |
| EC-007 | File Not Found | — | Missing |
| EC-008 | DuckDB Unavailable | — | Missing |
| EC-009 | Division by Zero | — | Missing |
| ER-001 | Error Response Mapping | — | Missing |

## Missing Scenarios for Future Work

### High-Value Gaps (recommended next)

1. **Multi-tenant isolation tests** (BR-001 across all services) — Critical for security
2. **Error response format tests** (ER-001 across all services) — Validates API contract consistency
3. **Connection failure handling** (EC-006/EC-007/EC-008) — Resilience testing
4. **Audit logging verification** (BR-004/BR-007/BR-008) — Compliance

### Edge Cases (lower priority)

- Empty/invalid input handling (EC-001, EC-002 across services)
- Resource limit testing (EC-003, EC-005, EC-006)
- Timeout behavior (EC-003, EC-004, EC-006)
- Concurrent write conflicts beyond Redis EC-007
