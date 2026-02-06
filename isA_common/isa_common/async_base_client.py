#!/usr/bin/env python3
"""
Async Base Client
Abstract base class for all async infrastructure clients.

Provides standardized patterns for:
- Constructor with environment variable defaults
- Lazy connection management
- Async context manager support
- Error handling and logging
- Multi-tenant isolation helpers
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any


class AsyncBaseClient(ABC):
    """
    Abstract base class for all async infrastructure clients.

    Subclasses must implement:
    - _connect(): Establish connection to the service
    - _disconnect(): Close connection to the service
    - health_check(): Check service health

    Class attributes to override:
    - SERVICE_NAME: Human-readable service name for logging
    - DEFAULT_HOST: Default host if not provided
    - DEFAULT_PORT: Default port if not provided
    - ENV_PREFIX: Environment variable prefix (e.g., 'REDIS' for REDIS_HOST)
    - TENANT_SEPARATOR: Separator for multi-tenant key prefixing
    """

    # Class-level config (override in subclasses)
    SERVICE_NAME: str = "base"
    DEFAULT_HOST: str = "localhost"
    DEFAULT_PORT: int = 0
    ENV_PREFIX: str = "SERVICE"
    TENANT_SEPARATOR: str = ":"  # Override per client: Redis=':', MinIO='-', NATS='.', MQTT='/'

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        lazy_connect: bool = True,
        **kwargs  # Accept additional kwargs for compatibility
    ):
        """
        Initialize async client with standardized configuration.

        Args:
            host: Service host (default: from {ENV_PREFIX}_HOST env or DEFAULT_HOST)
            port: Service port (default: from {ENV_PREFIX}_PORT env or DEFAULT_PORT)
            user_id: User ID for multi-tenant isolation (default: 'default')
            organization_id: Organization ID for multi-tenant isolation (default: 'default-org')
            lazy_connect: Delay connection until first use (default: True)
            **kwargs: Additional arguments for subclass compatibility
        """
        self._host = host or os.getenv(f'{self.ENV_PREFIX}_HOST', self.DEFAULT_HOST)
        self._port = port or int(os.getenv(f'{self.ENV_PREFIX}_PORT', str(self.DEFAULT_PORT)))
        self.user_id = user_id or 'default'
        self.organization_id = organization_id or 'default-org'
        self._connected = False

        # Setup logger
        self._logger = logging.getLogger(f"isa_common.{self.SERVICE_NAME.lower()}")

        # Log initialization
        if self._port:
            self._logger.info(f"{self.SERVICE_NAME} client initialized: {self._host}:{self._port}")
        else:
            self._logger.info(f"{self.SERVICE_NAME} client initialized: {self._host}")

    # ============================================
    # Abstract Methods (must implement in subclass)
    # ============================================

    @abstractmethod
    async def _connect(self) -> None:
        """
        Establish connection to the service.

        Called by _ensure_connected() when connection is needed.
        Must set up any connection pools, clients, or sessions.
        """
        pass

    @abstractmethod
    async def _disconnect(self) -> None:
        """
        Close connection to the service.

        Called by close() to clean up resources.
        Must close any connection pools, clients, or sessions.
        """
        pass

    @abstractmethod
    async def health_check(self) -> Optional[Dict[str, Any]]:
        """
        Check service health.

        Returns:
            Dict with at least {'healthy': bool} or None on error
        """
        pass

    # ============================================
    # Connection Management (shared implementation)
    # ============================================

    async def _ensure_connected(self) -> None:
        """Ensure connection is established (lazy connect)."""
        if not self._connected:
            await self._connect()
            self._connected = True

    async def close(self) -> None:
        """Close the connection."""
        if self._connected:
            await self._disconnect()
            self._connected = False
            self._logger.info(f"{self.SERVICE_NAME} connection closed")

    async def shutdown(self) -> None:
        """Alias for close() - explicit shutdown at application exit."""
        await self.close()

    async def reconnect(self) -> None:
        """Reconnect to the service (close and re-establish connection)."""
        await self.close()
        await self._ensure_connected()
        self._logger.debug(f"{self.SERVICE_NAME} connection reconnected")

    # ============================================
    # Async Context Manager
    # ============================================

    async def __aenter__(self):
        """Async context manager entry - ensures connection is ready."""
        await self._ensure_connected()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - keeps connection alive for reuse."""
        # Don't close on exit to allow connection reuse
        # Call close() or shutdown() explicitly when done
        pass

    # ============================================
    # Error Handling
    # ============================================

    def handle_error(self, error: Exception, operation: str) -> None:
        """
        Log error and return None.

        Args:
            error: The exception that occurred
            operation: Description of the operation that failed

        Returns:
            None (for easy return in except blocks)
        """
        self._logger.error(f"{self.SERVICE_NAME} {operation} failed: {error}")
        return None

    # ============================================
    # Multi-tenant Isolation Helpers
    # ============================================

    def _get_key_prefix(self) -> str:
        """
        Get prefix for multi-tenant isolation.

        Override in subclass for custom prefix format.
        Default format: {organization_id}{separator}{user_id}{separator}

        Returns:
            Prefix string to prepend to keys/subjects/topics
        """
        sep = self.TENANT_SEPARATOR
        return f"{self.organization_id}{sep}{self.user_id}{sep}"

    def _prefix_key(self, key: str) -> str:
        """
        Add tenant prefix to key if not already present.

        Args:
            key: The key to prefix

        Returns:
            Prefixed key
        """
        prefix = self._get_key_prefix()
        return key if key.startswith(prefix) else f"{prefix}{key}"

    def _unprefix_key(self, key: str) -> str:
        """
        Remove tenant prefix from key if present.

        Args:
            key: The prefixed key

        Returns:
            Key without prefix
        """
        prefix = self._get_key_prefix()
        return key[len(prefix):] if key.startswith(prefix) else key

    # ============================================
    # Properties
    # ============================================

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected

    @property
    def host(self) -> str:
        """Get the configured host."""
        return self._host

    @property
    def port(self) -> int:
        """Get the configured port."""
        return self._port
