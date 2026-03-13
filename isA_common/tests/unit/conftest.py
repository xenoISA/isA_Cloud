"""
Unit test fixtures — all tests use mocked backends, no infrastructure required.
"""
import logging
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ============================================================================
# Redis
# ============================================================================

@pytest_asyncio.fixture
async def redis_client():
    """AsyncRedisClient with mocked redis driver."""
    from isa_common import AsyncRedisClient

    client = AsyncRedisClient(
        host="localhost", port=6379,
        user_id="test_user", organization_id="org1",
        lazy_connect=True,
    )
    client._client = AsyncMock()
    client._pool = AsyncMock()  # pool.disconnect() is awaited
    client._connected = True
    yield client
    client._connected = False


# ============================================================================
# PostgreSQL
# ============================================================================

@pytest_asyncio.fixture
async def postgres_client():
    """AsyncPostgresClient with mocked asyncpg pool."""
    from isa_common import AsyncPostgresClient

    client = AsyncPostgresClient(
        host="localhost", port=5432, database="testdb",
        user_id="test_user", organization_id="org1",
        lazy_connect=True,
    )
    # asyncpg pool.acquire() is a sync call returning an async context manager
    mock_conn = AsyncMock()
    mock_acquire_cm = MagicMock()
    mock_acquire_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire_cm.__aexit__ = AsyncMock(return_value=None)

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_acquire_cm
    mock_pool.get_size.return_value = 5
    mock_pool.get_idle_size.return_value = 3
    mock_pool.close = AsyncMock()

    client._pool = mock_pool
    client._conn = mock_conn  # convenience ref for tests
    client._connected = True
    yield client
    client._connected = False


# ============================================================================
# Neo4j
# ============================================================================

@pytest_asyncio.fixture
async def neo4j_client():
    """AsyncNeo4jClient with mocked neo4j driver."""
    import isa_common.async_neo4j_client as neo4j_module

    # Patch missing module-level logger
    if not hasattr(neo4j_module, 'logger'):
        neo4j_module.logger = logging.getLogger('test_neo4j')

    from isa_common import AsyncNeo4jClient

    client = AsyncNeo4jClient(
        host="localhost", port=7687,
        user_id="test_user", organization_id="org1",
        lazy_connect=True,
    )
    # driver.session() is a sync call returning a session with async methods
    mock_session = AsyncMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session
    mock_driver.close = AsyncMock()

    client._driver = mock_driver
    client._session = mock_session  # convenience ref
    client._connected = True
    yield client
    client._connected = False


# ============================================================================
# MinIO
# ============================================================================

@pytest_asyncio.fixture
async def minio_client():
    """AsyncMinIOClient with mocked aioboto3 session."""
    from isa_common import AsyncMinIOClient

    client = AsyncMinIOClient(
        host="localhost", port=9000,
        user_id="test_user", organization_id="org1",
        lazy_connect=True,
    )
    client._session = MagicMock()
    client._connected = True
    yield client
    client._connected = False


# ============================================================================
# Qdrant
# ============================================================================

@pytest_asyncio.fixture
async def qdrant_client():
    """AsyncQdrantClient with mocked qdrant-client."""
    from isa_common import AsyncQdrantClient

    client = AsyncQdrantClient(
        host="localhost", port=6333,
        user_id="test_user", organization_id="org1",
        lazy_connect=True,
    )
    client._client = AsyncMock()
    client._connected = True
    yield client
    client._connected = False


# ============================================================================
# DuckDB
# ============================================================================

@pytest_asyncio.fixture
async def duckdb_client():
    """AsyncDuckDBClient with mocked duckdb connection."""
    from isa_common import AsyncDuckDBClient

    client = AsyncDuckDBClient(
        user_id="test_user", organization_id="org1",
        lazy_connect=True,
    )
    client._conn = MagicMock()
    client._connected = True
    yield client
    client._connected = False


# ============================================================================
# MQTT
# ============================================================================

