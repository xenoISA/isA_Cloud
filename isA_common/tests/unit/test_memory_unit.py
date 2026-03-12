"""Unit tests for AsyncMemoryClient — #119."""
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================================
# L1 — Pure logic helpers
# ============================================================================


class TestIsExpired:
    """_is_expired checks TTL expiration."""

    def test_not_expired(self):
        from isa_common import AsyncMemoryClient
        client = AsyncMemoryClient(use_global_store=False, lazy_connect=True)
        client._expiry["key1"] = time.time() + 3600
        assert client._is_expired("key1") is False

    def test_expired(self):
        from isa_common import AsyncMemoryClient
        client = AsyncMemoryClient(use_global_store=False, lazy_connect=True)
        client._expiry["key1"] = time.time() - 1
        assert client._is_expired("key1") is True

    def test_no_expiry(self):
        from isa_common import AsyncMemoryClient
        client = AsyncMemoryClient(use_global_store=False, lazy_connect=True)
        client._expiry["key1"] = 0
        assert client._is_expired("key1") is False

    def test_missing_key(self):
        from isa_common import AsyncMemoryClient
        client = AsyncMemoryClient(use_global_store=False, lazy_connect=True)
        assert client._is_expired("nonexistent") is False


# ============================================================================
# L2 — Component tests (string operations)
# ============================================================================


class TestMemoryClientSetGet:
    """set/get/delete/exists operations."""

    async def test_set_and_get(self, memory_client):
        await memory_client.set("key1", "value1")
        result = await memory_client.get("key1")
        assert result == "value1"

    async def test_get_missing_key(self, memory_client):
        result = await memory_client.get("nonexistent")
        assert result is None

    async def test_delete_existing(self, memory_client):
        await memory_client.set("key1", "value1")
        result = await memory_client.delete("key1")
        assert result is True
        assert await memory_client.get("key1") is None

    async def test_delete_missing(self, memory_client):
        result = await memory_client.delete("nonexistent")
        assert result is False

    async def test_exists_true(self, memory_client):
        await memory_client.set("key1", "value1")
        assert await memory_client.exists("key1") is True

    async def test_exists_false(self, memory_client):
        assert await memory_client.exists("nope") is False


class TestMemoryClientTTL:
    """TTL-based expiration."""

    async def test_set_with_ttl(self, memory_client):
        await memory_client.set("key1", "value1", ttl_seconds=3600)
        result = await memory_client.get("key1")
        assert result == "value1"

    async def test_expired_key_returns_none(self, memory_client):
        await memory_client.set("key1", "value1", ttl_seconds=1)
        # Manually expire it
        prefix = memory_client._prefix_key("key1")
        memory_client._expiry[prefix] = time.time() - 1
        result = await memory_client.get("key1")
        assert result is None

    async def test_ttl_returns_remaining(self, memory_client):
        await memory_client.set("key1", "value1", ttl_seconds=3600)
        remaining = await memory_client.ttl("key1")
        assert 3590 < remaining <= 3600

    async def test_ttl_no_expiry(self, memory_client):
        await memory_client.set("key1", "value1")
        result = await memory_client.ttl("key1")
        assert result == -1

    async def test_expire_sets_ttl(self, memory_client):
        await memory_client.set("key1", "value1")
        result = await memory_client.expire("key1", 60)
        assert result is True
        remaining = await memory_client.ttl("key1")
        assert 50 < remaining <= 60

    async def test_expire_nonexistent_key(self, memory_client):
        result = await memory_client.expire("nope", 60)
        assert result is False


class TestMemoryClientIncr:
    """Increment/decrement operations."""

    async def test_incr_new_key(self, memory_client):
        result = await memory_client.incr("counter")
        assert result == 1

    async def test_incr_existing(self, memory_client):
        await memory_client.set("counter", "5")
        result = await memory_client.incr("counter")
        assert result == 6

    async def test_incr_by_amount(self, memory_client):
        await memory_client.set("counter", "10")
        result = await memory_client.incr("counter", 5)
        assert result == 15

    async def test_decr(self, memory_client):
        await memory_client.set("counter", "10")
        result = await memory_client.decr("counter")
        assert result == 9


class TestMemoryClientMultiKey:
    """Multi-key operations (mset, mget, delete_many)."""

    async def test_mset_and_mget(self, memory_client):
        await memory_client.mset({"k1": "v1", "k2": "v2", "k3": "v3"})
        result = await memory_client.mget(["k1", "k2", "k3"])
        assert result == ["v1", "v2", "v3"]

    async def test_mget_with_missing(self, memory_client):
        await memory_client.set("k1", "v1")
        result = await memory_client.mget(["k1", "missing"])
        assert result == ["v1", None]

    async def test_delete_many(self, memory_client):
        await memory_client.mset({"k1": "v1", "k2": "v2"})
        count = await memory_client.delete_many(["k1", "k2", "k3"])
        assert count == 2


