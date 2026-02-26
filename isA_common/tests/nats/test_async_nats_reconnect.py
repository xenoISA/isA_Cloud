#!/usr/bin/env python3
"""
Async NATS reconnect regression tests.

Guards against stale/closed connection loops in consumers.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nats.errors import ConnectionClosedError

from isa_common import AsyncNATSClient


class _FakeNC:
    def __init__(self, connected: bool = True, closed: bool = False):
        self.is_connected = connected
        self.is_closed = closed
        self.publish = AsyncMock()


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
