# ISA Common - Contract-Driven Development (CDD) Guide

**Complete CDD Architecture for Shared Infrastructure Clients**

This document provides an overview of the Contract-Driven Development approach for the `isa_common` library.

---

## What is Contract-Driven Development?

Contract-Driven Development (CDD) is a methodology where **contracts define behavior before implementation**. It combines:

- **Domain-Driven Design (DDD)**: Understanding the problem space
- **Test-Driven Development (TDD)**: Writing tests before code
- **Documentation-First**: Clear specifications before implementation

---

## The 6-Layer Contract Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CONTRACT-DRIVEN DEVELOPMENT                            │
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
│                        ┌──────────────────┐                                 │
│                        │       ENV        │                                 │
│                        │ (Configuration)  │                                 │
│                        │   docs/env/      │                                 │
│                        └────────┬─────────┘                                 │
│                                 │                                           │
│         ┌───────────────────────┴───────────────────────┐                   │
│         │                                               │                   │
│         ▼                                               ▼                   │
│  ┌──────────────┐                              ┌──────────────────┐         │
│  │    DATA      │                              │     LOGIC        │         │
│  │  CONTRACT    │                              │    CONTRACT      │         │
│  │   (Schemas)  │                              │  (Rules/Tests)   │         │
│  │ data_        │                              │ logic_           │         │
│  │ contract.py  │                              │ contract.md      │         │
│  └──────┬───────┘                              └────────┬─────────┘         │
│         │                                               │                   │
│         └───────────────────────┬───────────────────────┘                   │
│                                 │                                           │
│                                 ▼                                           │
│                        ┌──────────────────┐                                 │
│                        │     SYSTEM       │                                 │
│                        │    CONTRACT      │                                 │
│                        │ (How to Test)    │                                 │
│                        │ TDD_CONTRACT.md  │                                 │
│                        └────────┬─────────┘                                 │
│                                 │                                           │
│         ┌───────────────────────┴───────────────────────┐                   │
│         │                                               │                   │
│         ▼                                               ▼                   │
│  ┌──────────────┐                              ┌──────────────────┐         │
│  │   GOLDEN     │                              │      TDD         │         │
│  │    TESTS     │                              │     TESTS        │         │
│  │  (Current)   │                              │   (Expected)     │         │
│  └──────────────┘                              └──────────────────┘         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Contract Responsibilities

| Layer | Document | Purpose | Audience |
|-------|----------|---------|----------|
| **Domain** | `docs/domain/README.md` | Business context, taxonomy, scenarios | Everyone |
| **PRD** | `docs/prd/README.md` | User stories, requirements, acceptance criteria | Product, Dev |
| **Design** | `docs/design/README.md` | Architecture, data flow, API design | Engineering |
| **ENV** | `docs/env/README.md` | Environment configuration, mocking strategy | Testing |
| **Data Contract** | `tests/contracts/{svc}/data_contract.py` | Pydantic schemas, test factories | Testing |
| **Logic Contract** | `tests/contracts/{svc}/logic_contract.md` | Business rules, state machines | Testing |
| **System Contract** | `tests/TDD_CONTRACT.md` | How to test, environment setup | Testing |

---

## Directory Structure

```
isA_common/
├── docs/
│   ├── cdd_guide.md              # ← This file (CDD overview)
│   │
│   ├── domain/                    # Layer 1: Domain Context
│   │   └── README.md              # Taxonomy, business scenarios
│   │
│   ├── prd/                       # Layer 2: Requirements
│   │   └── README.md              # User stories, AC
│   │
│   ├── design/                    # Layer 3: Technical Design
│   │   └── README.md              # Architecture, data flow
│   │
│   └── env/                       # Layer 4: Environment
│       └── README.md              # Configuration, mocking
│
├── tests/
│   ├── TDD_CONTRACT.md            # Layer 5: System Contract (HOW to test)
│   │
│   ├── contracts/                 # Layer 6: Data + Logic Contracts
│   │   └── grpc_client/
│   │       ├── __init__.py
│   │       ├── data_contract.py   # Schemas, factories
│   │       └── logic_contract.md  # Business rules
│   │
│   ├── component/                 # Layer 7: Tests
│   │   ├── golden/                # Current behavior tests
│   │   │   └── test_async_base_client_golden.py
│   │   │
│   │   └── clients/               # TDD tests
│   │       └── grpc_client/
│   │           └── test_channel_health_tdd.py
│   │
│   └── integration/               # Real infrastructure tests
│       └── clients/
│
└── isa_common/                    # Implementation
    ├── async_base_client.py       # Base gRPC client
    ├── async_grpc_pool.py         # Channel pool
    └── ...
```

