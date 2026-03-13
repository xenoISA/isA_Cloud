"""AsyncRedisClient unit tests — mocked redis driver, no infrastructure required."""
import pytest
from unittest.mock import AsyncMock


class TestRedisConnection:
    async def test_starts_disconnected(self):
        from isa_common import AsyncRedisClient

        client = AsyncRedisClient(host="localhost", port=6379, lazy_connect=True)
        assert client._connected is False
        assert client._client is None

    async def test_close_sets_disconnected(self, redis_client):
        await redis_client.close()
        assert redis_client._connected is False


class TestRedisHealthCheck:
    async def test_health_check_success(self, redis_client):
        redis_client._client.ping = AsyncMock(return_value=True)
        redis_client._client.info = AsyncMock(return_value={})

        result = await redis_client.health_check()

        assert result is not None
        assert result["healthy"] is True
        assert result["redis_status"] == "connected"

    async def test_health_check_deep(self, redis_client):
        redis_client._client.ping = AsyncMock(return_value=True)
        redis_client._client.info = AsyncMock(return_value={
            "connected_clients": 5,
            "used_memory": 2048,
        })

        result = await redis_client.health_check(deep_check=True)

        assert result["connected_clients"] == 5
        assert result["used_memory_bytes"] == 2048

    async def test_health_check_on_error_returns_none(self, redis_client):
        redis_client._client.ping = AsyncMock(side_effect=ConnectionError("refused"))

        result = await redis_client.health_check()

        assert result is None


class TestRedisStringOps:
    async def test_set_without_ttl(self, redis_client):
        redis_client._client.set = AsyncMock(return_value=True)

        result = await redis_client.set("mykey", "myvalue")

        assert result is True
        redis_client._client.set.assert_awaited_once()

    async def test_set_with_ttl(self, redis_client):
        redis_client._client.setex = AsyncMock(return_value=True)

        result = await redis_client.set("mykey", "myvalue", ttl_seconds=60)

        assert result is True
        redis_client._client.setex.assert_awaited_once()

    async def test_get_returns_value(self, redis_client):
        redis_client._client.get = AsyncMock(return_value="stored_value")

        result = await redis_client.get("mykey")

        assert result == "stored_value"

    async def test_get_missing_key_returns_none(self, redis_client):
        redis_client._client.get = AsyncMock(return_value=None)

        result = await redis_client.get("missing")

        assert result is None

    async def test_delete_existing_key(self, redis_client):
        redis_client._client.delete = AsyncMock(return_value=1)

        result = await redis_client.delete("mykey")

        assert result is True

    async def test_delete_missing_key(self, redis_client):
        redis_client._client.delete = AsyncMock(return_value=0)

        result = await redis_client.delete("missing")

        assert result is False

    async def test_exists_true(self, redis_client):
        redis_client._client.exists = AsyncMock(return_value=1)

        result = await redis_client.exists("mykey")

        assert result is True

    async def test_exists_false(self, redis_client):
        redis_client._client.exists = AsyncMock(return_value=0)

        result = await redis_client.exists("missing")

        assert result is False


class TestRedisMultiTenant:
    async def test_key_prefixed_with_org_and_user(self, redis_client):
        prefixed = redis_client._prefix_key("session:token")
        assert prefixed == "org1:test_user:session:token"

    async def test_set_uses_prefixed_key(self, redis_client):
        redis_client._client.set = AsyncMock(return_value=True)

        await redis_client.set("data", "value")

        call_args = redis_client._client.set.call_args
        assert call_args[0][0] == "org1:test_user:data"


class TestRedisErrorHandling:
    async def test_set_connection_error_returns_none(self, redis_client):
        redis_client._client.set = AsyncMock(side_effect=ConnectionError("refused"))

        result = await redis_client.set("key", "value")

        assert result is None

    async def test_get_connection_error_returns_none(self, redis_client):
        redis_client._client.get = AsyncMock(side_effect=ConnectionError("refused"))

        result = await redis_client.get("key")

        assert result is None

    async def test_exists_on_error_returns_false(self, redis_client):
        redis_client._client.exists = AsyncMock(side_effect=Exception("timeout"))

        result = await redis_client.exists("key")

        assert result is False
