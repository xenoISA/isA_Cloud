# Contract-Driven Development (CDD) for Go Services

**isA Cloud Platform - Go Microservices CDD Architecture**

This document provides an overview of the Contract-Driven Development approach for isA Cloud Go services, adapted from our Python CDD methodology.

---

## What is Contract-Driven Development?

Contract-Driven Development (CDD) is a methodology where **contracts define behavior before implementation**. It combines:

- **Domain-Driven Design (DDD)**: Understanding the problem space
- **Test-Driven Development (TDD)**: Writing tests before code
- **Documentation-First**: Clear specifications before implementation
- **Proto-First**: API contracts defined via Protocol Buffers

---

## The 5-Layer Contract Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CONTRACT-DRIVEN DEVELOPMENT (Go)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                        ┌──────────────────┐                                 │
│                        │     DOMAIN       │                                 │
│                        │    (Context)     │                                 │
│                        │ docs/domain/     │                                 │
│                        └────────┬─────────┘                                 │
│                                 │                                           │
│                                 ▼                                           │
│                        ┌──────────────────┐                                 │
│                        │       PRD        │                                 │
│                        │  (Requirements)  │                                 │
│                        │   docs/prd/      │                                 │
│                        └────────┬─────────┘                                 │
│                                 │                                           │
│                                 ▼                                           │
│                        ┌──────────────────┐                                 │
│                        │     DESIGN       │                                 │
│                        │  (Architecture)  │                                 │
│                        │  docs/design/    │                                 │
│                        └────────┬─────────┘                                 │
│                                 │                                           │
│                                 ▼                                           │
│         ┌───────────────────────┴───────────────────────┐                   │
│         │                                               │                   │
│         ▼                                               ▼                   │
│  ┌──────────────┐                              ┌──────────────────┐         │
│  │    DATA      │                              │     LOGIC        │         │
│  │  CONTRACT    │                              │    CONTRACT      │         │
│  │   (Proto)    │                              │  (Rules/Tests)   │         │
│  │ api/proto/   │                              │ logic_           │         │
│  │ *.proto      │                              │ contract.md      │         │
│  └──────┬───────┘                              └────────┬─────────┘         │
│         │                                               │                   │
│         └───────────────────────┬───────────────────────┘                   │
│                                 │                                           │
│                                 ▼                                           │
│                        ┌──────────────────┐                                 │
│                        │     SYSTEM       │                                 │
│                        │    CONTRACT      │                                 │
│                        │ (How to Test)    │                                 │
│                        │ shared_system_   │                                 │
│                        │ contract.md      │                                 │
│                        └──────────────────┘                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Go vs Python: Contract Mapping

| Contract Layer | Python Implementation | Go Implementation |
|----------------|----------------------|-------------------|
| **Domain** | `docs/domain/README.md` | `docs/domain/README.md` |
| **PRD** | `docs/prd/README.md` | `docs/prd/README.md` |
| **Design** | `docs/design/README.md` | `docs/design/README.md` |
| **Data Contract** | `data_contract.py` (Pydantic) | `api/proto/*.proto` (Protocol Buffers) |
| **Logic Contract** | `logic_contract.md` | `logic_contract.md` |
| **System Contract** | `shared_system_contract.md` | `shared_system_contract.md` |
| **Test Factories** | Python classes | Go structs + builder functions |
| **Test Markers** | `@pytest.mark.unit` | `//go:build unit` |

---

## Contract Responsibilities

| Layer | Document | Purpose | Audience |
|-------|----------|---------|----------|
| **Domain** | `docs/domain/README.md` | Business context, taxonomy, scenarios | Everyone |
| **PRD** | `docs/prd/README.md` | User stories, requirements, acceptance criteria | Product, Dev |
| **Design** | `docs/design/README.md` | Architecture, data flow, API design | Engineering |
| **Data Contract** | `api/proto/{svc}_service.proto` | gRPC schemas, message definitions | Engineering |
| **Logic Contract** | `tests/contracts/{svc}/logic_contract.md` | Business rules, state machines | Testing |
| **System Contract** | `tests/contracts/shared_system_contract.md` | How to test, environment setup | Testing |

---

## Directory Structure

