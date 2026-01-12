# TDD Contract & Checklist for isa_common

**Enforcement guide for creating consistent, high-quality tests for shared gRPC clients**

---

## Overview

This document serves as a **binding contract** for all developers testing the `isa_common` shared library. This library provides async gRPC clients for all infrastructure services (Qdrant, PostgreSQL, Redis, NATS, MinIO, etc.).

---

## Test Layer Structure

Since `isa_common` is a **shared library** (not a microservice), we use a modified test layer structure:

```
tests/
├── TDD_CONTRACT.md                    # System Contract (HOW to test)
│
├── contracts/                         # Data + Logic Contracts
│   ├── README.md
│   ├── grpc_client/                   # gRPC client contracts
│   │   ├── __init__.py
│   │   ├── data_contract.py           # Data schemas and factories
│   │   └── logic_contract.md          # Business rules and behavior
│   │
│   └── {client}/                      # Per-client contracts
│       ├── data_contract.py
│       └── logic_contract.md
│
├── component/                         # Unit-like tests with mocked dependencies
│   ├── golden/                        # Capture CURRENT behavior
│   │   └── test_async_base_client_golden.py
│   │
│   └── clients/                       # TDD tests for fixes/features
│       ├── grpc_client/
│       │   └── test_channel_health_tdd.py
│       └── qdrant/
│           └── test_qdrant_client_tdd.py
│
├── integration/                       # Tests against real infrastructure
│   ├── golden/
│   │   └── test_qdrant_integration_golden.py
│   │
│   └── clients/
│       ├── qdrant/
│       │   └── test_qdrant_crud_integration.py
│       └── postgres/
│           └── test_postgres_crud_integration.py
│
├── conftest.py                        # Shared fixtures
└── pytest.ini                         # Pytest configuration
```

---

## Golden vs TDD Workflow

### For Existing Clients (e.g., AsyncQdrantClient)

```
1. Write GOLDEN tests first to capture CURRENT behavior
   Location: tests/component/golden/test_{client}_golden.py
   Purpose: Document how it ACTUALLY works NOW

2. IF gotchas/bugs found:
   - Create TDD tests to define CORRECT behavior
   - Location: tests/component/clients/{client}/test_{feature}_tdd.py
   - Write RED test → Fix implementation → GREEN

3. Keep both:
   - Golden tests: baseline (update when intentional changes)
   - TDD tests: bug fixes and new features
```

### For New Clients

```
1. Start with TDD directly
   Location: tests/component/clients/{client}/test_{client}_tdd.py
   Purpose: Define behavior BEFORE implementation
```

---

## Pytest Markers

```python
# Component tests (mocked dependencies)
@pytest.mark.component
@pytest.mark.golden  # or @pytest.mark.tdd
@pytest.mark.asyncio

# Integration tests (real infrastructure)
@pytest.mark.integration
@pytest.mark.golden  # or @pytest.mark.tdd
@pytest.mark.asyncio
@pytest.mark.requires_infrastructure  # Requires gRPC services
```

---

## Infrastructure Requirements

### Component Tests
- **Dependencies**: NONE (all mocked)
- **Can run**: Anywhere, anytime

### Integration Tests
- **Dependencies**: Real gRPC infrastructure via port-forward
- **Port Registry**:
  ```
  PostgreSQL gRPC: localhost:50061
  Redis gRPC:      localhost:50055
  NATS gRPC:       localhost:50056
  MinIO gRPC:      localhost:50051
  MQTT gRPC:       localhost:50053
  Qdrant gRPC:     localhost:50062
  Neo4j gRPC:      localhost:50063
  DuckDB gRPC:     localhost:50052
  ```

---

## Validation Checklist

Before submitting PR with new tests:

- [ ] Follows directory structure from this contract
- [ ] Uses correct pytest markers
- [ ] Imports from centralized contracts (`tests/contracts/`)
- [ ] Has proper cleanup fixtures
- [ ] Documents infrastructure requirements
- [ ] Golden tests capture CURRENT behavior (not ideal behavior)
- [ ] TDD tests define EXPECTED behavior (may fail initially)

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
