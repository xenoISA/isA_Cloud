#!/usr/bin/env python3
"""
Backward-compatible NATS client import.

Historically, callers imported ``isa_common.nats_client.NATSClient``.
The native implementation now lives in ``async_nats_client.AsyncNATSClient``.
This shim preserves the old import path.
"""

from .async_nats_client import AsyncNATSClient


class NATSClient(AsyncNATSClient):
    """Compatibility alias for the async native NATS client."""

    async def aclose(self) -> None:
        """Compatibility alias for async close."""
        await self.close()
