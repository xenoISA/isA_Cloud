#!/usr/bin/env python3
"""
isa-common: Native Async Clients for isA Platform

Version 0.3.1 - Refactored with AsyncBaseClient

Native async clients connect directly to infrastructure services:
- AsyncPostgresClient (asyncpg) - port 5432
- AsyncRedisClient (redis-py async) - port 6379
- AsyncNeo4jClient (neo4j driver) - port 7687
- AsyncNATSClient (nats-py) - port 4222
- AsyncQdrantClient (qdrant-client) - port 6333
- AsyncFalkorClient (falkordb) - port 6379 (Redis-module graph DB)
- AsyncMQTTClient (aiomqtt) - port 1883
- AsyncMinIOClient (aioboto3) - port 9000
- AsyncDuckDBClient (duckdb) - embedded

All clients extend AsyncBaseClient for consistent interface.

Usage:
    from isa_common import AsyncPostgresClient, AsyncRedisClient

    # Create client with native connection
    async with AsyncPostgresClient(host='localhost', port=5432, database='mydb') as pg:
        result = await pg.query("SELECT * FROM users")
"""

from typing import Dict

# =============================================================================
# Base Client & Configuration
# =============================================================================
from .async_base_client import AsyncBaseClient
from .async_client_config import (
    ClientConfig,
    LokiConfig,
    MinIOConfig,
    PostgresConfig,
    RedisConfig,
)
from .async_duckdb_client import AsyncDuckDBClient
from .async_falkor_client import AsyncFalkorClient
from .async_loki_client import AsyncLokiClient
from .async_minio_client import AsyncMinIOClient
from .async_mqtt_client import AsyncMQTTClient
from .async_nats_client import AsyncNATSClient
from .async_neo4j_client import AsyncNeo4jClient
from .async_postgres_client import AsyncPostgresClient
from .async_qdrant_client import AsyncQdrantClient

# =============================================================================
# Native Async Clients (Direct Connections)
# =============================================================================
from .async_redis_client import AsyncRedisClient

# =============================================================================
# Brand (white-label "brand as config" contract)
# =============================================================================
from .brand import BrandConfig, get_brand

# =============================================================================
# Edition (runtime "which edition + which features" contract — ADR 0006)
# =============================================================================
from .edition import EditionConfig, EditionType, get_edition

# =============================================================================
# License (offline ed25519-signed entitlement contract — ADR 0008)
# =============================================================================
from .license import LicenseConfig, LicenseStatus, get_license
from .licensing import (
    LicenseError,
    add_license_middleware,
    setup_licensing,
)
from .loki_handler import LokiHandler, setup_loki_logging

# =============================================================================
# Observability (Metrics, Tracing, Unified Setup)
# =============================================================================
from .metrics import (
    create_counter,
    create_gauge,
    create_histogram,
    metrics_text,
    setup_metrics,
)
from .observability import setup_observability

# =============================================================================
# Plugin / Extension SDK (ADR 0006)
# =============================================================================
from .plugin import (
    PluginKind,
    PluginManifest,
    PluginServiceRegistry,
    ServiceBinding,
    load_manifest,
)
from .tracing import get_tracer, setup_tracing

# =============================================================================
# Local-Mode Alternative Clients (ICP/Desktop — no infrastructure required)
# =============================================================================
# Keep isa_common importable in lean producer runtimes even when local-mode
# optional dependencies are not installed.
try:
    from .async_sqlite_client import AsyncSQLiteClient
except ModuleNotFoundError:
    AsyncSQLiteClient = None  # type: ignore[assignment]

try:
    from .async_local_storage_client import AsyncLocalStorageClient
except ModuleNotFoundError:
    AsyncLocalStorageClient = None  # type: ignore[assignment]

try:
    from .async_chroma_client import AsyncChromaClient
except ModuleNotFoundError:
    AsyncChromaClient = None  # type: ignore[assignment]

try:
    from .async_memory_client import AsyncMemoryClient
except ModuleNotFoundError:
    AsyncMemoryClient = None  # type: ignore[assignment]

# Service Discovery
from .consul_client import AsyncConsulRegistry, ConsulRegistry, consul_lifespan

# =============================================================================
# Quota Enforcement (per-org/tenant resource limits — product_spec tiers)
# =============================================================================
from .quota_enforcer import (
    UNLIMITED,
    PartialConsumption,
    QuotaDecision,
    QuotaEnforcer,
    QuotaExceededError,
    QuotaType,
    TierQuota,
)

# =============================================================================
# Exports
# =============================================================================
__all__ = [
    # Base client & config
    "AsyncBaseClient",
    "ClientConfig",
    "PostgresConfig",
    "RedisConfig",
    "MinIOConfig",
    "LokiConfig",
    # Native async clients
    "AsyncRedisClient",
    "AsyncPostgresClient",
    "AsyncNATSClient",
    "AsyncNeo4jClient",
    "AsyncMinIOClient",
    "AsyncDuckDBClient",
    "AsyncMQTTClient",
    "AsyncQdrantClient",
    "AsyncFalkorClient",
    "AsyncLokiClient",
    "LokiHandler",
    "setup_loki_logging",
    # Observability
    "setup_metrics",
    "create_counter",
    "create_histogram",
    "create_gauge",
    "metrics_text",
    "setup_tracing",
    "get_tracer",
    "setup_observability",
    # Brand (white-label config)
    "BrandConfig",
    "get_brand",
    # Edition (runtime feature flags — ADR 0006)
    "EditionType",
    "EditionConfig",
    "get_edition",
    # License (offline ed25519-signed entitlement — ADR 0008)
    "LicenseStatus",
    "LicenseConfig",
    "get_license",
    "setup_licensing",
    "add_license_middleware",
    "LicenseError",
    # Plugin / Extension SDK (ADR 0006)
    "PluginKind",
    "PluginManifest",
    "ServiceBinding",
    "PluginServiceRegistry",
    "load_manifest",
    # Local-mode alternative clients
    "AsyncSQLiteClient",
    "AsyncLocalStorageClient",
    "AsyncChromaClient",
    "AsyncMemoryClient",
    # Service discovery
    "ConsulRegistry",
    "AsyncConsulRegistry",
    "consul_lifespan",
    # Quota enforcement
    "QuotaEnforcer",
    "QuotaType",
    "TierQuota",
    "QuotaDecision",
    "PartialConsumption",
    "QuotaExceededError",
    "UNLIMITED",
    # Port configuration
    "NATIVE_PORTS",
]

# =============================================================================
# Native port configuration
# =============================================================================
NATIVE_PORTS: Dict[str, int] = {
    "postgres": 5432,
    "redis": 6379,
    "neo4j": 7687,
    "nats": 4222,
    "qdrant": 6333,
    "falkordb": 6379,  # Redis-module graph DB; deployed on its own service in production
    "mqtt": 1883,
    "minio": 9000,
    "consul": 8500,
    "loki": 3100,
    "tempo_otlp_grpc": 4317,
    "tempo_otlp_http": 4318,
    "prometheus": 9090,
    "grafana": 3000,
    "duckdb": 0,  # Embedded, no port
}

__version__ = "0.4.0"
