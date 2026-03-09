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
from .async_client_config import ClientConfig, PostgresConfig, RedisConfig, MinIOConfig, LokiConfig

# =============================================================================
# Native Async Clients (Direct Connections)
# =============================================================================
from .async_redis_client import AsyncRedisClient
from .async_postgres_client import AsyncPostgresClient
from .async_nats_client import AsyncNATSClient
from .async_neo4j_client import AsyncNeo4jClient
from .async_minio_client import AsyncMinIOClient
from .async_duckdb_client import AsyncDuckDBClient
from .async_mqtt_client import AsyncMQTTClient
from .async_qdrant_client import AsyncQdrantClient
from .async_loki_client import AsyncLokiClient
from .loki_handler import LokiHandler, setup_loki_logging

# =============================================================================
# Observability (Metrics, Tracing, Unified Setup)
# =============================================================================
from .metrics import setup_metrics, create_counter, create_histogram, create_gauge, metrics_text
from .tracing import setup_tracing, get_tracer
from .observability import setup_observability

# =============================================================================
# Local-Mode Alternative Clients (ICP/Desktop — no infrastructure required)
# =============================================================================
from .async_sqlite_client import AsyncSQLiteClient
from .async_local_storage_client import AsyncLocalStorageClient
from .async_chroma_client import AsyncChromaClient
from .async_memory_client import AsyncMemoryClient

# Service Discovery
from .consul_client import ConsulRegistry, consul_lifespan

# =============================================================================
# Exports
# =============================================================================
__all__ = [
    # Base client & config
    'AsyncBaseClient',
    'ClientConfig',
    'PostgresConfig',
    'RedisConfig',
    'MinIOConfig',
    'LokiConfig',
    # Native async clients
    'AsyncRedisClient',
    'AsyncPostgresClient',
    'AsyncNATSClient',
    'AsyncNeo4jClient',
    'AsyncMinIOClient',
    'AsyncDuckDBClient',
    'AsyncMQTTClient',
    'AsyncQdrantClient',
    'AsyncLokiClient',
    'LokiHandler',
    'setup_loki_logging',
    # Observability
    'setup_metrics',
    'create_counter',
    'create_histogram',
    'create_gauge',
    'metrics_text',
    'setup_tracing',
    'get_tracer',
    'setup_observability',
    # Local-mode alternative clients
    'AsyncSQLiteClient',
    'AsyncLocalStorageClient',
    'AsyncChromaClient',
    'AsyncMemoryClient',
    # Service discovery
    'ConsulRegistry',
    'consul_lifespan',
    # Port configuration
    'NATIVE_PORTS',
]

# =============================================================================
# Native port configuration
# =============================================================================
NATIVE_PORTS: Dict[str, int] = {
    'postgres': 5432,
    'redis': 6379,
    'neo4j': 7687,
    'nats': 4222,
    'qdrant': 6333,
    'mqtt': 1883,
    'minio': 9000,
    'consul': 8500,
    'loki': 3100,
    'tempo_otlp_grpc': 4317,
    'tempo_otlp_http': 4318,
    'prometheus': 9090,
    'grafana': 3000,
    'duckdb': 0,  # Embedded, no port
}

__version__ = '0.4.0'
