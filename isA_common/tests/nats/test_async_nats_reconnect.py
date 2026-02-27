#!/usr/bin/env python3
"""
Async NATS reconnect regression tests.

Guards against stale/closed connection loops in consumers.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from nats.errors import ConnectionClosedError

from isa_common import AsyncNATSClient


class _FakeNC:
    def __init__(self, connected: bool = True, closed: bool = False):
        self.is_connected = connected
        self.is_closed = closed
        self.publish = AsyncMock()


class _FakeMsg:
    """Fake JetStream message with metadata and ack."""

    def __init__(self, subject="test.subject", data=b"{}"):
        self.subject = subject
        self.data = data
        self.metadata = SimpleNamespace(
            sequence=SimpleNamespace(stream=1),
            num_delivered=1,
        )
        self.ack = AsyncMock()


@pytest.mark.asyncio
async def test_ensure_connected_reconnects_when_connection_is_stale():
    client = AsyncNATSClient(host="localhost", port=4222, user_id="u1", organization_id="o1")
    client._connected = True
    client._nc = _FakeNC(connected=False, closed=True)
    client._js = None

    disconnect_mock = AsyncMock(side_effect=lambda: setattr(client, "_nc", None))

    async def _fake_connect():
        client._nc = _FakeNC(connected=True, closed=False)
        client._js = object()
        client._connected = True

    connect_mock = AsyncMock(side_effect=_fake_connect)
    client._disconnect = disconnect_mock
    client._connect = connect_mock

    await client._ensure_connected()

    assert disconnect_mock.await_count == 1
    assert connect_mock.await_count == 1
    assert client._connection_healthy() is True


@pytest.mark.asyncio
async def test_pull_messages_recovers_on_connection_closed_error():
    client = AsyncNATSClient(host="localhost", port=4222, user_id="u1", organization_id="o1")
    client._connected = True
    client._nc = _FakeNC(connected=True, closed=False)

    pull_sub = SimpleNamespace(fetch=AsyncMock(side_effect=ConnectionClosedError()))
    client._js = SimpleNamespace(pull_subscribe=AsyncMock(return_value=pull_sub))
    client._recover_connection = AsyncMock()

    messages = await client.pull_messages("USAGE_EVENTS", "billing-consumer", batch_size=10)

    assert messages == []
    client._recover_connection.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_retries_once_after_connection_error():
    client = AsyncNATSClient(host="localhost", port=4222, user_id="u1", organization_id="o1")
    client._connected = True
    client._nc = _FakeNC(connected=True, closed=False)
    client._nc.publish = AsyncMock(side_effect=[ConnectionClosedError(), None])
    client._js = object()
    client._recover_connection = AsyncMock()

    result = await client.publish("billing.usage.recorded.test", b"{}")

    assert result is not None and result.get("success") is True
    assert client._nc.publish.await_count == 2
    client._recover_connection.assert_awaited_once()


# ============================================
# Reconnect stats tracking
# ============================================


@pytest.mark.asyncio
async def test_recover_connection_increments_reconnect_count():
    """Recover connection should bump reconnect_count and reset consecutive_errors."""
    client = AsyncNATSClient(host="localhost", port=4222, user_id="u1", organization_id="o1")
    client._connected = False
    client._nc = _FakeNC(connected=False, closed=True)
    client._js = None

    async def _fake_connect():
        client._nc = _FakeNC(connected=True, closed=False)
        client._js = object()
        client._connected = True

    client._disconnect = AsyncMock()
    client._connect = AsyncMock(side_effect=_fake_connect)

    assert client._reconnect_count == 0
    assert client._consecutive_errors == 0

    await client._recover_connection("test_op", ConnectionClosedError())

    assert client._reconnect_count == 1
    assert client._consecutive_errors == 0
    assert client._last_reconnect_ts > 0


@pytest.mark.asyncio
async def test_recover_connection_skips_if_already_healthy():
    """Recover should not bump counts when the connection is already healthy."""
    client = AsyncNATSClient(host="localhost", port=4222, user_id="u1", organization_id="o1")
    client._connected = True
    client._nc = _FakeNC(connected=True, closed=False)
    client._js = object()
    client._disconnect = AsyncMock()
    client._connect = AsyncMock()

    await client._recover_connection("test_op", ConnectionClosedError())

    # Connection was already healthy inside the lock, so no reconnect triggered
    client._connect.assert_not_awaited()
    assert client._consecutive_errors == 0


@pytest.mark.asyncio
async def test_health_check_includes_reconnect_stats():
    """Health check should return reconnect and message processing stats."""
    client = AsyncNATSClient(host="localhost", port=4222, user_id="u1", organization_id="o1")
    client._connected = True
    client._nc = _FakeNC(connected=True, closed=False)
    client._js = object()
    client._reconnect_count = 3
    client._total_messages_pulled = 42
    client._total_ack_failures = 1

    health = await client.health_check()

    assert health["reconnect_count"] == 3
    assert health["total_messages_pulled"] == 42
    assert health["total_ack_failures"] == 1
    assert health["consecutive_errors"] == 0


@pytest.mark.asyncio
async def test_pull_messages_tracks_message_and_ack_stats():
    """Pull messages should increment total_messages_pulled and track ack failures."""
    client = AsyncNATSClient(host="localhost", port=4222, user_id="u1", organization_id="o1")
    client._connected = True
    client._nc = _FakeNC(connected=True, closed=False)

    msg_ok = _FakeMsg(subject="billing.usage.recorded.ok")
    msg_ack_fail = _FakeMsg(subject="billing.usage.recorded.fail")
    msg_ack_fail.ack = AsyncMock(side_effect=Exception("ack timeout"))

    pull_sub = SimpleNamespace(fetch=AsyncMock(return_value=[msg_ok, msg_ack_fail]))
    client._js = SimpleNamespace(pull_subscribe=AsyncMock(return_value=pull_sub))

    messages = await client.pull_messages("USAGE_EVENTS", "billing-consumer", batch_size=10)

    assert len(messages) == 2
    assert client._total_messages_pulled == 2
    assert client._total_ack_failures == 1
