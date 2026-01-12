"""
gRPC Client Data Contract

Defines canonical data structures for gRPC client testing.
All tests MUST use these enums, factories, and mocks for consistency.

This is the SINGLE SOURCE OF TRUTH for gRPC client test data.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from unittest.mock import AsyncMock, MagicMock, PropertyMock
import grpc


# ============================================================================
# Channel State Definitions (from gRPC)
# ============================================================================

class ChannelState(Enum):
    """
    gRPC Channel Connectivity States

    Maps to grpc.ChannelConnectivity enum values.
    """
    IDLE = grpc.ChannelConnectivity.IDLE
    CONNECTING = grpc.ChannelConnectivity.CONNECTING
    READY = grpc.ChannelConnectivity.READY
    TRANSIENT_FAILURE = grpc.ChannelConnectivity.TRANSIENT_FAILURE
    SHUTDOWN = grpc.ChannelConnectivity.SHUTDOWN


# Define healthy vs unhealthy states per logic contract
HEALTHY_STATES = frozenset([
    ChannelState.IDLE,
    ChannelState.READY,
    ChannelState.CONNECTING,
])

UNHEALTHY_STATES = frozenset([
    ChannelState.SHUTDOWN,
    ChannelState.TRANSIENT_FAILURE,
])


# ============================================================================
# Test Scenarios
# ============================================================================

@dataclass
class ChannelHealthScenario:
    """
    Test scenario for channel health checking.

    Defines initial state, expected behavior, and assertions.
    """
    name: str
    description: str
    initial_state: ChannelState
    should_reconnect: bool
    expected_final_state: Optional[ChannelState] = None

    def __str__(self):
        return f"Scenario({self.name})"


# Pre-defined test scenarios based on logic contract
CHANNEL_HEALTH_SCENARIOS = [
    # Healthy states - should NOT reconnect
    ChannelHealthScenario(
        name="idle_channel",
        description="IDLE channel should proceed without reconnection",
        initial_state=ChannelState.IDLE,
        should_reconnect=False,
    ),
    ChannelHealthScenario(
        name="ready_channel",
        description="READY channel should proceed without reconnection",
        initial_state=ChannelState.READY,
        should_reconnect=False,
    ),
    ChannelHealthScenario(
        name="connecting_channel",
        description="CONNECTING channel should proceed (wait for ready)",
        initial_state=ChannelState.CONNECTING,
        should_reconnect=False,
    ),

    # Unhealthy states - MUST reconnect
    ChannelHealthScenario(
        name="shutdown_channel",
        description="SHUTDOWN channel MUST trigger reconnection",
        initial_state=ChannelState.SHUTDOWN,
        should_reconnect=True,
        expected_final_state=ChannelState.READY,
    ),
    ChannelHealthScenario(
        name="transient_failure_channel",
        description="TRANSIENT_FAILURE channel MUST trigger reconnection",
        initial_state=ChannelState.TRANSIENT_FAILURE,
        should_reconnect=True,
        expected_final_state=ChannelState.READY,
    ),
]


# ============================================================================
# Mock Factories
# ============================================================================

class MockChannelFactory:
    """
    Factory for creating mock gRPC channels with specific states.

    Used to test channel health checking without real gRPC connections.
    """

    @staticmethod
    def create_channel(state: ChannelState) -> MagicMock:
        """
        Create a mock channel in the specified state.

        Args:
            state: The channel state to simulate

        Returns:
            MagicMock configured to return the specified state
        """
        channel = MagicMock()
        channel.get_state.return_value = state.value
        channel.close = AsyncMock()
        return channel

    @staticmethod
    def create_channel_that_transitions(
        initial_state: ChannelState,
        final_state: ChannelState,
    ) -> MagicMock:
        """
        Create a mock channel that transitions between states.

        First call to get_state() returns initial_state.
        Subsequent calls return final_state.

        Useful for testing reconnection behavior.
        """
        channel = MagicMock()
        call_count = [0]

        def get_state_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return initial_state.value
            return final_state.value

        channel.get_state.side_effect = get_state_side_effect
        channel.close = AsyncMock()
        return channel

    @staticmethod
    def create_healthy_channel() -> MagicMock:
        """Create a channel in READY state"""
        return MockChannelFactory.create_channel(ChannelState.READY)

    @staticmethod
    def create_closed_channel() -> MagicMock:
        """Create a channel in SHUTDOWN state"""
        return MockChannelFactory.create_channel(ChannelState.SHUTDOWN)

    @staticmethod
    def create_failing_channel() -> MagicMock:
        """Create a channel in TRANSIENT_FAILURE state"""
        return MockChannelFactory.create_channel(ChannelState.TRANSIENT_FAILURE)


class MockPoolFactory:
    """
    Factory for creating mock AsyncGlobalChannelPool instances.
    """

    @staticmethod
    def create_pool(
        channels: Optional[Dict[str, MagicMock]] = None,
    ) -> MagicMock:
        """
        Create a mock channel pool.

        Args:
            channels: Pre-configured channels by address

        Returns:
            MagicMock configured as AsyncGlobalChannelPool
        """
        pool = MagicMock()
        pool._channels = channels or {}
        pool._channel_ref_counts = {}

        async def mock_get_channel(address: str, **kwargs):
            if address not in pool._channels:
                pool._channels[address] = MockChannelFactory.create_healthy_channel()
            pool._channel_ref_counts[address] = pool._channel_ref_counts.get(address, 0) + 1
            return pool._channels[address]

        async def mock_release_channel(address: str):
            if address in pool._channel_ref_counts:
                pool._channel_ref_counts[address] = max(0, pool._channel_ref_counts[address] - 1)

        async def mock_close_channel(address: str):
            if address in pool._channels:
                del pool._channels[address]
                pool._channel_ref_counts.pop(address, None)

        pool.get_channel = AsyncMock(side_effect=mock_get_channel)
        pool.release_channel = AsyncMock(side_effect=mock_release_channel)
        pool.close_channel = AsyncMock(side_effect=mock_close_channel)
        pool.shutdown = AsyncMock()

        return pool


class GRPCTestDataFactory:
    """
    Factory for creating test data conforming to contracts.

    Provides methods to generate valid test configurations.
    """

    @staticmethod
    def make_address(host: str = "localhost", port: int = 50062) -> str:
        """Generate address string"""
        return f"{host}:{port}"

    @staticmethod
    def make_client_config(
        host: str = "localhost",
        port: int = 50062,
        user_id: str = "test_user",
        lazy_connect: bool = True,
    ) -> Dict[str, Any]:
        """
        Create valid client configuration.

        Returns:
            Dict with host, port, user_id, lazy_connect
        """
        return {
            "host": host,
            "port": port,
            "user_id": user_id,
            "lazy_connect": lazy_connect,
        }

    @staticmethod
    def make_pool_options() -> List[tuple]:
        """
        Create default gRPC channel options.

        Based on production AsyncGlobalChannelPool settings.
        """
        return [
            ('grpc.max_receive_message_length', 100 * 1024 * 1024),
            ('grpc.max_send_message_length', 100 * 1024 * 1024),
            ('grpc.keepalive_time_ms', 60000),
            ('grpc.keepalive_timeout_ms', 20000),
            ('grpc.http2.min_time_between_pings_ms', 60000),
            ('grpc.http2.max_pings_without_data', 2),
            ('grpc.keepalive_permit_without_calls', 0),
        ]

    @staticmethod
    def get_all_channel_states() -> List[ChannelState]:
        """Get all possible channel states for parametrized tests"""
        return list(ChannelState)

    @staticmethod
    def get_healthy_states() -> List[ChannelState]:
        """Get healthy channel states"""
        return list(HEALTHY_STATES)

    @staticmethod
    def get_unhealthy_states() -> List[ChannelState]:
        """Get unhealthy channel states"""
        return list(UNHEALTHY_STATES)


# ============================================================================
# Mock Client for Testing
# ============================================================================

class MockGRPCClient:
    """
    Minimal mock implementation of AsyncBaseGRPCClient for testing.

    Does NOT inherit from AsyncBaseGRPCClient to avoid real gRPC dependencies.
    Used to test the _ensure_connected logic in isolation.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 50062,
        user_id: str = "test_user",
    ):
        self.host = host
        self.port = port
        self.user_id = user_id
        self.address = f"{host}:{port}"

        # Connection state
        self.channel: Optional[MagicMock] = None
        self.stub: Optional[MagicMock] = None
        self._connected = False
        self._connect_lock = asyncio.Lock()

        # Tracking for assertions
        self.reconnect_count = 0
        self.get_channel_count = 0

    async def _ensure_connected(self):
        """
        CURRENT (buggy) implementation.

        Only checks _connected flag, not channel health.
        """
        if self._connected and self.channel is not None:
            return  # BUG: Doesn't check channel state!

        async with self._connect_lock:
            if self._connected and self.channel is not None:
                return

            self.channel = MockChannelFactory.create_healthy_channel()
            self.stub = MagicMock()
            self._connected = True
            self.get_channel_count += 1

    async def _ensure_connected_fixed(self):
        """
        FIXED implementation that checks channel health.

        This is the expected behavior per BR-002.
        """
        if self._connected and self.channel is not None:
            # NEW: Check actual channel state
            state = self.channel.get_state()
            if state in [s.value for s in HEALTHY_STATES]:
                return  # Channel is healthy, proceed
            # Channel is unhealthy, need to reconnect
            await self.reconnect()
            return

        async with self._connect_lock:
            if self._connected and self.channel is not None:
                state = self.channel.get_state()
                if state in [s.value for s in HEALTHY_STATES]:
                    return
                await self.reconnect()
                return

            self.channel = MockChannelFactory.create_healthy_channel()
            self.stub = MagicMock()
            self._connected = True
            self.get_channel_count += 1

    async def reconnect(self):
        """Force reconnect"""
        self.channel = MockChannelFactory.create_healthy_channel()
        self.stub = MagicMock()
        self._connected = True
        self.reconnect_count += 1

    async def close(self):
        """Release connection"""
        self._connected = False
        self.stub = None

    def is_channel_healthy(self) -> bool:
        """Check if channel is in healthy state"""
        if self.channel is None:
            return False
        state = self.channel.get_state()
        return state in [s.value for s in HEALTHY_STATES]


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # States
    "ChannelState",
    "HEALTHY_STATES",
    "UNHEALTHY_STATES",

    # Scenarios
    "ChannelHealthScenario",
    "CHANNEL_HEALTH_SCENARIOS",

    # Factories
    "MockChannelFactory",
    "MockPoolFactory",
    "GRPCTestDataFactory",

    # Mock Client
    "MockGRPCClient",
]
