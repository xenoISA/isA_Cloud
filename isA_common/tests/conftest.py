"""
isa_common Test Configuration

Shared fixtures and configuration for all tests.
"""
import pytest
import asyncio
from typing import Generator


# ============================================================================
# Async Event Loop Configuration
# ============================================================================

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for session-scoped async fixtures."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Infrastructure Ports
# ============================================================================

class InfraConfig:
    """Infrastructure configuration for tests."""

    # gRPC service ports (via port-forward from K8s)
    POSTGRES_GRPC_PORT = 50061
    REDIS_GRPC_PORT = 50055
    NATS_GRPC_PORT = 50056
    MINIO_GRPC_PORT = 50051
    MQTT_GRPC_PORT = 50053
    QDRANT_GRPC_PORT = 50062
    NEO4J_GRPC_PORT = 50063
    DUCKDB_GRPC_PORT = 50052
    LOKI_GRPC_PORT = 50054

    # Default host
    DEFAULT_HOST = "localhost"


@pytest.fixture
def infra_config() -> InfraConfig:
    """Provide infrastructure configuration."""
    return InfraConfig()


# ============================================================================
# Skip Markers
# ============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "component: Component tests with mocked dependencies"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests with real infrastructure"
    )
    config.addinivalue_line(
        "markers", "golden: Golden tests capturing current behavior"
    )
    config.addinivalue_line(
        "markers", "tdd: TDD tests defining expected behavior"
    )
    config.addinivalue_line(
        "markers", "requires_infrastructure: Tests requiring gRPC infrastructure"
    )
