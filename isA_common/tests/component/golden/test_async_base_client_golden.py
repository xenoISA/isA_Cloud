"""
AsyncBaseGRPCClient Component Golden Tests

These tests document CURRENT behavior of AsyncBaseGRPCClient with mocked deps.
Uses proper dependency injection - no patching needed!

Golden tests capture behavior as-is for regression detection.
They document how the code ACTUALLY works NOW, not how it SHOULD work.

GOTCHA FOUND (BR-002 violation):
  The current _ensure_connected() method does NOT check channel health state.
  It only checks `_connected` flag and `channel is not None`.
  This causes "Channel is closed" errors when channel becomes SHUTDOWN.

Usage:
    pytest tests/component/golden/test_async_base_client_golden.py -v
"""
import pytest
import pytest_asyncio
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import grpc

# Import from contracts - add tests directory to path
import sys
import os
_tests_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from contracts.grpc_client import (
    ChannelState,
    HEALTHY_STATES,
    UNHEALTHY_STATES,
    MockChannelFactory,
    MockPoolFactory,
    GRPCTestDataFactory,
    MockGRPCClient,
    CHANNEL_HEALTH_SCENARIOS,
)

pytestmark = [pytest.mark.component, pytest.mark.golden, pytest.mark.asyncio]


# ============================================================================
# Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def mock_client():
    """Create MockGRPCClient for testing"""
    client = MockGRPCClient(
        host="localhost",
        port=50062,
        user_id="test_user",
    )
    yield client
    await client.close()


# ============================================================================
# Golden Tests: Document CURRENT Behavior
# ============================================================================

class TestEnsureConnectedCurrentBehavior:
    """
    Golden tests documenting CURRENT _ensure_connected behavior.

    These tests pass with the CURRENT (buggy) implementation.
    They document the bug for regression detection.
    """

    async def test_ensure_connected_creates_channel_when_not_connected(
        self, mock_client
    ):
        """
        Golden: First call creates channel and stub.

        CURRENT BEHAVIOR:
        - _connected=False, channel=None → creates new connection
        - This is CORRECT behavior
        """
        # Given: Client not connected
        assert mock_client._connected is False
        assert mock_client.channel is None

        # When: _ensure_connected called
        await mock_client._ensure_connected()

        # Then: Channel created
        assert mock_client._connected is True
        assert mock_client.channel is not None
        assert mock_client.stub is not None
        assert mock_client.get_channel_count == 1

    async def test_ensure_connected_reuses_channel_when_connected(
        self, mock_client
    ):
        """
        Golden: Subsequent calls reuse existing channel.

        CURRENT BEHAVIOR:
        - _connected=True, channel exists → reuses existing channel
        - This is CORRECT behavior for healthy channels
        """
        # Given: Client already connected
        await mock_client._ensure_connected()
        original_channel = mock_client.channel

        # When: _ensure_connected called again
        await mock_client._ensure_connected()

        # Then: Same channel reused
        assert mock_client.channel is original_channel
        assert mock_client.get_channel_count == 1  # Only one get_channel call

    async def test_ensure_connected_does_not_check_channel_state(
        self, mock_client
    ):
        """
        Golden: GOTCHA - Current implementation does NOT check channel state!

        CURRENT BEHAVIOR (BUG):
        - _connected=True, channel exists (but SHUTDOWN) → DOES NOT reconnect
        - Returns immediately without checking channel health
        - This causes "Channel is closed" errors on subsequent operations

        This test documents the bug. See TDD test for expected behavior.
        """
        # Given: Client connected
        await mock_client._ensure_connected()

        # Simulate channel becoming SHUTDOWN (e.g., server restart, idle timeout)
        mock_client.channel = MockChannelFactory.create_closed_channel()
        assert mock_client.channel.get_state() == ChannelState.SHUTDOWN.value

        # When: _ensure_connected called
        await mock_client._ensure_connected()

        # Then: GOTCHA - Still using closed channel! (BUG)
        assert mock_client.channel.get_state() == ChannelState.SHUTDOWN.value
        assert mock_client.reconnect_count == 0  # No reconnect happened!

    async def test_ensure_connected_ignores_transient_failure(
        self, mock_client
    ):
        """
        Golden: GOTCHA - Current implementation ignores TRANSIENT_FAILURE!

        CURRENT BEHAVIOR (BUG):
        - _connected=True, channel in TRANSIENT_FAILURE → DOES NOT reconnect
        - Operations will fail with connectivity errors

        This test documents the bug.
        """
        # Given: Client connected
        await mock_client._ensure_connected()

        # Simulate channel going into transient failure
        mock_client.channel = MockChannelFactory.create_failing_channel()
        assert mock_client.channel.get_state() == ChannelState.TRANSIENT_FAILURE.value

        # When: _ensure_connected called
        await mock_client._ensure_connected()

        # Then: GOTCHA - Still using failing channel! (BUG)
        assert mock_client.channel.get_state() == ChannelState.TRANSIENT_FAILURE.value
        assert mock_client.reconnect_count == 0


