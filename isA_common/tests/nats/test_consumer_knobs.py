"""Unit tests for AsyncNATSClient consumer knobs (#213).

Mocks the underlying ``jetstream`` context so we can verify
``create_consumer`` forwards ``max_deliver`` / ``ack_wait`` / ``ack_policy``
to ``ConsumerConfig`` and that ``pull_messages`` honors the configured
ack policy.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from isa_common.async_nats_client import AsyncNATSClient


@pytest.fixture
def client():
    c = AsyncNATSClient(host="x", port=4222, logger_name="test_nats")
    # Skip connection — wire mocks directly.
    c._ensure_connected = AsyncMock(return_value=None)
    c._js = MagicMock()
    c._js.add_consumer = AsyncMock()
    c._js.delete_consumer = AsyncMock()
    c._js.pull_subscribe = AsyncMock()
    return c


# ---------------------------------------------------------------------------
# create_consumer — knob forwarding
# ---------------------------------------------------------------------------


class TestCreateConsumerKnobs:
    @pytest.mark.asyncio
    async def test_defaults_are_explicit_unlimited_30s(self, client):
        result = await client.create_consumer("S1", "C1")
        assert result == {"success": True, "consumer": "C1"}

        config = client._js.add_consumer.await_args.args[1]
        assert config.ack_policy.name == "EXPLICIT"
        assert config.max_deliver == -1
        assert config.ack_wait == 30

    @pytest.mark.asyncio
    async def test_max_deliver_forwarded(self, client):
        await client.create_consumer("S", "C", max_deliver=5)
        cfg = client._js.add_consumer.await_args.args[1]
        assert cfg.max_deliver == 5

    @pytest.mark.asyncio
    async def test_ack_wait_forwarded(self, client):
        await client.create_consumer("S", "C", ack_wait=120)
        cfg = client._js.add_consumer.await_args.args[1]
        assert cfg.ack_wait == 120

    @pytest.mark.asyncio
    async def test_ack_policy_all(self, client):
        await client.create_consumer("S", "C", ack_policy="all")
        cfg = client._js.add_consumer.await_args.args[1]
        assert cfg.ack_policy.name == "ALL"

    @pytest.mark.asyncio
    async def test_ack_policy_none(self, client):
        await client.create_consumer("S", "C", ack_policy="none")
        cfg = client._js.add_consumer.await_args.args[1]
        assert cfg.ack_policy.name == "NONE"


# ---------------------------------------------------------------------------
# pull_messages — honor ack_policy
# ---------------------------------------------------------------------------


def _fake_msg(subject: str = "s.x", data: bytes = b"hi", seq: int = 1, delivered: int = 1):
    msg = MagicMock()
    msg.subject = subject
    msg.data = data
    msg.metadata = SimpleNamespace(
        sequence=SimpleNamespace(stream=seq),
        num_delivered=delivered,
    )
    msg.ack = AsyncMock()
    msg.nak = AsyncMock()
    msg.term = AsyncMock()
    return msg


class TestPullMessagesAckPolicy:
    @pytest.mark.asyncio
    async def test_explicit_does_not_auto_ack_and_returns_handle(self, client):
        msg = _fake_msg()
        psub = MagicMock()
        psub.fetch = AsyncMock(return_value=[msg])
        client._js.pull_subscribe = AsyncMock(return_value=psub)

        # Configure consumer as explicit (the post-#213 default).
        await client.create_consumer("S", "C", ack_policy="explicit")
        envelopes = await client.pull_messages("S", "C")

        assert len(envelopes) == 1
        env = envelopes[0]
        assert env["subject"] == "s.x"
        assert env["num_delivered"] == 1
        assert "_msg" in env  # caller must ack
        msg.ack.assert_not_called()  # no auto-ack in explicit mode

    @pytest.mark.asyncio
    async def test_all_mode_auto_acks(self, client):
        msg = _fake_msg()
        psub = MagicMock()
        psub.fetch = AsyncMock(return_value=[msg])
        client._js.pull_subscribe = AsyncMock(return_value=psub)

        await client.create_consumer("S", "C", ack_policy="all")
        envelopes = await client.pull_messages("S", "C")

        assert "_msg" not in envelopes[0]  # legacy auto-ack mode — no handle
        msg.ack.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_explicit_override_via_auto_ack_param(self, client):
        msg = _fake_msg()
        psub = MagicMock()
        psub.fetch = AsyncMock(return_value=[msg])
        client._js.pull_subscribe = AsyncMock(return_value=psub)

        await client.create_consumer("S", "C", ack_policy="explicit")
        # Force auto-ack even though policy is explicit
        envelopes = await client.pull_messages("S", "C", auto_ack=True)
        assert "_msg" not in envelopes[0]
        msg.ack.assert_awaited_once()


# ---------------------------------------------------------------------------
# ack/nak/term helpers
# ---------------------------------------------------------------------------


class TestExplicitAckHelpers:
    @pytest.mark.asyncio
    async def test_ack_message_handle_calls_msg_ack(self, client):
        msg = _fake_msg()
        ok = await client.ack_message_handle(msg)
        assert ok is True
        msg.ack.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_nak_message_handle_with_delay(self, client):
        msg = _fake_msg()
        ok = await client.nak_message_handle(msg, delay=2.5)
        assert ok is True
        msg.nak.assert_awaited_once_with(delay=2.5)

    @pytest.mark.asyncio
    async def test_term_message_handle(self, client):
        msg = _fake_msg()
        ok = await client.term_message_handle(msg)
        assert ok is True
        msg.term.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ack_failure_returns_false(self, client):
        msg = _fake_msg()
        msg.ack = AsyncMock(side_effect=RuntimeError("broken"))
        ok = await client.ack_message_handle(msg)
        assert ok is False
