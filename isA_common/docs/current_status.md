# isa-common (Python Library) - CDD Progress Tracker

## Overview

Python shared library providing async gRPC clients for all infrastructure services.

**PyPI**: `isa-common` v0.2.1
**Install**: `pip install isa-common==0.2.1`

**Reference Documents**:
- `tests/TDD_CONTRACT.md` - System contract (HOW to test)
- `tests/contracts/README.md` - Contract architecture overview
- `docs/cdd_guide.md` - CDD methodology for Python library

---

## Progress Summary

| Category | Complete | Partial | Missing |
|----------|----------|---------|---------|
| PyPI Published | ✅ v0.2.1 | - | - |
| System Contract | ✅ | - | - |
| Data Contracts | 1/9 | 0 | 8 |
| Logic Contracts | 1/9 | 0 | 8 |
| Component Golden Tests | 1/9 | 0 | 8 |
| Component TDD Tests | 1/9 | 0 | 8 |
| Integration Tests | 0/9 | 8 | 1 |

**Last Updated**: 2025-12-16

---

## Test Layer Targets (per TDD_CONTRACT.md)

| Layer | Marker | Dependencies | Status |
|-------|--------|--------------|--------|
| Component Golden | `@pytest.mark.component @pytest.mark.golden` | None (mocked) | 1/9 |
| Component TDD | `@pytest.mark.component @pytest.mark.tdd` | None (mocked) | 1/9 |
| Integration Golden | `@pytest.mark.integration @pytest.mark.golden` | Real gRPC | 0/9 |
| Integration TDD | `@pytest.mark.integration @pytest.mark.tdd` | Real gRPC | 0/9 |

---

## Detailed Client Status

| Client | Data Contract | Logic Contract | Comp Golden | Comp TDD | Integ | Status |
|--------|:-------------:|:--------------:|:-----------:|:--------:|:-----:|:------:|
| **grpc_client (base)** | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| async_redis_client | ❌ | ❌ | ❌ | ❌ | ⚠️ | ❌ |
| async_postgres_client | ❌ | ❌ | ❌ | ❌ | ⚠️ | ❌ |
| async_nats_client | ❌ | ❌ | ❌ | ❌ | ⚠️ | ❌ |
| async_mqtt_client | ❌ | ❌ | ❌ | ❌ | ⚠️ | ❌ |
| async_minio_client | ❌ | ❌ | ❌ | ❌ | ⚠️ | ❌ |
| async_neo4j_client | ❌ | ❌ | ❌ | ❌ | ⚠️ | ❌ |
| async_qdrant_client | ❌ | ❌ | ❌ | ❌ | ⚠️ | ❌ |
| async_duckdb_client | ❌ | ❌ | ❌ | ❌ | ⚠️ | ❌ |

**Note**: ⚠️ in Integ column means basic test files exist but not following CDD structure.

---

## Directory Structure (Current)

```
isA_common/
├── tests/
│   ├── TDD_CONTRACT.md                  # System Contract
│   ├── conftest.py                      # Shared fixtures
│   ├── pytest.ini                       # Pytest config
│   │
│   ├── contracts/
│   │   ├── README.md
│   │   └── grpc_client/                 # Only this one complete
│   │       ├── __init__.py
│   │       ├── data_contract.py         # Channel states, mocks
│   │       └── logic_contract.md        # Business rules
│   │
│   ├── component/
│   │   ├── golden/
│   │   │   └── test_async_base_client_golden.py
│   │   └── clients/
│   │       └── grpc_client/
│   │           └── test_channel_health_tdd.py
│   │
│   └── {client}/                        # Legacy test structure
│       ├── redis/test_async_redis.py
│       ├── postgres/test_async_postgres.py
│       └── ...
```

---

## Directory Structure (Target)

```
isA_common/
├── tests/
│   ├── TDD_CONTRACT.md
│   ├── conftest.py
│   ├── pytest.ini
│   │
│   ├── contracts/
│   │   ├── README.md
│   │   ├── grpc_client/                 # ✅ Complete
│   │   ├── redis/                       # ❌ Need to create
│   │   │   ├── data_contract.py
│   │   │   └── logic_contract.md
│   │   ├── postgres/                    # ❌ Need to create
│   │   ├── nats/
│   │   ├── mqtt/
│   │   ├── minio/
│   │   ├── neo4j/
│   │   ├── qdrant/
│   │   └── duckdb/
│   │
│   ├── component/
│   │   ├── golden/
│   │   │   ├── test_async_base_client_golden.py  # ✅
│   │   │   ├── test_redis_client_golden.py       # ❌
│   │   │   └── ...
│   │   └── clients/
│   │       ├── grpc_client/             # ✅
│   │       ├── redis/                   # ❌
│   │       └── ...
│   │
│   └── integration/
│       ├── golden/
│       └── clients/
```

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Complete and verified |
| ⚠️ | Exists but not CDD-compliant |
| ❌ | Missing |

---

## Next Priority

1. **Redis Client Contracts** - Create data_contract.py + logic_contract.md
2. **Redis Component Tests** - Golden + TDD tests with mocked gRPC
3. **Postgres Client Contracts** - Same pattern
4. **Repeat for remaining 6 clients**

---

## Running Tests

```bash
# Run all component tests
pytest -m component tests/component/

# Run only golden tests
pytest -m "component and golden" tests/component/

# Run only TDD tests
pytest -m "component and tdd" tests/component/

# Run integration tests (requires port-forward)
pytest -m integration tests/integration/
```

---

## Port Registry (for Integration Tests)

| Service | gRPC Port |
|---------|-----------|
| PostgreSQL | localhost:50061 |
| Redis | localhost:50055 |
| NATS | localhost:50056 |
| MinIO | localhost:50051 |
| MQTT | localhost:50053 |
| Qdrant | localhost:50062 |
| Neo4j | localhost:50063 |
| DuckDB | localhost:50052 |