class TestCloseCurrentBehavior:
    """Golden tests for close() behavior"""

    async def test_close_resets_connection_state(self, mock_client):
        """
        Golden: close() resets _connected and stub but not channel.

        CURRENT BEHAVIOR:
        - Sets _connected=False
        - Sets stub=None
        - Does NOT close channel (shared via pool)
        """
        # Given: Connected client
        await mock_client._ensure_connected()
        assert mock_client._connected is True

        # When: close called
        await mock_client.close()

        # Then: Connection state reset
        assert mock_client._connected is False
        assert mock_client.stub is None


class TestReconnectCurrentBehavior:
    """Golden tests for reconnect() behavior"""

    async def test_reconnect_creates_new_channel(self, mock_client):
        """
        Golden: reconnect() creates new channel regardless of current state.

        CURRENT BEHAVIOR:
        - Creates new channel
        - Creates new stub
        - Sets _connected=True
        - Increments reconnect_count
        """
        # Given: Connected client
        await mock_client._ensure_connected()
        original_channel = mock_client.channel

        # When: reconnect called
        await mock_client.reconnect()

        # Then: New channel created
        assert mock_client.channel is not original_channel
        assert mock_client._connected is True
        assert mock_client.reconnect_count == 1


class TestIsChannelHealthyCurrentBehavior:
    """Golden tests for is_channel_healthy() method"""

    @pytest.mark.parametrize("state", list(ChannelState))
    async def test_is_channel_healthy_checks_channel_state(
        self, mock_client, state: ChannelState
    ):
        """
        Golden: is_channel_healthy returns correct value for each state.

        CURRENT BEHAVIOR:
        - IDLE, READY, CONNECTING → True (healthy)
        - SHUTDOWN, TRANSIENT_FAILURE → False (unhealthy)
        """
        # Given: Channel in specific state
        mock_client.channel = MockChannelFactory.create_channel(state)

        # When: Check health
        is_healthy = mock_client.is_channel_healthy()

        # Then: Correct result
        if state in HEALTHY_STATES:
            assert is_healthy is True, f"State {state} should be healthy"
        else:
            assert is_healthy is False, f"State {state} should be unhealthy"

    async def test_is_channel_healthy_returns_false_when_no_channel(
        self, mock_client
    ):
        """
        Golden: is_channel_healthy returns False when channel is None.
        """
        # Given: No channel
        assert mock_client.channel is None

        # When: Check health
        is_healthy = mock_client.is_channel_healthy()

        # Then: Not healthy
        assert is_healthy is False


# ============================================================================
# Summary of Gotchas Found
# ============================================================================
"""
GOTCHAS DOCUMENTED IN GOLDEN TESTS:

1. BR-002 Violation: _ensure_connected() does NOT check channel health
   - File: test_ensure_connected_does_not_check_channel_state
   - File: test_ensure_connected_ignores_transient_failure
   - Impact: "Channel is closed" errors when channel becomes SHUTDOWN
   - Solution: Add channel state check in _ensure_connected()

TDD tests will define the EXPECTED behavior to fix these issues.
See: tests/component/clients/grpc_client/test_channel_health_tdd.py
"""
