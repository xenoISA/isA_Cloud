# isA_Cloud (Go gRPC Services) - CDD Progress Tracker

## Overview

Go gRPC infrastructure services providing backend infrastructure access (Redis, PostgreSQL, NATS, MQTT, MinIO, Neo4j, Qdrant, DuckDB).

**Reference Documents**:
- `docs/cdd_guide.md` - CDD methodology for Go services
- `tests/contracts/shared_system_contract.md` - System contract (HOW to test)
- `docs/GO_MICROSERVICE_DEVELOPMENT_GUIDE.md` - Implementation guide

---

## Progress Summary

| Category | Complete | Partial | Missing |
|----------|----------|---------|---------|
| Logic Contracts | 8/8 | 0 | 0 |
| Fixtures (Go) | 8/8 | 0 | 0 |
| Unit Golden Tests | 8/8 | 0 | 0 |
| Integration Golden Tests | 8/8 | 0 | 0 |
| API Tests | 8/8 | 0 | 0 |
| Smoke Tests (E2E) | 8/8 | 0 | 0 |
| System Contract | 1/1 | 0 | 0 |

**Last Updated**: 2025-12-17

---

## Test Layer Targets (per CDD Guide)

| Layer | Build Tag | Dependencies | Status |
|-------|-----------|--------------|--------|
| Unit | `//go:build unit` | None (mocked) | 8/8 services |
| Component | `//go:build component` | Mocked infra | 0/8 services |
| Integration | `//go:build integration` | Real DB/Cache | 8/8 services |
| E2E/Smoke | Bash scripts | Running services | 8/8 services |

---

## Detailed Service Status

| Service | Logic Contract | Fixtures | Unit | Integration | API | Smoke | Status |
|---------|:--------------:|:--------:|:----:|:-----------:|:---:|:-----:|:------:|
| **redis** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **postgres** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **nats** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **mqtt** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **minio** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **neo4j** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **qdrant** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **duckdb** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Directory Structure

```
isA_Cloud/
├── tests/
│   ├── contracts/
│   │   ├── README.md
│   │   ├── shared_system_contract.md    # System Contract
│   │   ├── redis/
│   │   │   ├── logic_contract.md        # Logic Contract
│   │   │   └── fixtures.go              # Test Factories
│   │   ├── postgres/
│   │   ├── nats/
│   │   ├── mqtt/
│   │   ├── minio/
│   │   ├── neo4j/
│   │   ├── qdrant/
│   │   └── duckdb/
│   │
│   ├── unit/golden/                     # Unit Tests
│   │   ├── redis_test.go
│   │   ├── postgres_test.go
│   │   └── ...
│   │
│   ├── integration/golden/              # Integration Tests
│   │   ├── redis_integration_test.go
│   │   ├── postgres_integration_test.go
│   │   └── ...
│   │
│   ├── api/golden/                      # API Tests (all 8 services)
│   │   ├── redis_api_test.go
│   │   ├── postgres_api_test.go
│   │   ├── nats_api_test.go
│   │   ├── mqtt_api_test.go
│   │   ├── minio_api_test.go
│   │   ├── neo4j_api_test.go
│   │   ├── qdrant_api_test.go
│   │   └── duckdb_api_test.go
│   │
│   └── smoke/                           # E2E Smoke Tests
│       ├── run_all_smoke_tests.sh
│       ├── redis_e2e.sh
│       ├── postgres_e2e.sh
│       └── ...
```

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Complete and verified |
| ⚠️ | Partially complete |
| ❌ | Missing |

---

## Next Priority

1. **Component Tests** - Add component layer tests with mocked infrastructure
2. **TDD Tests** - Add TDD tests for bug fixes and new features
3. **Contract Test Coverage** - Expand test scenarios per logic contracts

---

## Running Tests

```bash
# Run unit tests only
go test -tags=unit ./tests/unit/...

# Run integration tests (requires port-forward)
go test -tags=integration ./tests/integration/...

# Run API tests (requires port-forward)
go test -v -tags=api ./tests/api/golden/... -timeout 300s

# Run API health checks only
go test -v -tags=api ./tests/api/golden/... -run "HealthCheck"

# Run specific service API tests
go test -v -tags=api ./tests/api/golden/... -run "TestRedis"
go test -v -tags=api ./tests/api/golden/... -run "TestQdrant"

# Run all smoke tests
./tests/smoke/run_all_smoke_tests.sh

# Run specific service smoke test
./tests/smoke/redis_e2e.sh
```

## API Test Port Configuration

| Service | gRPC Port | Environment Variable |
|---------|-----------|---------------------|
| MinIO | 50051 | MINIO_GRPC_ADDR |
| DuckDB | 50052 | DUCKDB_GRPC_ADDR |
| MQTT | 50053 | MQTT_GRPC_ADDR |
| Loki | 50054 | LOKI_GRPC_ADDR |
| Redis | 50055 | REDIS_GRPC_ADDR |
| NATS | 50056 | NATS_GRPC_ADDR |
| PostgreSQL | 50061 | POSTGRES_GRPC_ADDR |
| Qdrant | 50062 | QDRANT_GRPC_ADDR |
| Neo4j | 50063 | NEO4J_GRPC_ADDR |
