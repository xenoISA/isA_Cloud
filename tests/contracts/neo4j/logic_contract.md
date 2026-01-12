# Neo4j Service - Logic Contract

> Business Rules and Edge Cases for Neo4j gRPC Service (Graph Database)

---

## Overview

This document defines the business rules for the Neo4j gRPC service, covering node/relationship operations and graph traversal queries.

---

## Business Rules

### BR-001: Multi-Tenant Graph Isolation

**Description**: Graph data is isolated by organization using labels and properties.

**Given**: A user performs graph operations
**When**: Any operation is executed
**Then**:
- Nodes labeled with `_org_{org_id}`
- Queries filtered by org label automatically
- Cannot access other org's graph data

**Examples**:

| Operation | Org ID | Cypher Transformation |
|-----------|--------|----------------------|
| `MATCH (n:User)` | `org-001` | `MATCH (n:User:_org_org_001)` |
| `CREATE (n:User)` | `org-002` | `CREATE (n:User:_org_org_002)` |

**Test Cases**:
- `TestCreateNode_BR001_NodeLabeledWithOrg`
- `TestQuery_BR001_ResultsFilteredByOrg`
- `TestQuery_BR001_CannotAccessOtherOrgData`

---

### BR-002: Node Operations

**Description**: Create, read, update, delete nodes with properties.

**Given**: Node operations
**When**: CRUD is performed
**Then**:
- Nodes have unique ID within org
- Properties stored as key-value pairs
- Labels categorize nodes

**Node Structure**:
```cypher
CREATE (n:Person:_org_org001 {
  id: "person-123",
  name: "Alice",
  email: "alice@example.com",
  created_at: datetime()
})
```

**Test Cases**:
- `TestCreateNode_BR002_NodeCreatedWithProperties`
- `TestGetNode_BR002_ReturnsNodeById`
- `TestUpdateNode_BR002_UpdatesProperties`
- `TestDeleteNode_BR002_RemovesNode`

---

### BR-003: Relationship Operations

**Description**: Create and query relationships between nodes.

**Given**: Two nodes exist
**When**: Relationship is created
**Then**:
- Relationship has type and direction
- Can have properties
- Both nodes must be in same org

**Relationship Structure**:
```cypher
MATCH (a:Person {id: "person-1"}), (b:Person {id: "person-2"})
CREATE (a)-[r:KNOWS {since: date("2020-01-01")}]->(b)
RETURN r
```

**Test Cases**:
- `TestCreateRelationship_BR003_RelationshipCreated`
- `TestCreateRelationship_BR003_CrossOrgFails`
- `TestQueryRelationships_BR003_ReturnsConnectedNodes`

---

### BR-004: Cypher Query Execution

**Description**: Execute Cypher queries with parameter binding.

**Given**: A Cypher query with parameters
**When**: Query is executed
**Then**:
- Parameters bound safely (no injection)
- Results returned as structured data
- Query automatically scoped to org

**Parameter Binding**:
```cypher
// Input query
MATCH (n:Person {name: $name}) RETURN n

// Parameters
{"name": "Alice"}

// Safe execution (no string concatenation)
```

**Test Cases**:
- `TestQuery_BR004_ParameterizedQuerySafe`
- `TestQuery_BR004_ResultsReturnedAsJSON`

---

### BR-005: Graph Traversal

**Description**: Query patterns for traversing relationships.

**Given**: A connected graph
**When**: Traversal query is executed
**Then**:
- Supports variable-length paths
- Supports shortest path
- Results include path information

**Traversal Examples**:
```cypher
// Find friends of friends
MATCH (a:Person)-[:KNOWS*2]->(b:Person)
WHERE a.id = $id
RETURN DISTINCT b

// Shortest path
MATCH p = shortestPath((a:Person)-[*]-(b:Person))
WHERE a.id = $from AND b.id = $to
RETURN p
```