class TestMemoryClientKeys:
    """Key pattern matching and scanning."""

    async def test_keys_pattern(self, memory_client):
        await memory_client.mset({"user:1": "a", "user:2": "b", "session:1": "c"})
        result = await memory_client.keys("user:*")
        assert sorted(result) == ["user:1", "user:2"]

    async def test_keys_all(self, memory_client):
        await memory_client.mset({"k1": "v1", "k2": "v2"})
        result = await memory_client.keys("*")
        assert len(result) == 2

    async def test_scan_pagination(self, memory_client):
        await memory_client.mset({f"k{i}": f"v{i}" for i in range(5)})
        cursor, batch = await memory_client.scan(cursor=0, pattern="*", count=3)
        assert len(batch) == 3
        assert cursor > 0  # More results available


class TestMemoryClientFlush:
    """Flush operations."""

    async def test_flush_clears_tenant_keys(self, memory_client):
        await memory_client.mset({"k1": "v1", "k2": "v2"})
        result = await memory_client.flush()
        assert result is True
        assert await memory_client.keys("*") == []

    async def test_flush_all(self, memory_client):
        await memory_client.mset({"k1": "v1"})
        result = await memory_client.flush_all()
        assert result is True
        assert len(memory_client._store) == 0


# ============================================================================
# L2 — Hash operations
# ============================================================================


class TestMemoryClientHash:
    """Hash (dict-like) operations."""

    async def test_hset_and_hget(self, memory_client):
        await memory_client.hset("myhash", "field1", "value1")
        result = await memory_client.hget("myhash", "field1")
        assert result == "value1"

    async def test_hget_missing_field(self, memory_client):
        await memory_client.hset("myhash", "field1", "value1")
        result = await memory_client.hget("myhash", "missing")
        assert result is None

    async def test_hget_missing_hash(self, memory_client):
        result = await memory_client.hget("nohash", "field")
        assert result is None

    async def test_hgetall(self, memory_client):
        await memory_client.hset("myhash", "f1", "v1")
        await memory_client.hset("myhash", "f2", "v2")
        result = await memory_client.hgetall("myhash")
        assert result == {"f1": "v1", "f2": "v2"}

    async def test_hgetall_empty(self, memory_client):
        result = await memory_client.hgetall("nohash")
        assert result == {}

    async def test_hdel(self, memory_client):
        await memory_client.hset("myhash", "f1", "v1")
        result = await memory_client.hdel("myhash", "f1")
        assert result is True
        assert await memory_client.hget("myhash", "f1") is None

    async def test_hdel_missing(self, memory_client):
        result = await memory_client.hdel("myhash", "nope")
        assert result is False


# ============================================================================
# L2 — List operations
# ============================================================================


class TestMemoryClientList:
    """List (lpush, rpush, lrange, llen) operations."""

    async def test_rpush_and_lrange(self, memory_client):
        await memory_client.rpush("mylist", "a", "b", "c")
        result = await memory_client.lrange("mylist", 0, -1)
        assert result == ["a", "b", "c"]

    async def test_lpush(self, memory_client):
        await memory_client.rpush("mylist", "b")
        await memory_client.lpush("mylist", "a")
        result = await memory_client.lrange("mylist", 0, -1)
        assert result == ["a", "b"]

    async def test_llen(self, memory_client):
        await memory_client.rpush("mylist", "a", "b", "c")
        result = await memory_client.llen("mylist")
        assert result == 3

    async def test_llen_empty(self, memory_client):
        result = await memory_client.llen("empty")
        assert result == 0

    async def test_lrange_slice(self, memory_client):
        await memory_client.rpush("mylist", "a", "b", "c", "d")
        result = await memory_client.lrange("mylist", 1, 2)
        assert result == ["b", "c"]


# ============================================================================
# L2 — Health check and stats
# ============================================================================


class TestMemoryClientHealthCheck:
    """health_check returns status."""

    async def test_health_check(self, memory_client):
        result = await memory_client.health_check()
        assert result["healthy"] is True
        assert result["key_count"] == 0


class TestMemoryClientStats:
    """get_stats returns statistics."""

    async def test_get_stats(self, memory_client):
        await memory_client.mset({"k1": "v1", "k2": "v2"})
        stats = await memory_client.get_stats()
        assert stats["total_keys"] == 2
        assert stats["storage_type"] == "in-memory"


class TestMemoryClientDisconnect:
    """_disconnect cancels cleanup task."""

    async def test_disconnect_cancels_cleanup(self, memory_client):
        import asyncio

        # Create a real task that sleeps forever
        async def forever():
            await asyncio.sleep(3600)

        task = asyncio.create_task(forever())
        memory_client._cleanup_task = task
        await memory_client._disconnect()
        assert task.cancelled()
        assert memory_client._cleanup_task is None


class TestMemoryClientGlobalVsInstance:
    """Global vs instance store isolation."""

    def test_instance_store_isolation(self):
        from isa_common import AsyncMemoryClient
        c1 = AsyncMemoryClient(use_global_store=False, lazy_connect=True)
        c2 = AsyncMemoryClient(use_global_store=False, lazy_connect=True)
        c1._store["key"] = "val"
        assert "key" not in c2._store
