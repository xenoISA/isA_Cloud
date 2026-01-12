# Test Contracts Architecture for isa_common

**3-Contract Driven Development for Shared gRPC Clients**

This directory contains the **Data Contracts** and **Logic Contracts** for all gRPC clients. Together with the **System Contract** (`tests/TDD_CONTRACT.md`), these form the complete testing specification.

---

## The 3-Contract Architecture

### 1. System Contract (Shared) - `tests/TDD_CONTRACT.md`
**Defines HOW to test**
- Test layer structure
- Directory conventions
- Pytest markers and fixtures
- Golden vs TDD workflow

### 2. Data Contract (Per Client) - `data_contract.py`
**Defines WHAT data structures to test**
- Channel states and enums
- Mock factories for channels/pools
- Test data generators
- Test scenarios

### 3. Logic Contract (Per Client) - `logic_contract.md`
**Defines WHAT business rules to test**
- Business rules (BR-001, BR-002, ...)
- State machines
- Error handling rules
- Performance SLAs
- Edge cases

---

## Directory Structure

```
tests/contracts/
├── README.md                         # This file
│
├── grpc_client/                      # Core gRPC client contracts
│   ├── __init__.py
│   ├── data_contract.py              # Channel states, mocks, factories
│   └── logic_contract.md             # Connection pool rules, health checking
│
└── {client}/                         # Per-client contracts (as needed)
    ├── data_contract.py
    └── logic_contract.md
```

---

## Usage

### In Tests

```python
from tests.contracts.grpc_client import (
    ChannelState,
    HEALTHY_STATES,
    UNHEALTHY_STATES,
    MockChannelFactory,
    CHANNEL_HEALTH_SCENARIOS,
)

# Use factory to create mock channel
channel = MockChannelFactory.create_channel(ChannelState.SHUTDOWN)

# Parametrize with scenarios
@pytest.mark.parametrize("scenario", CHANNEL_HEALTH_SCENARIOS)
async def test_channel_health(scenario):
    if scenario.initial_state in UNHEALTHY_STATES:
        assert scenario.should_reconnect is True
```

---

## Current Contracts

| Client | Logic Contract | Data Contract | Status |
|--------|---------------|---------------|--------|
| grpc_client | `grpc_client/logic_contract.md` | `grpc_client/data_contract.py` | Active |

---

**Version**: 1.0.0
**Last Updated**: 2025-12-11
