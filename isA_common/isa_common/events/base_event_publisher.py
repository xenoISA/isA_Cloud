#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base Event Publisher

Generic event publisher that can be extended for business-specific needs.
"""

import json
import logging
import asyncio
import warnings
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod

from ..nats_client import NATSClient
from .base_event_models import BaseEvent

logger = logging.getLogger(__name__)


class BaseEventPublisher(ABC):
    """
    Base class for event publishers.

    Extend this for your service-specific publishers.

    Example:
        class UserEventPublisher(BaseEventPublisher):
            def service_name(self) -> str:
                return "user_service"

            async def publish_user_created(self, user_id: str, email: str) -> bool:
                event = UserCreatedEvent(
                    event_type="user.created",
                    user_id=user_id,
                    email=email
                )
                return await self.publish_event(event, subject="user.created")
    """

    def __init__(
        self,
        nats_host: Optional[str] = None,
        nats_port: Optional[int] = None,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        service_name: Optional[str] = None,
    ):
        """
        Initialize event publisher.

        Args:
            nats_host: NATS service host
            nats_port: NATS service port (default: 4222)
            user_id: Default user ID for events
            organization_id: Default organization ID
            service_name: Name of the service publishing events
        """
        self.nats_client = NATSClient(
            host=nats_host,
            port=nats_port,
            user_id=user_id or service_name,
            organization_id=organization_id,
        )
        self.default_user_id = user_id
        self.default_org_id = organization_id
        self._service_name = service_name

    @abstractmethod
    def service_name(self) -> str:
        """
        Return the name of the service publishing events.

        This is used for logging and tracking event sources.
        """
        pass

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.aclose()

    async def aclose(self):
        """Close NATS connection (async)."""
        await self.nats_client.close()

    def close(self):
        """Close NATS connection (sync fallback).

        Prefer ``aclose()`` or ``async with`` instead.  This method
        creates a new event loop when none is running, which is safe
        for cleanup in synchronous teardown paths.  If a loop *is*
        already running, the close is scheduled as a task that will
        execute before the loop ends, but cannot be awaited here.
        """
        warnings.warn(
            "Sync close() is deprecated — use 'await aclose()' or 'async with'.",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            asyncio.get_running_loop()
            # We're inside a running loop — cannot block.  Best-effort.
            logger.warning(
                "BaseEventPublisher.close() called inside a running event loop; "
                "connection close is best-effort. Use aclose() instead."
            )
        except RuntimeError:
            # No running loop — safe to create one and block.
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self.nats_client.close())
            finally:
                loop.close()

    def _serialize_event(self, event: BaseEvent) -> bytes:
        """
        Serialize Pydantic event to JSON bytes.

        Args:
            event: Pydantic event model

        Returns:
            JSON bytes ready for NATS
        """
        # Set source service in metadata if not already set
        if hasattr(event, 'metadata') and event.metadata.source_service is None:
            event.metadata.source_service = self.service_name()

        # Use Pydantic's JSON serialization with custom encoders
        json_str = event.model_dump_json()
        return json_str.encode('utf-8')

    async def publish_event(
        self,
        event: BaseEvent,
        subject: str,
        headers: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Publish an event to NATS.

        Args:
            event: Event to publish (must extend BaseEvent)
            subject: NATS subject
            headers: Optional headers

        Returns:
            True if published successfully, False otherwise
        """
        try:
            # Serialize event
            data = self._serialize_event(event)

            # Add event type to headers
            if headers is None:
                headers = {}
            headers['event_type'] = event.event_type

            # Publish to NATS
            result = await self.nats_client.publish(
                subject=subject,
                data=data,
                headers=headers
            )

            if result and result.get('success'):
                logger.info(
                    f"[{self.service_name()}] Published event: {event.event_type} "
                    f"to subject: {subject}"
                )
                return True
            else:
                logger.error(
                    f"[{self.service_name()}] Failed to publish event: {result}"
                )
                return False

        except Exception as e:
            logger.error(
                f"[{self.service_name()}] Error publishing event {event.event_type}: {e}",
                exc_info=True
            )
            return False

    async def publish_raw(
        self,
        subject: str,
        data: bytes,
        headers: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Publish raw data to NATS (for advanced use cases).

        Args:
            subject: NATS subject
            data: Raw bytes to publish
            headers: Optional headers

        Returns:
            True if published successfully
        """
        try:
            result = await self.nats_client.publish(
                subject=subject,
                data=data,
                headers=headers
            )

            if result and result.get('success'):
                logger.info(f"[{self.service_name()}] Published to subject: {subject}")
                return True
            else:
                logger.error(f"[{self.service_name()}] Failed to publish: {result}")
                return False

        except Exception as e:
            logger.error(
                f"[{self.service_name()}] Error publishing to {subject}: {e}",
                exc_info=True
            )
            return False
