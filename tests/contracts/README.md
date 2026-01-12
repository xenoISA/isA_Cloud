# Test Contracts

> Contract definitions for isA Cloud Go services

---

## Overview

This directory contains test contracts that define the expected behavior of each service. Contracts serve as the source of truth for testing and documentation.

---

## Structure

```
tests/contracts/
├── README.md                      # This file
├── shared_system_contract.md      # Testing methodology (all services)
│
├── redis/                         # Redis service contracts
│   ├── logic_contract.md          # Business rules & edge cases
│   └── fixtures.go                # Test data factories
│
├── postgres/                      # PostgreSQL service contracts
│   ├── logic_contract.md
│   └── fixtures.go
│
├── nats/                          # NATS service contracts
│   ├── logic_contract.md
│   └── fixtures.go
│
├── minio/                         # MinIO service contracts
│   ├── logic_contract.md
│   └── fixtures.go
│
├── qdrant/                        # Qdrant service contracts
│   ├── logic_contract.md
│   └── fixtures.go
│
└── loki/                          # Loki service contracts
    ├── logic_contract.md
    └── fixtures.go
```

---

## Contract Types

### 1. Data Contracts (Proto)

Location: `api/proto/*.proto`

Protocol Buffer definitions serve as data contracts, defining:
- Message structures (request/response)
- Field types and validation
- Service methods (RPC definitions)

### 2. Logic Contracts

Location: `tests/contracts/{service}/logic_contract.md`

Markdown documents defining:
- **Business Rules (BR-XXX)**: Core business logic
- **Edge Cases (EC-XXX)**: Boundary conditions
- **Error Handling (ER-XXX)**: Error scenarios
- **State Machines**: Lifecycle diagrams

### 3. System Contract

Location: `tests/contracts/shared_system_contract.md`

Defines testing methodology:
- Test layer hierarchy (unit, component, integration, e2e)
- Naming conventions
- Mock patterns
- CI/CD integration

### 4. Test Fixtures

Location: `tests/contracts/{service}/fixtures.go`

Go code providing:
- Test data factories with defaults
- Functional options for customization
- Pre-built scenarios for common tests
- Assertion helpers

---

## Quick Reference

### Creating Tests for a Business Rule

1. Find the rule in `logic_contract.md`:
   ```markdown
   ### BR-001: Multi-Tenant Key Isolation
   ```

2. Import fixtures:
   ```go
   import fixtures "github.com/isa-cloud/isa_cloud/tests/contracts/redis"
   ```

3. Create test using rule ID:
   ```go
   func TestSet_BR001_MultiTenantKeyIsolation(t *testing.T) {
       factory := fixtures.NewTestDataFactory()
       req := factory.MakeSetRequest()
       // ... test implementation
   }
   ```

### Using Fixtures

```go
// Default request
req := factory.MakeSetRequest()

// Customized request
req := factory.MakeSetRequest(
    fixtures.WithKey("custom-key"),
    fixtures.WithTTL(3600),
    fixtures.WithUser("user-002", "org-002"),
)

// Pre-built scenario
scenarios := fixtures.NewScenarios()
req := scenarios.SetRequestEmptyKey()  // For EC-001
```

### Running Contract Tests

```bash
# All contract-related tests
go test -tags=unit ./tests/...

# Specific service
go test -tags=unit ./tests/contracts/redis/...

# By rule ID
go test -tags=unit -run "BR001" ./...
```

---

## Adding a New Service Contract

1. Create directory:
   ```bash
   mkdir -p tests/contracts/{service}
   ```

2. Create logic contract:
   ```bash
   touch tests/contracts/{service}/logic_contract.md
   ```

3. Create fixtures:
   ```bash
   touch tests/contracts/{service}/fixtures.go
   ```

4. Define business rules in `logic_contract.md`

5. Implement fixtures following the pattern in `redis/fixtures.go`

---

## Contract Status

| Service | Logic Contract | Fixtures | Unit Tests | Integration Tests | API Tests | Smoke Tests |
|---------|---------------|----------|------------|-------------------|-----------|-------------|
| Redis | Done | Done | Done | Done | Done | Done |
| PostgreSQL | Done | Done | Done | Done | Planned | Done |
| NATS | Done | Done | Done | Done | Planned | Done |
| MinIO | Done | Done | Done | Done | Planned | Done |
| Qdrant | Done | Done | Done | Done | Planned | Done |
| MQTT | Done | Done | Done | Done | Planned | Done |
| Neo4j | Done | Done | Done | Done | Planned | Done |
| DuckDB | Done | Done | Done | Done | Planned | Done |

---

## Test Layers

### 4-Layer Test Pyramid

```
tests/
├── unit/golden/           # Unit tests - Business logic, no I/O
│   ├── redis_test.go
│   ├── postgres_test.go
│   ├── nats_test.go
│   ├── minio_test.go
│   ├── qdrant_test.go
│   ├── mqtt_test.go
│   ├── neo4j_test.go
│   └── duckdb_test.go
│
├── integration/golden/    # Integration tests - Mocked dependencies
│   ├── redis_integration_test.go
│   ├── postgres_integration_test.go
│   ├── nats_integration_test.go
│   ├── minio_integration_test.go
│   ├── qdrant_integration_test.go
│   ├── mqtt_integration_test.go
│   ├── neo4j_integration_test.go
│   └── duckdb_integration_test.go
│
├── api/golden/            # API tests - Real gRPC endpoints
│   └── redis_api_test.go
│
└── smoke/                 # E2E smoke tests - Bash scripts
    ├── run_all_smoke_tests.sh   # Master runner
    ├── redis_e2e.sh
    ├── postgres_e2e.sh
    ├── nats_e2e.sh
    ├── minio_e2e.sh
    ├── qdrant_e2e.sh
    ├── mqtt_e2e.sh
    ├── neo4j_e2e.sh
    └── duckdb_e2e.sh
```

### Running Tests

```bash
# Unit tests (no I/O, fast)
go test -v -tags=unit ./tests/unit/golden/...

# Integration tests (mocked dependencies)
go test -v -tags=integration ./tests/integration/golden/...

# API tests (requires running services)
go test -v -tags=api ./tests/api/golden/...

# Smoke tests (E2E bash scripts)
./tests/smoke/run_all_smoke_tests.sh

# Single service smoke test
./tests/smoke/redis_e2e.sh localhost:50051
```

---

## Related Documents

- [CDD Guide](../../docs/cdd_guide.md) - Contract-Driven Development overview
- [Domain](../../docs/domain/README.md) - Business context
- [PRD](../../docs/prd/README.md) - Product requirements
- [Design](../../docs/design/README.md) - Technical architecture

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
