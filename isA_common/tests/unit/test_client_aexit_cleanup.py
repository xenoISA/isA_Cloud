"""Unit tests for #122 — verify NATS and MQTT clients clean up on context exit."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestNATSClientAexit:
    """AsyncNATSClient must clean up subscriptions and close on __aexit__."""

    async def test_aexit_calls_close(self):
        from isa_common import AsyncNATSClient

        client = AsyncNATSClient(host="localhost", port=4222, lazy_connect=True)
        client._connected = True
        client._nc = AsyncMock()
        client._nc.is_connected = True
        client._nc.is_closed = False
        client._nc.drain = AsyncMock()
        client._nc.close = AsyncMock()
        client._js = MagicMock()

        await client.__aexit__(None, None, None)

        assert client._connected is False

    async def test_aexit_unsubscribes_active_subscriptions(self):
        from isa_common import AsyncNATSClient

        client = AsyncNATSClient(host="localhost", port=4222, lazy_connect=True)
        client._connected = True
        client._nc = AsyncMock()
        client._nc.is_connected = True
        client._nc.is_closed = False
        client._nc.drain = AsyncMock()
        client._nc.close = AsyncMock()
        client._js = MagicMock()

        # Add mock subscriptions
        mock_sub = AsyncMock()
        mock_sub.unsubscribe = AsyncMock()
        client._subscriptions["test.subject"] = mock_sub

        await client.__aexit__(None, None, None)

        mock_sub.unsubscribe.assert_awaited_once()
        assert len(client._subscriptions) == 0

    async def test_aexit_handles_unsubscribe_error(self):
        from isa_common import AsyncNATSClient

        client = AsyncNATSClient(host="localhost", port=4222, lazy_connect=True)
        client._connected = True
        client._nc = AsyncMock()
        client._nc.is_connected = True
        client._nc.is_closed = False
        client._nc.drain = AsyncMock()
        client._nc.close = AsyncMock()
        client._js = MagicMock()

        mock_sub = AsyncMock()
        mock_sub.unsubscribe = AsyncMock(side_effect=Exception("already unsubscribed"))
        client._subscriptions["test.subject"] = mock_sub

        # Should not raise
        await client.__aexit__(None, None, None)
        assert client._connected is False

    async def test_aexit_cleans_up_on_exception(self):
        from isa_common import AsyncNATSClient

        client = AsyncNATSClient(host="localhost", port=4222, lazy_connect=True)
        client._connected = True
        client._nc = AsyncMock()
        client._nc.is_connected = True
        client._nc.is_closed = False
        client._nc.drain = AsyncMock()
        client._nc.close = AsyncMock()
        client._js = MagicMock()

        # Simulate context exit with an exception
        await client.__aexit__(RuntimeError, RuntimeError("test"), None)
        assert client._connected is False


class TestMQTTClientAexit:
    """AsyncMQTTClient must clean up sessions and subscriptions on __aexit__."""

    async def test_aexit_calls_close(self):
        from isa_common import AsyncMQTTClient

        client = AsyncMQTTClient(host="localhost", port=1883, lazy_connect=True)
        client._connected = True

        await client.__aexit__(None, None, None)

        assert client._connected is False

    async def test_aexit_clears_sessions_and_subscriptions(self):
        from isa_common import AsyncMQTTClient

        client = AsyncMQTTClient(host="localhost", port=1883, lazy_connect=True)
        client._connected = True

        # Add some state
        client._sessions["s1"] = {"client_id": "test"}
        client._subscriptions["s1:topic/test"] = {"topic": "topic/test"}
        client._devices["d1"] = {"device_id": "d1"}

        await client.__aexit__(None, None, None)

        assert len(client._sessions) == 0
        assert len(client._subscriptions) == 0
        assert len(client._devices) == 0
        assert client._connected is False

    async def test_aexit_cleans_up_on_exception(self):
        from isa_common import AsyncMQTTClient

        client = AsyncMQTTClient(host="localhost", port=1883, lazy_connect=True)
        client._connected = True
        client._sessions["s1"] = {"client_id": "test"}

        await client.__aexit__(RuntimeError, RuntimeError("test"), None)

        assert len(client._sessions) == 0
        assert client._connected is False


class TestBaseClientAexitDefault:
    """Base class __aexit__ should be a no-op (backward compat)."""

    async def test_base_aexit_is_noop(self):
        from isa_common.async_base_client import AsyncBaseClient

        # Base __aexit__ doesn't close — subclasses override
        # Just verify it exists and doesn't raise
        class DummyClient(AsyncBaseClient):
            async def _connect(self): pass
            async def _disconnect(self): pass
            async def health_check(self): return {"healthy": True}

        client = DummyClient(lazy_connect=True)
        client._connected = True
        await client.__aexit__(None, None, None)
        # Base doesn't close — that's the documented behavior
        assert client._connected is True