---

## Development Workflow

### For Bug Fixes (like "Channel is closed" error)

```
1. UNDERSTAND DOMAIN
   └── Read docs/domain/README.md
       └── Understand gRPC client architecture
       └── Learn about channel states

2. CHECK REQUIREMENTS
   └── Read docs/prd/README.md
       └── Find relevant user story (E2-US1: Channel Health Check)
       └── Check acceptance criteria

3. REVIEW DESIGN
   └── Read docs/design/README.md
       └── Understand _ensure_connected() flow
       └── Identify the fix location

4. CHECK ENV CONTRACT
   └── Read docs/env/README.md
       └── Understand test environment (KIND, port-forward)
       └── Understand why pip install -e won't work in Docker

5. WRITE GOLDEN TEST (CURRENT behavior)
   └── tests/component/golden/test_async_base_client_golden.py
       └── Document the BUG - doesn't check channel state
       └── This test PASSES with current (buggy) code

6. WRITE TDD TEST (EXPECTED behavior)
   └── tests/component/clients/grpc_client/test_channel_health_tdd.py
       └── Define CORRECT behavior per logic contract
       └── This test FAILS initially (RED)

7. FIX IMPLEMENTATION
   └── isa_common/async_base_client.py
       └── Add channel state check to _ensure_connected()
       └── TDD test passes (GREEN)

8. VERIFY ALL TESTS PASS
   └── pytest tests/component/ -v
       └── Both golden and TDD tests should pass

9. PUBLISH TO PYPI
   └── Version bump in pyproject.toml
   └── python -m build && twine upload dist/*
       └── Now Docker builds will get the fix
```

### For New Features

```
1. UNDERSTAND DOMAIN → 2. CREATE PRD STORY → 3. UPDATE DESIGN
       ↓
4. CREATE/UPDATE CONTRACTS
   └── Data Contract (if new schemas)
   └── Logic Contract (if new rules)
       ↓
5. WRITE TDD TESTS (failing)
       ↓
6. IMPLEMENT FEATURE
       ↓
7. TESTS PASS → 8. PUBLISH
```

---

## Key Insight: Why This Matters

### The Environment Contract Problem

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WHY pip install -e DOESN'T WORK FOR DOCKER                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  LOCAL DEVELOPMENT                                                          │
│  ┌─────────────────┐                                                        │
│  │ pip install -e  │ ◄── Editable install - changes take effect instantly  │
│  │ ./isa_common    │     BUT only on YOUR machine!                         │
│  └─────────────────┘                                                        │
│                                                                             │
│  DOCKER BUILD (Dockerfile.staging)                                          │
│  ┌─────────────────┐                                                        │
│  │ pip install     │ ◄── Pulls from PyPI                                   │
│  │ isa-common      │     Your local changes DON'T exist here!              │
│  └─────────────────┘                                                        │
│                                                                             │
│  CONCLUSION:                                                                │
│  ✗ Local editable install → Only affects local machine                     │
│  ✗ Rebuilding Docker → Still pulls OLD version from PyPI                   │
│  ✓ MUST publish to PyPI first → Then Docker gets the fix                   │
│                                                                             │
│  CORRECT WORKFLOW:                                                          │
│  1. Test locally with pytest (no Docker needed)                            │
│  2. All tests pass? → Publish to PyPI                                       │
│  3. Rebuild Docker → Now has the fix                                        │
│  4. Deploy and smoke test                                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Commands

```bash
# Run all component tests (no infrastructure needed)
cd /Users/xenodennis/Documents/Fun/isA_Cloud/isA_common
pytest tests/component/ -v

# Run only TDD tests
pytest tests/component/ -v -m tdd

# Run only golden tests
pytest tests/component/ -v -m golden

# Run specific client tests
pytest tests/component/clients/grpc_client/ -v

# Build and publish to PyPI (after tests pass)
python -m build
twine upload dist/*
```

---

## Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| Domain | [docs/domain/README.md](domain/README.md) | Business context |
| PRD | [docs/prd/README.md](prd/README.md) | Requirements |
| Design | [docs/design/README.md](design/README.md) | Architecture |
| ENV | [docs/env/README.md](env/README.md) | Configuration |
| System Contract | [tests/TDD_CONTRACT.md](../tests/TDD_CONTRACT.md) | Test methodology |
| Data Contract | [tests/contracts/grpc_client/data_contract.py](../tests/contracts/grpc_client/data_contract.py) | Test data |
| Logic Contract | [tests/contracts/grpc_client/logic_contract.md](../tests/contracts/grpc_client/logic_contract.md) | Business rules |

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
**Owner**: ISA Platform Team