@pytest_asyncio.fixture
async def mqtt_client():
    """AsyncMQTTClient with mocked state."""
    from isa_common import AsyncMQTTClient

    client = AsyncMQTTClient(
        host="localhost", port=1883,
        user_id="test_user", organization_id="org1",
        lazy_connect=True,
    )
    client._connected = True
    yield client
    client._connected = False


# ============================================================================
# Loki
# ============================================================================

@pytest_asyncio.fixture
async def loki_client():
    """AsyncLokiClient with mocked aiohttp session."""
    from isa_common import AsyncLokiClient

    client = AsyncLokiClient(
        host="localhost", port=3100,
        user_id="test_user", organization_id="org1",
        default_labels={"app": "test-service", "env": "test"},
        lazy_connect=True,
    )
    client._session = AsyncMock()
    client._connected = True
    yield client
    client._batch = []
    client._connected = False


# ============================================================================
# SQLite
# ============================================================================

@pytest_asyncio.fixture
async def sqlite_client(tmp_path):
    """AsyncSQLiteClient with a real temp database (no external deps)."""
    from isa_common import AsyncSQLiteClient

    client = AsyncSQLiteClient(
        database="test.db",
        db_path=str(tmp_path),
        user_id="test_user", organization_id="org1",
        lazy_connect=True,
    )
    # Mock _conn so tests don't need aiosqlite
    client._conn = AsyncMock()
    client._connected = True
    yield client
    client._connected = False


# ============================================================================
# LocalStorage
# ============================================================================

@pytest_asyncio.fixture
async def local_storage_client(tmp_path):
    """AsyncLocalStorageClient with a real temp directory."""
    from isa_common import AsyncLocalStorageClient

    client = AsyncLocalStorageClient(
        base_path=str(tmp_path),
        user_id="test_user", organization_id="org1",
        lazy_connect=True,
    )
    client._connected = True
    yield client
    client._connected = False


# ============================================================================
# ChromaDB
# ============================================================================

@pytest_asyncio.fixture
async def chroma_client(tmp_path):
    """AsyncChromaClient with mocked chromadb backend."""
    from isa_common import AsyncChromaClient

    client = AsyncChromaClient(
        persist_directory=str(tmp_path),
        user_id="test_user", organization_id="org1",
        lazy_connect=True,
    )
    client._client = MagicMock()
    client._connected = True
    yield client
    client._connected = False


# ============================================================================
# Memory (In-memory cache)
# ============================================================================

@pytest_asyncio.fixture
async def memory_client():
    """AsyncMemoryClient with instance-local store (no global bleed)."""
    from isa_common import AsyncMemoryClient

    client = AsyncMemoryClient(
        use_global_store=False,
        user_id="test_user", organization_id="org1",
        lazy_connect=True,
    )
    client._connected = True
    yield client
    client._store.clear()
    client._expiry.clear()
    client._connected = False


# ============================================================================
# Consul
# ============================================================================

@pytest.fixture
def consul_registry():
    """ConsulRegistry with mocked consul backend."""
    from isa_common.consul_client import ConsulRegistry

    with patch("isa_common.consul_client.consul.Consul") as MockConsul:
        mock_consul = MagicMock()
        MockConsul.return_value = mock_consul
        registry = ConsulRegistry(
            service_name="test-service",
            service_port=8080,
            consul_host="localhost",
            consul_port=8500,
        )
        registry.consul = mock_consul
        yield registry


# ============================================================================
# AsyncConsulRegistry
# ============================================================================

@pytest_asyncio.fixture
async def async_consul_registry():
    """AsyncConsulRegistry with mocked consul backend."""
    from isa_common.consul_client import AsyncConsulRegistry

    with patch("isa_common.consul_client.consul.Consul") as MockConsul:
        mock_consul = MagicMock()
        MockConsul.return_value = mock_consul
        registry = AsyncConsulRegistry(
            service_name="test-service",
            service_port=8080,
            consul_host="localhost",
            consul_port=8500,
            lazy_connect=True,
        )
        registry._consul = mock_consul
        registry._connected = True
        yield registry
        registry._connected = False
