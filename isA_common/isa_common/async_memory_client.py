#!/usr/bin/env python3
"""
Async In-Memory Cache Client
Local alternative to AsyncRedisClient for ICP (Intelligent Personal Context) mode.

This client provides the same interface as AsyncRedisClient but uses an in-memory
dictionary with TTL support, making it suitable for local desktop usage without
requiring Redis server.

Features:
- TTL-based expiration
- Pattern matching for key searches
- Basic pub/sub simulation (optional)
- Thread-safe operations
"""

import asyncio
import fnmatch
import time
from typing import List, Dict, Optional, Any, AsyncIterator
from collections import defaultdict
import threading

from .async_base_client import AsyncBaseClient


class AsyncMemoryClient(AsyncBaseClient):
    """
    Async in-memory cache client - drop-in replacement for AsyncRedisClient.

    Provides the same interface as AsyncRedisClient for local ICP mode.
    Data is stored in memory and will be lost on restart.

    Thread-safe implementation using asyncio locks.
    """

    # Class-level configuration
    SERVICE_NAME = "MemoryCache"
    DEFAULT_HOST = "localhost"  # Not used, but kept for interface compatibility
    DEFAULT_PORT = 0  # In-memory, no port
    ENV_PREFIX = "MEMORY"
    TENANT_SEPARATOR = ":"  # org:user:key

    # Shared storage for singleton-like behavior across instances
    _global_store: Dict[str, Any] = {}
    _global_expiry: Dict[str, float] = {}
    _global_lock = threading.Lock()

    def __init__(
        self,
        use_global_store: bool = True,
        **kwargs
    ):
        """
        Initialize async in-memory cache client.

        Args:
            use_global_store: If True, share storage across all instances.
                            If False, use instance-local storage.
            **kwargs: Base client args (user_id, organization_id, lazy_connect)
        """
        super().__init__(**kwargs)

        self._use_global = use_global_store

        if use_global_store:
            self._store = AsyncMemoryClient._global_store
            self._expiry = AsyncMemoryClient._global_expiry
        else:
            self._store = {}
            self._expiry = {}

        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    async def _connect(self) -> None:
        """Initialize cache (start cleanup task)."""
        # Start background cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_expired())
        self._logger.info("In-memory cache initialized")

    async def _disconnect(self) -> None:
        """Cleanup cache."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_expired(self):
        """Background task to clean up expired keys."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                await self._remove_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Cleanup error: {e}")

    async def _remove_expired(self):
        """Remove all expired keys."""
        now = time.time()
        async with self._lock:
            expired_keys = [
                key for key, exp_time in self._expiry.items()
                if exp_time > 0 and exp_time < now
            ]
            for key in expired_keys:
                self._store.pop(key, None)
                self._expiry.pop(key, None)

    def _is_expired(self, key: str) -> bool:
        """Check if a key is expired."""
        exp_time = self._expiry.get(key, 0)
        if exp_time > 0 and exp_time < time.time():
            return True
        return False

    # ============================================
    # Health Check
    # ============================================

    async def health_check(self, deep_check: bool = False) -> Optional[Dict]:
        """Check cache health."""
        try:
            await self._ensure_connected()

            async with self._lock:
                key_count = len(self._store)
                expired_count = sum(1 for k in self._expiry if self._is_expired(k))

            return {
                'healthy': True,
                'cache_status': 'connected',
                'key_count': key_count,
                'expired_pending': expired_count,
                'used_memory_estimate': key_count * 1024  # Rough estimate
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

            async with self._lock:
                self._store[prefixed_key] = value
                if ttl_seconds > 0:
                    self._expiry[prefixed_key] = time.time() + ttl_seconds
                else:
                    self._expiry[prefixed_key] = 0  # No expiry

            return True

        except Exception as e:
            self.handle_error(e, "set")
            return False

    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        try:
            await self._ensure_connected()
            prefixed_key = self._prefix_key(key)

            async with self._lock:
                if self._is_expired(prefixed_key):
                    self._store.pop(prefixed_key, None)
                    self._expiry.pop(prefixed_key, None)
                    return None

                return self._store.get(prefixed_key)

        except Exception as e:
            return self.handle_error(e, "get")

    async def delete(self, key: str) -> Optional[bool]:
        """Delete key."""
        try:
            await self._ensure_connected()
            prefixed_key = self._prefix_key(key)

            async with self._lock:
                existed = prefixed_key in self._store
                self._store.pop(prefixed_key, None)
                self._expiry.pop(prefixed_key, None)

            return existed

        except Exception as e:
            self.handle_error(e, "delete")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        try:
            await self._ensure_connected()
            prefixed_key = self._prefix_key(key)

            async with self._lock:
                if self._is_expired(prefixed_key):
                    self._store.pop(prefixed_key, None)
                    self._expiry.pop(prefixed_key, None)
                    return False

                return prefixed_key in self._store

        except Exception as e:
            self.handle_error(e, "exists")
            return False

    async def ttl(self, key: str) -> Optional[int]:
        """Get TTL for key in seconds."""
        try:
            await self._ensure_connected()
            prefixed_key = self._prefix_key(key)

            async with self._lock:
                exp_time = self._expiry.get(prefixed_key, 0)
                if exp_time == 0:
                    return -1  # No expiry
                if exp_time < time.time():
                    return -2  # Expired

                return int(exp_time - time.time())

        except Exception as e:
            return self.handle_error(e, "ttl")

    async def expire(self, key: str, ttl_seconds: int) -> Optional[bool]:
        """Set TTL on existing key."""
        try:
            await self._ensure_connected()
            prefixed_key = self._prefix_key(key)

            async with self._lock:
                if prefixed_key in self._store:
                    self._expiry[prefixed_key] = time.time() + ttl_seconds
                    return True
                return False

        except Exception as e:
            self.handle_error(e, "expire")
            return False

    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment value by amount."""
        try:
            await self._ensure_connected()
            prefixed_key = self._prefix_key(key)

            async with self._lock:
                current = self._store.get(prefixed_key, '0')
                try:
                    new_value = int(current) + amount
                except ValueError:
                    new_value = amount

                self._store[prefixed_key] = str(new_value)
                return new_value

        except Exception as e:
            return self.handle_error(e, "incr")

    async def decr(self, key: str, amount: int = 1) -> Optional[int]:
        """Decrement value by amount."""
        return await self.incr(key, -amount)

    # ============================================
    # Multi-key Operations
    # ============================================

    async def mset(self, mapping: Dict[str, str]) -> Optional[bool]:
        """Set multiple key-value pairs."""
        try:
            await self._ensure_connected()

            async with self._lock:
                for key, value in mapping.items():
                    prefixed_key = self._prefix_key(key)
                    self._store[prefixed_key] = value
                    self._expiry[prefixed_key] = 0

            return True

        except Exception as e:
            self.handle_error(e, "mset")
            return False

    async def mget(self, keys: List[str]) -> List[Optional[str]]:
        """Get multiple values by keys."""
        try:
            await self._ensure_connected()

            results = []
            async with self._lock:
                for key in keys:
                    prefixed_key = self._prefix_key(key)
                    if self._is_expired(prefixed_key):
                        self._store.pop(prefixed_key, None)
                        self._expiry.pop(prefixed_key, None)
                        results.append(None)
                    else:
                        results.append(self._store.get(prefixed_key))

            return results

        except Exception as e:
            self.handle_error(e, "mget")
            return [None] * len(keys)

    async def delete_many(self, keys: List[str]) -> Optional[int]:
        """Delete multiple keys."""
        try:
            await self._ensure_connected()

            count = 0
            async with self._lock:
                for key in keys:
                    prefixed_key = self._prefix_key(key)
                    if prefixed_key in self._store:
                        self._store.pop(prefixed_key, None)
                        self._expiry.pop(prefixed_key, None)
                        count += 1

            return count

        except Exception as e:
            return self.handle_error(e, "delete_many")

    # ============================================
    # Key Operations
    # ============================================

    async def keys(self, pattern: str = '*') -> List[str]:
        """Get keys matching pattern."""
        try:
            await self._ensure_connected()
            prefixed_pattern = self._prefix_key(pattern)

            async with self._lock:
                matched = []
                for key in self._store.keys():
                    if fnmatch.fnmatch(key, prefixed_pattern):
                        if not self._is_expired(key):
                            # Return unprefixed key
                            matched.append(self._unprefix_key(key))

                return matched

        except Exception as e:
            self.handle_error(e, "keys")
            return []

    async def scan(self, cursor: int = 0, pattern: str = '*',
                  count: int = 100) -> tuple:
        """Scan keys with pattern."""
        try:
            await self._ensure_connected()
            prefixed_pattern = self._prefix_key(pattern)

            async with self._lock:
                all_keys = [
                    k for k in self._store.keys()
                    if fnmatch.fnmatch(k, prefixed_pattern) and not self._is_expired(k)
                ]

            # Simulate cursor-based pagination
            start = cursor
            end = min(cursor + count, len(all_keys))
            batch = [self._unprefix_key(k) for k in all_keys[start:end]]

            new_cursor = end if end < len(all_keys) else 0

            return (new_cursor, batch)

        except Exception as e:
            self.handle_error(e, "scan")
            return (0, [])

    async def flush(self) -> Optional[bool]:
        """Clear all keys (within tenant prefix)."""
        try:
            await self._ensure_connected()
            prefix = self._get_key_prefix()

            async with self._lock:
                keys_to_delete = [k for k in self._store.keys() if k.startswith(prefix)]
                for key in keys_to_delete:
                    self._store.pop(key, None)
                    self._expiry.pop(key, None)

            return True

        except Exception as e:
            self.handle_error(e, "flush")
            return False

    async def flush_all(self) -> Optional[bool]:
        """Clear all keys (globally)."""
        try:
            await self._ensure_connected()

            async with self._lock:
                self._store.clear()
                self._expiry.clear()

            return True

        except Exception as e:
            self.handle_error(e, "flush_all")
            return False

    # ============================================
    # Hash Operations
    # ============================================

    async def hset(self, name: str, key: str, value: str) -> Optional[bool]:
        """Set hash field."""
        try:
            await self._ensure_connected()
            prefixed_name = self._prefix_key(name)

            async with self._lock:
                if prefixed_name not in self._store:
                    self._store[prefixed_name] = {}
                    self._expiry[prefixed_name] = 0

                hash_data = self._store[prefixed_name]
                if not isinstance(hash_data, dict):
                    hash_data = {}
                    self._store[prefixed_name] = hash_data

                hash_data[key] = value

            return True

        except Exception as e:
            self.handle_error(e, "hset")
            return False

    async def hget(self, name: str, key: str) -> Optional[str]:
        """Get hash field."""
        try:
            await self._ensure_connected()
            prefixed_name = self._prefix_key(name)

            async with self._lock:
                if self._is_expired(prefixed_name):
                    self._store.pop(prefixed_name, None)
                    self._expiry.pop(prefixed_name, None)
                    return None

                hash_data = self._store.get(prefixed_name, {})
                if isinstance(hash_data, dict):
                    return hash_data.get(key)
                return None

        except Exception as e:
            return self.handle_error(e, "hget")

    async def hgetall(self, name: str) -> Dict[str, str]:
        """Get all hash fields."""
        try:
            await self._ensure_connected()
            prefixed_name = self._prefix_key(name)

            async with self._lock:
                if self._is_expired(prefixed_name):
                    self._store.pop(prefixed_name, None)
                    self._expiry.pop(prefixed_name, None)
                    return {}

                hash_data = self._store.get(prefixed_name, {})
                if isinstance(hash_data, dict):
                    return dict(hash_data)
                return {}

        except Exception as e:
            self.handle_error(e, "hgetall")
            return {}

    async def hdel(self, name: str, key: str) -> Optional[bool]:
        """Delete hash field."""
        try:
            await self._ensure_connected()
            prefixed_name = self._prefix_key(name)

            async with self._lock:
                hash_data = self._store.get(prefixed_name, {})
                if isinstance(hash_data, dict) and key in hash_data:
                    del hash_data[key]
                    return True
                return False

        except Exception as e:
            self.handle_error(e, "hdel")
            return False

    # ============================================
    # List Operations
    # ============================================

    async def lpush(self, key: str, *values: str) -> Optional[int]:
        """Push values to list head."""
        try:
            await self._ensure_connected()
            prefixed_key = self._prefix_key(key)

            async with self._lock:
                if prefixed_key not in self._store:
                    self._store[prefixed_key] = []
                    self._expiry[prefixed_key] = 0

                lst = self._store[prefixed_key]
                if not isinstance(lst, list):
                    lst = []
                    self._store[prefixed_key] = lst

                for v in reversed(values):
                    lst.insert(0, v)

                return len(lst)

        except Exception as e:
            return self.handle_error(e, "lpush")

    async def rpush(self, key: str, *values: str) -> Optional[int]:
        """Push values to list tail."""
        try:
            await self._ensure_connected()
            prefixed_key = self._prefix_key(key)

            async with self._lock:
                if prefixed_key not in self._store:
                    self._store[prefixed_key] = []
                    self._expiry[prefixed_key] = 0

                lst = self._store[prefixed_key]
                if not isinstance(lst, list):
                    lst = []
                    self._store[prefixed_key] = lst

                lst.extend(values)
                return len(lst)

        except Exception as e:
            return self.handle_error(e, "rpush")

    async def lrange(self, key: str, start: int, end: int) -> List[str]:
        """Get list range."""
        try:
            await self._ensure_connected()
            prefixed_key = self._prefix_key(key)

            async with self._lock:
                if self._is_expired(prefixed_key):
                    self._store.pop(prefixed_key, None)
                    self._expiry.pop(prefixed_key, None)
                    return []

                lst = self._store.get(prefixed_key, [])
                if not isinstance(lst, list):
                    return []

                # Handle negative indices like Redis
                if end == -1:
                    return lst[start:]
                return lst[start:end + 1]

        except Exception as e:
            self.handle_error(e, "lrange")
            return []

    async def llen(self, key: str) -> int:
        """Get list length."""
        try:
            await self._ensure_connected()
            prefixed_key = self._prefix_key(key)

            async with self._lock:
                if self._is_expired(prefixed_key):
                    return 0

                lst = self._store.get(prefixed_key, [])
                if isinstance(lst, list):
                    return len(lst)
                return 0

        except Exception as e:
            self.handle_error(e, "llen")
            return 0

    # ============================================
    # Statistics
    # ============================================

    async def get_stats(self) -> Optional[Dict]:
        """Get cache statistics."""
        try:
            await self._ensure_connected()

            async with self._lock:
                total_keys = len(self._store)
                expired_keys = sum(1 for k in self._expiry if self._is_expired(k))
                active_keys = total_keys - expired_keys

            return {
                'total_keys': total_keys,
                'active_keys': active_keys,
                'expired_pending': expired_keys,
                'storage_type': 'in-memory'
            }

        except Exception as e:
            return self.handle_error(e, "get stats")


# Example usage
if __name__ == '__main__':
    async def main():
        async with AsyncMemoryClient(
            user_id='test_user'
        ) as client:
            # Health check
            health = await client.health_check()
            print(f"Health: {health}")

            # Set/Get
            await client.set('test_key', 'test_value', ttl_seconds=60)
            value = await client.get('test_key')
            print(f"Get: {value}")

            # TTL
            ttl = await client.ttl('test_key')
            print(f"TTL: {ttl}")

            # Keys
            await client.set('key1', 'value1')
            await client.set('key2', 'value2')
            keys = await client.keys('key*')
            print(f"Keys: {keys}")

            # Hash
            await client.hset('hash1', 'field1', 'value1')
            await client.hset('hash1', 'field2', 'value2')
            hash_val = await client.hgetall('hash1')
            print(f"Hash: {hash_val}")

            # List
            await client.rpush('list1', 'a', 'b', 'c')
            list_val = await client.lrange('list1', 0, -1)
            print(f"List: {list_val}")

            # Stats
            stats = await client.get_stats()
            print(f"Stats: {stats}")

            # Cleanup
            await client.flush()

    asyncio.run(main())
