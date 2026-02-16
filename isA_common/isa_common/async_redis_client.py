#!/usr/bin/env python3
"""
Async Redis Native Client
High-performance async Redis client using redis-py async API.

This client connects directly to Redis using the official redis-py library,
providing full support for all Redis operations including:
- String, List, Hash, Set, Sorted Set operations
- Pub/Sub messaging
- Distributed locks
- Sessions management
- Pipelining and batching
"""

import os
import asyncio
import uuid
from typing import List, Dict, Optional, AsyncIterator, Any

import redis.asyncio as redis
from redis.asyncio import ConnectionPool

from .async_base_client import AsyncBaseClient


class AsyncRedisClient(AsyncBaseClient):
    """
    Async Redis client using native redis-py async driver.

    Provides direct connection to Redis with full feature support including
    all data structures, pub/sub, locks, and high-performance pipelining.
    """

    # Class-level configuration
    SERVICE_NAME = "Redis"
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 6379
    ENV_PREFIX = "REDIS"
    TENANT_SEPARATOR = ":"  # org:user:key

    def __init__(
        self,
        password: Optional[str] = None,
        db: int = 0,
        max_connections: int = 20,
        **kwargs
    ):
        """
        Initialize async Redis client with native driver.

        Args:
            password: Redis password (default: from REDIS_PASSWORD env)
            db: Redis database number (default: 0)
            max_connections: Maximum pool connections (default: 20)
            **kwargs: Base client args (host, port, user_id, organization_id, lazy_connect)
        """
        super().__init__(**kwargs)

        self._password = password or os.getenv('REDIS_PASSWORD')
        self._db = db
        self._max_connections = max_connections

        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._pubsub = None

    async def _connect(self) -> None:
        """Establish Redis connection."""
        self._pool = ConnectionPool(
            host=self._host,
            port=self._port,
            password=self._password,
            db=self._db,
            decode_responses=True,
            max_connections=self._max_connections
        )
        self._client = redis.Redis(connection_pool=self._pool)
        self._logger.info(f"Connected to Redis at {self._host}:{self._port}")

    async def _disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self, deep_check: bool = False) -> Optional[Dict]:
        """Check Redis service health."""
        try:
            await self._ensure_connected()
            await self._client.ping()

            info = await self._client.info() if deep_check else {}

            return {
                'healthy': True,
                'redis_status': 'connected',
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_bytes': info.get('used_memory', 0)
            }

        except Exception as e:
            return self.handle_error(e, "health check")

    # ============================================
    # String Operations
    # ============================================

    async def set(self, key: str, value: str, ttl_seconds: int = 0) -> Optional[bool]:
        """Set key-value with optional TTL."""
        try:
            await self._ensure_connected()
            prefixed_key = self._prefix_key(key)

            if ttl_seconds > 0:
                result = await self._client.setex(prefixed_key, ttl_seconds, value)
            else:
                result = await self._client.set(prefixed_key, value)

            return result is True or result == 'OK'

        except Exception as e:
            self.handle_error(e, "set")
            return False

    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        try:
            await self._ensure_connected()
            return await self._client.get(self._prefix_key(key))

        except Exception as e:
            return self.handle_error(e, "get")

    async def delete(self, key: str) -> Optional[bool]:
        """Delete key."""
        try:
            await self._ensure_connected()
            result = await self._client.delete(self._prefix_key(key))
            return result > 0

        except Exception as e:
            self.handle_error(e, "delete")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        try:
            await self._ensure_connected()
            return await self._client.exists(self._prefix_key(key)) > 0

        except Exception as e:
            self.handle_error(e, "exists")
            return False

    async def set_with_ttl(self, key: str, value: str, ttl_seconds: int) -> Optional[bool]:
        """Set key-value with TTL (alias for set with ttl)."""
        return await self.set(key, value, ttl_seconds)

    async def append(self, key: str, value: str) -> Optional[int]:
        """Append value to key."""
        try:
            await self._ensure_connected()
            return await self._client.append(self._prefix_key(key), value)

        except Exception as e:
            return self.handle_error(e, "append")

    # ============================================
    # Batch Operations
    # ============================================

    async def mset(self, key_values: Dict[str, str], ttl_seconds: int = 0) -> Optional[bool]:
        """Batch set key-values."""
        try:
            await self._ensure_connected()

            prefixed = {self._prefix_key(k): v for k, v in key_values.items()}

            if ttl_seconds > 0:
                pipe = self._client.pipeline()
                for key, value in prefixed.items():
                    pipe.setex(key, ttl_seconds, value)
                await pipe.execute()
            else:
                await self._client.mset(prefixed)

            return True

        except Exception as e:
            self.handle_error(e, "mset")
            return False

    async def mget(self, keys: List[str]) -> Dict[str, str]:
        """Batch get key-values."""
        try:
            await self._ensure_connected()
            prefixed_keys = [self._prefix_key(k) for k in keys]
            values = await self._client.mget(prefixed_keys)

            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    result[key] = value
            return result

        except Exception as e:
            return self.handle_error(e, "mget") or {}

    async def delete_multiple(self, keys: List[str]) -> Optional[int]:
        """Delete multiple keys."""
        try:
            await self._ensure_connected()
            prefixed_keys = [self._prefix_key(k) for k in keys]
            return await self._client.delete(*prefixed_keys)

        except Exception as e:
            self.handle_error(e, "delete_multiple")
            return 0

    async def execute_batch(self, commands: List[Dict]) -> Optional[Dict]:
        """Execute batch commands using pipeline."""
        try:
            await self._ensure_connected()
            pipe = self._client.pipeline()

            for cmd in commands:
                op = cmd.get('operation', '').upper()
                key = self._prefix_key(cmd.get('key', ''))
                value = cmd.get('value', '')
                expiration = cmd.get('expiration')

                if op == 'SET':
                    if expiration:
                        pipe.setex(key, expiration, value)
                    else:
                        pipe.set(key, value)
                elif op == 'GET':
                    pipe.get(key)
                elif op == 'DELETE':
                    pipe.delete(key)
                elif op == 'INCR':
                    pipe.incr(key)
                elif op == 'DECR':
                    pipe.decr(key)

            results = await pipe.execute()

            return {
                'success': True,
                'executed_count': len(results),
                'errors': []
            }

        except Exception as e:
            self.handle_error(e, "execute_batch")
            return None

    # ============================================
    # Counter Operations
    # ============================================

    async def incr(self, key: str, delta: int = 1) -> Optional[int]:
        """Increment counter."""
        try:
            await self._ensure_connected()
            return await self._client.incrby(self._prefix_key(key), delta)

        except Exception as e:
            return self.handle_error(e, "incr")

    async def decr(self, key: str, delta: int = 1) -> Optional[int]:
        """Decrement counter."""
        try:
            await self._ensure_connected()
            return await self._client.decrby(self._prefix_key(key), delta)

        except Exception as e:
            return self.handle_error(e, "decr")

    # ============================================
    # Key Operations
    # ============================================

    async def expire(self, key: str, seconds: int) -> Optional[bool]:
        """Set key expiration."""
        try:
            await self._ensure_connected()
            return await self._client.expire(self._prefix_key(key), seconds)

        except Exception as e:
            self.handle_error(e, "expire")
            return False

    async def ttl(self, key: str) -> Optional[int]:
        """Get time to live."""
        try:
            await self._ensure_connected()
            return await self._client.ttl(self._prefix_key(key))

        except Exception as e:
            return self.handle_error(e, "ttl")

    async def rename(self, old_key: str, new_key: str) -> Optional[bool]:
        """Rename key."""
        try:
            await self._ensure_connected()
            await self._client.rename(
                self._prefix_key(old_key),
                self._prefix_key(new_key)
            )
            return True

        except Exception as e:
            self.handle_error(e, "rename")
            return False

    async def list_keys(self, pattern: str = "*", limit: int = 100) -> List[str]:
        """List keys matching pattern."""
        try:
            await self._ensure_connected()
            full_pattern = self._prefix_key(pattern)
            keys = []
            prefix = self._get_key_prefix()

            async for key in self._client.scan_iter(match=full_pattern, count=limit):
                # Remove prefix from returned keys
                if key.startswith(prefix):
                    keys.append(key[len(prefix):])
                else:
                    keys.append(key)
                if len(keys) >= limit:
                    break

            return keys

        except Exception as e:
            return self.handle_error(e, "list_keys") or []

    # ============================================
    # List Operations
    # ============================================

    async def lpush(self, key: str, values: List[str]) -> Optional[int]:
        """Left push to list."""
        try:
            await self._ensure_connected()
            return await self._client.lpush(self._prefix_key(key), *values)

        except Exception as e:
            return self.handle_error(e, "lpush")

    async def rpush(self, key: str, values: List[str]) -> Optional[int]:
        """Right push to list."""
        try:
            await self._ensure_connected()
            return await self._client.rpush(self._prefix_key(key), *values)

        except Exception as e:
            return self.handle_error(e, "rpush")

    async def lrange(self, key: str, start: int = 0, stop: int = -1) -> List[str]:
        """Get list range."""
        try:
            await self._ensure_connected()
            return await self._client.lrange(self._prefix_key(key), start, stop)

        except Exception as e:
            return self.handle_error(e, "lrange") or []

    async def lpop(self, key: str) -> Optional[str]:
        """Pop from left of list."""
        try:
            await self._ensure_connected()
            return await self._client.lpop(self._prefix_key(key))

        except Exception as e:
            return self.handle_error(e, "lpop")

    async def rpop(self, key: str) -> Optional[str]:
        """Pop from right of list."""
        try:
            await self._ensure_connected()
            return await self._client.rpop(self._prefix_key(key))

        except Exception as e:
            return self.handle_error(e, "rpop")

    async def llen(self, key: str) -> Optional[int]:
        """Get list length."""
        try:
            await self._ensure_connected()
            return await self._client.llen(self._prefix_key(key))

        except Exception as e:
            return self.handle_error(e, "llen")

    # ============================================
    # Hash Operations
    # ============================================

    async def hset(self, key: str, field: str, value: str) -> Optional[bool]:
        """Set hash field."""
        try:
            await self._ensure_connected()
            await self._client.hset(self._prefix_key(key), field, value)
            return True

        except Exception as e:
            self.handle_error(e, "hset")
            return False

    async def hget(self, key: str, field: str) -> Optional[str]:
        """Get hash field."""
        try:
            await self._ensure_connected()
            return await self._client.hget(self._prefix_key(key), field)

        except Exception as e:
            return self.handle_error(e, "hget")

    async def hgetall(self, key: str) -> Dict[str, str]:
        """Get all hash fields."""
        try:
            await self._ensure_connected()
            return await self._client.hgetall(self._prefix_key(key))

        except Exception as e:
            return self.handle_error(e, "hgetall") or {}

    async def hdelete(self, key: str, fields: List[str]) -> Optional[int]:
        """Delete hash fields."""
        try:
            await self._ensure_connected()
            return await self._client.hdel(self._prefix_key(key), *fields)

        except Exception as e:
            self.handle_error(e, "hdelete")
            return 0

    async def hexists(self, key: str, field: str) -> bool:
        """Check if hash field exists."""
        try:
            await self._ensure_connected()
            return await self._client.hexists(self._prefix_key(key), field)

        except Exception as e:
            self.handle_error(e, "hexists")
            return False

    # ============================================
    # Set Operations
    # ============================================

    async def sadd(self, key: str, members: List[str]) -> Optional[int]:
        """Add members to set."""
        try:
            await self._ensure_connected()
            return await self._client.sadd(self._prefix_key(key), *members)

        except Exception as e:
            return self.handle_error(e, "sadd")

    async def sremove(self, key: str, members: List[str]) -> Optional[int]:
        """Remove members from set."""
        try:
            await self._ensure_connected()
            return await self._client.srem(self._prefix_key(key), *members)

        except Exception as e:
            return self.handle_error(e, "sremove")

    async def smembers(self, key: str) -> List[str]:
        """Get all set members."""
        try:
            await self._ensure_connected()
            result = await self._client.smembers(self._prefix_key(key))
            return list(result)

        except Exception as e:
            return self.handle_error(e, "smembers") or []

    async def sismember(self, key: str, member: str) -> bool:
        """Check if member is in set."""
        try:
            await self._ensure_connected()
            return await self._client.sismember(self._prefix_key(key), member)

        except Exception as e:
            self.handle_error(e, "sismember")
            return False

    async def scard(self, key: str) -> Optional[int]:
        """Get set cardinality."""
        try:
            await self._ensure_connected()
            return await self._client.scard(self._prefix_key(key))

        except Exception as e:
            return self.handle_error(e, "scard")

    # ============================================
    # Sorted Set Operations
    # ============================================

    async def zadd(self, key: str, score_members: Dict[str, float]) -> Optional[int]:
        """Add members to sorted set."""
        try:
            await self._ensure_connected()
            # redis-py expects {member: score} format
            return await self._client.zadd(self._prefix_key(key), score_members)

        except Exception as e:
            self.handle_error(e, "zadd")
            return None

    async def zrange(self, key: str, start: int = 0, stop: int = -1,
                     with_scores: bool = False) -> List:
        """Get sorted set range."""
        try:
            await self._ensure_connected()
            result = await self._client.zrange(
                self._prefix_key(key), start, stop, withscores=with_scores
            )
            return list(result)

        except Exception as e:
            return self.handle_error(e, "zrange") or []

    async def zrem(self, key: str, members: List[str]) -> Optional[int]:
        """Remove members from sorted set."""
        try:
            await self._ensure_connected()
            return await self._client.zrem(self._prefix_key(key), *members)

        except Exception as e:
            self.handle_error(e, "zrem")
            return None

    async def zrank(self, key: str, member: str) -> Optional[int]:
        """Get member rank in sorted set."""
        try:
            await self._ensure_connected()
            return await self._client.zrank(self._prefix_key(key), member)

        except Exception as e:
            return self.handle_error(e, "zrank")

    async def zscore(self, key: str, member: str) -> Optional[float]:
        """Get member score in sorted set."""
        try:
            await self._ensure_connected()
            return await self._client.zscore(self._prefix_key(key), member)

        except Exception as e:
            return self.handle_error(e, "zscore")

    async def zcard(self, key: str) -> Optional[int]:
        """Get sorted set cardinality."""
        try:
            await self._ensure_connected()
            return await self._client.zcard(self._prefix_key(key))

        except Exception as e:
            return self.handle_error(e, "zcard")

    # ============================================
    # Distributed Lock Operations
    # ============================================

    async def acquire_lock(self, lock_key: str, ttl_seconds: int = 10,
                          wait_timeout_seconds: int = 5) -> Optional[str]:
        """Acquire distributed lock using SET NX."""
        try:
            await self._ensure_connected()
            lock_id = str(uuid.uuid4())
            prefixed_key = self._prefix_key(f"lock:{lock_key}")

            deadline = asyncio.get_event_loop().time() + wait_timeout_seconds

            while asyncio.get_event_loop().time() < deadline:
                acquired = await self._client.set(
                    prefixed_key, lock_id, nx=True, ex=ttl_seconds
                )
                if acquired:
                    return lock_id

                await asyncio.sleep(0.1)

            return None

        except Exception as e:
            self.handle_error(e, "acquire_lock")
            return None

    async def release_lock(self, lock_key: str, lock_id: str) -> bool:
        """Release distributed lock."""
        try:
            await self._ensure_connected()
            prefixed_key = self._prefix_key(f"lock:{lock_key}")

            # Lua script for atomic check-and-delete
            script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            result = await self._client.eval(script, 1, prefixed_key, lock_id)
            return result == 1

        except Exception as e:
            self.handle_error(e, "release_lock")
            return False

    async def renew_lock(self, lock_key: str, lock_id: str, ttl_seconds: int = 10) -> bool:
        """Renew distributed lock TTL."""
        try:
            await self._ensure_connected()
            prefixed_key = self._prefix_key(f"lock:{lock_key}")

            # Lua script for atomic check-and-expire
            script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("expire", KEYS[1], ARGV[2])
            else
                return 0
            end
            """
            result = await self._client.eval(script, 1, prefixed_key, lock_id, ttl_seconds)
            return result == 1

        except Exception as e:
            self.handle_error(e, "renew_lock")
            return False

    # ============================================
    # Pub/Sub Operations
    # ============================================

    async def publish(self, channel: str, message: str) -> Optional[int]:
        """Publish message to channel."""
        try:
            await self._ensure_connected()
            prefixed_channel = self._prefix_key(channel)
            return await self._client.publish(prefixed_channel, message)

        except Exception as e:
            return self.handle_error(e, "publish")

    async def subscribe(self, channels: List[str]) -> AsyncIterator[Dict]:
        """Subscribe to channels and yield messages."""
        try:
            await self._ensure_connected()
            pubsub = self._client.pubsub()
            prefixed_channels = [self._prefix_key(c) for c in channels]

            await pubsub.subscribe(*prefixed_channels)

            async for message in pubsub.listen():
                if message['type'] == 'message':
                    channel = message['channel']
                    prefix = self._get_key_prefix()
                    if channel.startswith(prefix):
                        channel = channel[len(prefix):]

                    yield {
                        'channel': channel,
                        'message': message['data'],
                        'timestamp': ''
                    }

        except Exception as e:
            self.handle_error(e, "subscribe")

    # ============================================
    # Session Management
    # ============================================

    async def create_session(self, data: Dict[str, str], ttl_seconds: int = 3600) -> Optional[str]:
        """Create session."""
        try:
            await self._ensure_connected()
            session_id = str(uuid.uuid4())
            session_key = self._prefix_key(f"session:{session_id}")

            await self._client.hset(session_key, mapping=data)
            await self._client.expire(session_key, ttl_seconds)

            return session_id

        except Exception as e:
            return self.handle_error(e, "create_session")

    async def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session data."""
        try:
            await self._ensure_connected()
            session_key = self._prefix_key(f"session:{session_id}")
            data = await self._client.hgetall(session_key)

            if data:
                return data
            return None

        except Exception as e:
            return self.handle_error(e, "get_session")

    async def delete_session(self, session_id: str) -> bool:
        """Delete session."""
        try:
            await self._ensure_connected()
            session_key = self._prefix_key(f"session:{session_id}")
            result = await self._client.delete(session_key)
            return result > 0

        except Exception as e:
            self.handle_error(e, "delete_session")
            return False

    # ============================================
    # Statistics
    # ============================================

    async def get_statistics(self) -> Optional[Dict]:
        """Get Redis statistics."""
        try:
            await self._ensure_connected()
            info = await self._client.info()

            return {
                'total_keys': info.get('db0', {}).get('keys', 0) if isinstance(info.get('db0'), dict) else 0,
                'memory_used_bytes': info.get('used_memory', 0),
                'commands_processed': info.get('total_commands_processed', 0),
                'connections_received': info.get('total_connections_received', 0),
                'hit_rate': 0,  # Would need keyspace_hits / (keyspace_hits + keyspace_misses)
                'key_type_distribution': {}
            }

        except Exception as e:
            return self.handle_error(e, "get_statistics")

    # ============================================
    # Concurrent Operations
    # ============================================

    async def get_many_concurrent(self, keys: List[str]) -> Dict[str, Optional[str]]:
        """Get multiple keys concurrently."""
        return await self.mget(keys)

    async def set_many_concurrent(self, key_values: Dict[str, str],
                                  ttl_seconds: int = 0) -> Dict[str, bool]:
        """Set multiple key-values concurrently."""
        success = await self.mset(key_values, ttl_seconds)
        return {k: success for k in key_values.keys()}


# Example usage
if __name__ == '__main__':
    async def main():
        async with AsyncRedisClient(
            host='localhost',
            port=6379,
            user_id='test_user'
        ) as client:
            # Health check
            health = await client.health_check()
            print(f"Health: {health}")

            # Basic operations
            await client.set('test:key1', 'value1')
            value = await client.get('test:key1')
            print(f"Got: {value}")

            # Batch operations
            await client.mset({
                'test:key2': 'value2',
                'test:key3': 'value3'
            })
            values = await client.mget(['test:key2', 'test:key3'])
            print(f"Batch get: {values}")

    asyncio.run(main())
