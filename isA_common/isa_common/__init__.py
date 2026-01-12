#!/usr/bin/env python3
"""
isa-common: Native Async Clients for isA Platform

Version 0.4.0 - Direct native drivers (gRPC removed)

Native async clients connect directly to infrastructure services:
- AsyncPostgresClient (asyncpg) - port 5432
- AsyncRedisClient (redis-py async) - port 6379
- AsyncNeo4jClient (neo4j driver) - port 7687
- AsyncNATSClient (nats-py) - port 4222
- AsyncQdrantClient (qdrant-client) - port 6333
- AsyncMQTTClient (aiomqtt) - port 1883
- AsyncMinIOClient (aioboto3) - port 9000
- AsyncDuckDBClient (duckdb) - embedded

Usage:
    from isa_common import AsyncPostgresClient, AsyncRedisClient

    # Create client with native connection
    async with AsyncPostgresClient(host='localhost', port=5432, database='mydb') as pg:
        result = await pg.query("SELECT * FROM users")
"""

from typing import Dict

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

# Service Discovery
from .consul_client import ConsulRegistry, consul_lifespan

# =============================================================================
# Exports
# =============================================================================
__all__ = [
    # Native async clients
    'AsyncRedisClient',
    'AsyncPostgresClient',
    'AsyncNATSClient',
    'AsyncNeo4jClient',
    'AsyncMinIOClient',
    'AsyncDuckDBClient',
    'AsyncMQTTClient',
    'AsyncQdrantClient',
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
    'duckdb': 0,  # Embedded, no port
}

__version__ = '0.4.0'