```
isA_Cloud/
├── docs/
│   ├── cdd_guide.md              # ← This file (CDD guide)
│   │
│   ├── domain/                   # Layer 1: Domain Context
│   │   └── README.md             # Taxonomy, business scenarios
│   │
│   ├── prd/                      # Layer 2: Requirements
│   │   └── README.md             # User stories, AC
│   │
│   └── design/                   # Layer 3: Technical Design
│       └── README.md             # Architecture, data flow
│
├── api/
│   └── proto/                    # Layer 4: Data Contracts
│       ├── common.proto          # Shared message types
│       ├── redis_service.proto   # Redis service contract
│       ├── postgres_service.proto
│       ├── nats_service.proto
│       └── ...
│
├── tests/
│   ├── contracts/                # Layer 5-6: Test Contracts
│   │   ├── README.md             # Contract overview
│   │   ├── shared_system_contract.md  # Layer 6: System Contract
│   │   │
│   │   ├── redis/                # Per-service contracts
│   │   │   ├── logic_contract.md
│   │   │   └── fixtures.go       # Test data factories
│   │   │
│   │   ├── postgres/
│   │   │   ├── logic_contract.md
│   │   │   └── fixtures.go
│   │   │
│   │   └── nats/
│   │       ├── logic_contract.md
│   │       └── fixtures.go
│   │
│   ├── unit/                     # Unit tests (no external deps)
│   ├── integration/              # Integration tests (real deps)
│   └── e2e/                      # End-to-end tests
│
├── cmd/                          # Service entry points
│   └── {service}-service/
│       ├── main.go
│       └── server/
│           ├── server.go
│           └── server_test.go
│
├── internal/                     # Internal implementation
│   └── {service}/
│       ├── domain/               # Domain entities
│       ├── repository/           # Data access
│       ├── service/              # Business logic
│       └── handler/              # gRPC handlers
│
└── pkg/                          # Shared packages
    └── infrastructure/
```

---

## Development Workflow

### For New Features

```
1. UNDERSTAND DOMAIN
   └── Read docs/domain/README.md
       └── Understand taxonomy, scenarios

2. CHECK REQUIREMENTS
   └── Read docs/prd/README.md
       └── Find relevant user story
       └── Check acceptance criteria

3. REVIEW DESIGN
   └── Read docs/design/README.md
       └── Understand architecture
       └── Identify affected components

4. CREATE/UPDATE CONTRACTS
   └── Proto Contract (if new API)
       └── Define messages in api/proto/
       └── Run protoc to generate Go code

   └── Logic Contract (if new rules)
       └── Define business rules (BR-XXX)
       └── Define state machines
       └── Define edge cases (EC-XXX)

5. WRITE TDD TESTS
   └── Follow tests/contracts/shared_system_contract.md
       └── Write failing tests (RED)
       └── Implement feature
       └── Tests pass (GREEN)

6. UPDATE DOCS
   └── Update PRD status
   └── Update design if needed
```

### For Bug Fixes

```
1. WRITE GOLDEN TEST
   └── Capture current (buggy) behavior
   └── Document what actually happens

2. WRITE TDD TEST
   └── Define expected (correct) behavior
   └── Test should fail (RED)

3. FIX IMPLEMENTATION
   └── Make TDD test pass (GREEN)

4. UPDATE GOLDEN TEST
   └── Golden now shows correct behavior
```

---

## Contract Examples

### Data Contract Example (Proto)

```protobuf
// api/proto/redis_service.proto
syntax = "proto3";
package redis;

message SetRequest {
  string user_id = 1;
  string organization_id = 2;
  string key = 3;
  string value = 4;
  int64 ttl_seconds = 5;  // 0 = no expiry
}

message SetResponse {
  bool success = 1;
  string message = 2;
}

service RedisService {
  rpc Set(SetRequest) returns (SetResponse);
  rpc Get(GetRequest) returns (GetResponse);
  // ...
}
```

### Logic Contract Example (logic_contract.md)

```markdown
### BR-001: Multi-Tenant Key Isolation

**Given**: A user sets a key
**When**: The key is stored in Redis
**Then**:
- Key is prefixed with `{org_id}:{user_id}:`
- Other tenants cannot access the key
- Audit log is recorded

### BR-002: TTL Expiration

**Given**: A key is set with TTL > 0
**When**: TTL seconds have passed
**Then**:
- Key is automatically deleted
- Get returns NotFound error

### EC-001: Empty Key Handling

**Given**: User provides empty key
**When**: Set is called
**Then**: Returns InvalidArgument error
```

### Test Fixtures Example (Go)