**Test Cases**:
- `TestTraversal_BR005_VariableLengthPath`
- `TestTraversal_BR005_ShortestPath`
- `TestTraversal_BR005_PathResultsReturned`

---

### BR-006: Index and Constraint Support

**Description**: Create indexes and constraints for performance.

**Given**: Admin requests index/constraint
**When**: Schema operation is called
**Then**:
- Indexes created on specified properties
- Unique constraints enforced
- Indexes scoped to org label

**Test Cases**:
- `TestSchema_BR006_CreateIndex`
- `TestSchema_BR006_UniqueConstraintEnforced`

---

### BR-007: Audit Logging

**Description**: All operations logged for audit trail.

**Given**: Any operation is performed
**When**: Operation completes
**Then**:
- Audit log sent to Loki
- Includes: timestamp, user_id, org_id, operation, query
- Results NOT logged (may be large)

**Test Cases**:
- `TestQuery_BR007_AuditLogRecorded`
- `TestCreateNode_BR007_AuditLogRecorded`

---

## Edge Cases

### EC-001: Empty Query

**Given**: User provides empty Cypher query
**When**: Query is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestQuery_EC001_EmptyQueryReturnsError`

---

### EC-002: Syntax Error in Cypher

**Given**: User provides malformed Cypher
**When**: Query is called
**Then**: Returns InvalidArgument error with details

**Test Cases**:
- `TestQuery_EC002_SyntaxErrorReturnsError`

---

### EC-003: Node Not Found

**Given**: Node ID does not exist
**When**: GetNode/UpdateNode/DeleteNode is called
**Then**: Returns NotFound error

**Test Cases**:
- `TestGetNode_EC003_NonExistentReturnsNotFound`

---

### EC-004: Relationship Node Not Found

**Given**: Source or target node doesn't exist
**When**: CreateRelationship is called
**Then**: Returns NotFound error

**Test Cases**:
- `TestCreateRelationship_EC004_NodeNotFoundReturnsError`

---

### EC-005: Unique Constraint Violation

**Given**: Unique constraint exists on property
**When**: Duplicate value is inserted
**Then**: Returns AlreadyExists error

**Test Cases**:
- `TestCreateNode_EC005_UniqueViolationReturnsError`

---

### EC-006: Query Timeout

**Given**: Query runs longer than timeout
**When**: Timeout is exceeded
**Then**: Query cancelled, returns DeadlineExceeded

**Test Cases**:
- `TestQuery_EC006_TimeoutReturnsDeadlineExceeded`

---

### EC-007: Neo4j Unavailable

**Given**: Neo4j database is down
**When**: Any operation is called
**Then**: Returns Unavailable error

**Test Cases**:
- `TestQuery_EC007_Neo4jUnavailableReturnsError`

---

### EC-008: Invalid Label Name

**Given**: Label contains invalid characters
**When**: CreateNode is called
**Then**: Returns InvalidArgument error

**Test Cases**:
- `TestCreateNode_EC008_InvalidLabelReturnsError`

---

## Error Handling Rules

### ER-001: Error Response Mapping

| Neo4j Error | gRPC Code | Message |
|-------------|-----------|---------|
| Syntax error | `InvalidArgument` | "cypher syntax error" |
| Node not found | `NotFound` | "node not found" |
| Constraint violation | `AlreadyExists` | "unique constraint violation" |
| Permission denied | `PermissionDenied` | "access denied" |
| Connection error | `Unavailable` | "neo4j unavailable" |
| Timeout | `DeadlineExceeded` | "query timeout" |

---

## Performance Expectations

| Operation | Expected Latency (p99) | Notes |
|-----------|------------------------|-------|
| CreateNode | < 20ms | Single node |
| GetNode | < 10ms | By ID with index |
| CreateRelationship | < 20ms | |
| Simple query | < 50ms | Single match |
| Traversal (depth 3) | < 200ms | Depends on graph |
| Shortest path | < 500ms | Depends on distance |

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
