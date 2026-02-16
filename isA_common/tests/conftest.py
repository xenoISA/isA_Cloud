"""
isa_common Test Configuration

Shared fixtures and configuration for all tests.
"""
import pytest
import asyncio
import socket
import os
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
    config.addinivalue_line(
        "markers", "requires_redis: Tests requiring Redis connection"
    )
    config.addinivalue_line(
        "markers", "requires_postgres: Tests requiring PostgreSQL connection"
    )
    config.addinivalue_line(
        "markers", "requires_neo4j: Tests requiring Neo4j connection"
    )
    config.addinivalue_line(
        "markers", "requires_nats: Tests requiring NATS connection"
    )
    config.addinivalue_line(
        "markers", "requires_minio: Tests requiring MinIO/S3 connection"
    )
    config.addinivalue_line(
        "markers", "requires_qdrant: Tests requiring Qdrant connection"
    )
    config.addinivalue_line(
        "markers", "requires_mqtt: Tests requiring MQTT broker"
    )
    config.addinivalue_line(
        "markers", "requires_duckdb: Tests requiring DuckDB"
    )
    config.addinivalue_line(
        "markers", "requires_consul: Tests requiring Consul connection"
    )


# ============================================================================
# Infrastructure Availability Checks
# ============================================================================

def _check_port(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a port is open on a host."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


# Infrastructure service ports and environment variable overrides
INFRASTRUCTURE_SERVICES = {
    "redis": {"port": 6379, "env": "REDIS_HOST"},
    "postgres": {"port": 5432, "env": "POSTGRES_HOST"},
    "neo4j": {"port": 7687, "env": "NEO4J_HOST"},
    "nats": {"port": 4222, "env": "NATS_HOST"},
    "minio": {"port": 9000, "env": "MINIO_HOST"},
    "qdrant": {"port": 6333, "env": "QDRANT_HOST"},
    "mqtt": {"port": 1883, "env": "MQTT_HOST"},
    "consul": {"port": 8500, "env": "CONSUL_HOST"},
}


def _is_service_available(service: str) -> bool:
    """Check if an infrastructure service is available."""
    if service not in INFRASTRUCTURE_SERVICES:
        return False

    config = INFRASTRUCTURE_SERVICES[service]
    host = os.environ.get(config["env"], "localhost")
    return _check_port(host, config["port"])


# Cache availability results for the session
_availability_cache: dict[str, bool] = {}


def pytest_runtest_setup(item):
    """Auto-skip tests based on infrastructure availability markers."""
    for marker in item.iter_markers():
        if marker.name.startswith("requires_"):
            service = marker.name.replace("requires_", "")

            # Check cache first
            if service not in _availability_cache:
                _availability_cache[service] = _is_service_available(service)

            if not _availability_cache[service]:
                pytest.skip(f"{service} is not available (use {INFRASTRUCTURE_SERVICES.get(service, {}).get('env', 'HOST')} env var to configure)")


# ============================================================================
# Infrastructure Fixtures (for tests that need connections)
# ============================================================================

@pytest.fixture
def redis_available() -> bool:
    """Check if Redis is available."""
    return _is_service_available("redis")


@pytest.fixture
def postgres_available() -> bool:
    """Check if PostgreSQL is available."""
    return _is_service_available("postgres")


@pytest.fixture
def neo4j_available() -> bool:
    """Check if Neo4j is available."""
    return _is_service_available("neo4j")


@pytest.fixture
def nats_available() -> bool:
    """Check if NATS is available."""
    return _is_service_available("nats")