```go
// tests/contracts/redis/fixtures.go
package redis_contract

import (
    pb "github.com/isa-cloud/isa_cloud/api/proto/redis"
)

// TestDataFactory provides test data for Redis service tests
type TestDataFactory struct{}

// MakeSetRequest creates a SetRequest with sensible defaults
func (f *TestDataFactory) MakeSetRequest(overrides ...func(*pb.SetRequest)) *pb.SetRequest {
    req := &pb.SetRequest{
        UserId:         "test-user-001",
        OrganizationId: "test-org-001",
        Key:            "test-key",
        Value:          "test-value",
        TtlSeconds:     0,
    }
    for _, override := range overrides {
        override(req)
    }
    return req
}

// WithTTL sets TTL on the request
func WithTTL(ttl int64) func(*pb.SetRequest) {
    return func(req *pb.SetRequest) {
        req.TtlSeconds = ttl
    }
}

// WithKey sets the key on the request
func WithKey(key string) func(*pb.SetRequest) {
    return func(req *pb.SetRequest) {
        req.Key = key
    }
}
```

### Test Example (Go with Build Tags)

```go
//go:build unit

package redis_test

import (
    "context"
    "testing"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"

    fixtures "github.com/isa-cloud/isa_cloud/tests/contracts/redis"
)

// TestSet_BR001_MultiTenantIsolation tests BR-001
func TestSet_BR001_MultiTenantIsolation(t *testing.T) {
    // Arrange
    factory := &fixtures.TestDataFactory{}
    req := factory.MakeSetRequest()

    // Act
    resp, err := server.Set(context.Background(), req)

    // Assert
    require.NoError(t, err)
    assert.True(t, resp.Success)

    // Verify key isolation
    isolatedKey := fmt.Sprintf("%s:%s:%s", req.OrganizationId, req.UserId, req.Key)
    // ... verify key exists with isolated prefix
}

// TestSet_EC001_EmptyKey tests EC-001
func TestSet_EC001_EmptyKey(t *testing.T) {
    // Arrange
    factory := &fixtures.TestDataFactory{}
    req := factory.MakeSetRequest(fixtures.WithKey(""))

    // Act
    _, err := server.Set(context.Background(), req)

    // Assert
    require.Error(t, err)
    assert.Contains(t, err.Error(), "InvalidArgument")
}
```

---

## Test Layer Hierarchy

| Layer | Build Tag | Dependencies | Purpose |
|-------|-----------|--------------|---------|
| Unit | `//go:build unit` | None (mocked) | Test business logic |
| Component | `//go:build component` | Mocked infra | Test service layer |
| Integration | `//go:build integration` | Real DB/Cache | Test data access |
| E2E | `//go:build e2e` | Running services | Test full flow |

### Running Tests by Layer

```bash
# Run unit tests only
go test -tags=unit ./...

# Run integration tests
go test -tags=integration ./...

# Run all tests
go test ./...

# Run specific service tests
go test -tags=unit ./cmd/redis-service/...

# Run with verbose output
go test -tags=unit -v ./...

# Run with coverage
go test -tags=unit -cover ./...
```

---

## Quick Reference

### Creating a New Service

```bash
# 1. Define Proto contract
cat > api/proto/{service}_service.proto << 'EOF'
syntax = "proto3";
package {service};
// ... define messages and service
EOF

# 2. Generate Go code
make proto-gen SERVICE={service}

# 3. Create logic contract
mkdir -p tests/contracts/{service}
touch tests/contracts/{service}/logic_contract.md
touch tests/contracts/{service}/fixtures.go

# 4. Create service structure
mkdir -p cmd/{service}-service/server
mkdir -p internal/{service}/{domain,repository,service,handler}

# 5. Implement following TDD
go test -tags=unit ./cmd/{service}-service/... -v
```

### Key Commands

```bash
# Generate proto
make proto-gen

# Run all tests
make test

# Run by layer
make test-unit
make test-integration
make test-e2e

# Run specific service
go test -tags=unit ./cmd/redis-service/... -v

# Check test coverage
make test-coverage
```

---

## Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| Domain | [docs/domain/README.md](domain/README.md) | Business context |
| PRD | [docs/prd/README.md](prd/README.md) | Requirements |
| Design | [docs/design/README.md](design/README.md) | Architecture |
| System Contract | [tests/contracts/shared_system_contract.md](../tests/contracts/shared_system_contract.md) | Test methodology |
| Go Dev Guide | [docs/GO_MICROSERVICE_DEVELOPMENT_GUIDE.md](GO_MICROSERVICE_DEVELOPMENT_GUIDE.md) | Implementation guide |

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
**Owner**: isA Cloud Team
