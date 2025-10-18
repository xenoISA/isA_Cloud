#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base Event Subscriber for All Microservices

Provides reusable event subscription infrastructure with:
- Idempotency handling
- Automatic retries
- Error handling
- Dead letter queue
- Monitoring hooks
"""

import logging
import asyncio
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime
from abc import ABC, abstractmethod
from decimal import Decimal

from ..nats_client import NATSClient
from .billing_events import BaseModel

logger = logging.getLogger(__name__)


class EventHandler(ABC):
    """
    Abstract base class for event handlers.

    Each service should implement handlers for specific event types.
    """

    @abstractmethod
    async def handle(self, event: BaseModel) -> bool:
        """
        Handle an event.

        Args:
            event: The event to handle

        Returns:
            True if handled successfully, False otherwise
        """
        pass

    @abstractmethod
    def event_type(self) -> str:
        """Return the event type this handler processes"""
        pass


class IdempotencyChecker:
    """
    Checks if an event has already been processed.

    This prevents duplicate processing of the same event.
    """

    def __init__(self, storage_backend: str = "memory"):
        """
        Initialize idempotency checker.

        Args:
            storage_backend: "memory", "redis", or "postgres"
        """
        self.storage = storage_backend
        self._memory_cache: Dict[str, datetime] = {}
        self._max_cache_size = 10000

    async def is_processed(self, event_id: str) -> bool:
        """
        Check if event has been processed.

        Args:
            event_id: Unique event identifier

        Returns:
            True if already processed
        """
        if self.storage == "memory":
            return event_id in self._memory_cache
        elif self.storage == "redis":
            # TODO: Implement Redis check
            return False
        elif self.storage == "postgres":
            # TODO: Implement PostgreSQL check
            return False
        return False

    async def mark_processed(self, event_id: str, result: Any = None):
        """
        Mark event as processed.

        Args:
            event_id: Unique event identifier
            result: Optional processing result
        """
        if self.storage == "memory":
            # Implement simple LRU-style eviction
            if len(self._memory_cache) >= self._max_cache_size:
                # Remove oldest entry
                oldest_key = next(iter(self._memory_cache))
                del self._memory_cache[oldest_key]

            self._memory_cache[event_id] = datetime.utcnow()
        elif self.storage == "redis":
            # TODO: Store in Redis with TTL
            pass
        elif self.storage == "postgres":
            # TODO: Store in PostgreSQL
            pass


class RetryPolicy:
    """
    Defines retry behavior for failed event processing.
    """

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: int = 1,
        max_delay: int = 60,
        exponential_backoff: bool = True
    ):
        """
        Initialize retry policy.

        Args:
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            exponential_backoff: Use exponential backoff
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_backoff = exponential_backoff

    def get_delay(self, attempt: int) -> int:
        """
        Calculate delay for retry attempt.

        Args:
            attempt: Retry attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        if self.exponential_backoff:
            delay = self.initial_delay * (2 ** attempt)
        else:
            delay = self.initial_delay

        return min(delay, self.max_delay)


class BaseEventSubscriber:
    """
    Base class for event subscribers in all microservices.

    Usage:
        class BillingEventSubscriber(BaseEventSubscriber):
            def __init__(self, nats_client, billing_service):
                super().__init__(
                    service_name="billing_service",
                    nats_client=nats_client
                )
                self.billing_service = billing_service
                self.register_handler(UsageEventHandler(billing_service))

            async def start(self):
                await self.subscribe("usage.recorded.*", queue="billing-workers")
    """

    def __init__(
        self,
        service_name: str,
        nats_client: NATSClient,
        idempotency_storage: str = "memory",
        retry_policy: Optional[RetryPolicy] = None
    ):
        """
        Initialize event subscriber.

        Args:
            service_name: Name of the service (for logging)
            nats_client: NATS client instance
            idempotency_storage: Storage backend for idempotency
            retry_policy: Retry policy (uses default if None)
        """
        self.service_name = service_name
        self.nats_client = nats_client
        self.idempotency = IdempotencyChecker(idempotency_storage)
        self.retry_policy = retry_policy or RetryPolicy()

        # Event handlers registry
        self.handlers: Dict[str, EventHandler] = {}

        # Metrics
        self.metrics = {
            "events_received": 0,
            "events_processed": 0,
            "events_failed": 0,
            "events_skipped_duplicate": 0,
            "total_processing_time": 0.0
        }

        # Active subscriptions
        self.subscriptions: List[str] = []

    def register_handler(self, handler: EventHandler):
        """
        Register an event handler.

        Args:
            handler: Event handler instance
        """
        event_type = handler.event_type()
        self.handlers[event_type] = handler
        logger.info(f"[{self.service_name}] Registered handler for {event_type}")

    async def subscribe(
        self,
        subject: str,
        queue: Optional[str] = None,
        durable: Optional[str] = None
    ):
        """
        Subscribe to a NATS subject.

        Args:
            subject: NATS subject pattern (e.g., "usage.recorded.*")
            queue: Queue group name (for load balancing)
            durable: Durable consumer name (survives restarts)
        """
        logger.info(f"[{self.service_name}] Subscribing to {subject}")

        # For now, we'll use the gRPC NATS client's basic subscribe
        # In production, this would use JetStream with queue and durable options

        # Note: The current NATSClient doesn't have a subscribe method exposed
        # We'll need to extend it or create a wrapper
        # For now, we'll mark this as TODO and return

        logger.warning(
            f"[{self.service_name}] NATS subscription setup - "
            f"requires JetStream consumer implementation"
        )

        self.subscriptions.append(subject)

    async def process_event(self, event_data: bytes, subject: str) -> bool:
        """
        Process an incoming event.

        This is the main processing pipeline:
        1. Deserialize event
        2. Check idempotency
        3. Find handler
        4. Execute handler with retries
        5. Mark as processed

        Args:
            event_data: Raw event data (JSON bytes)
            subject: NATS subject the event was published to

        Returns:
            True if processed successfully
        """
        start_time = datetime.utcnow()
        self.metrics["events_received"] += 1

        try:
            # 1. Deserialize event
            event = self._deserialize_event(event_data)
            if not event:
                logger.error(f"[{self.service_name}] Failed to deserialize event")
                self.metrics["events_failed"] += 1
                return False

            event_id = getattr(event, "event_id", None)
            event_type = getattr(event, "event_type", "unknown")

            logger.info(
                f"[{self.service_name}] Processing event {event_id} "
                f"type={event_type} subject={subject}"
            )

            # 2. Check idempotency
            if event_id and await self.idempotency.is_processed(event_id):
                logger.info(
                    f"[{self.service_name}] Event {event_id} already processed, skipping"
                )
                self.metrics["events_skipped_duplicate"] += 1
                return True

            # 3. Find handler
            handler = self.handlers.get(event_type)
            if not handler:
                logger.warning(
                    f"[{self.service_name}] No handler found for {event_type}"
                )
                return False

            # 4. Execute handler with retries
            success = await self._execute_with_retry(handler, event)

            if success:
                # 5. Mark as processed
                if event_id:
                    await self.idempotency.mark_processed(event_id)

                self.metrics["events_processed"] += 1

                # Record processing time
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                self.metrics["total_processing_time"] += elapsed

                logger.info(
                    f"[{self.service_name}] Successfully processed {event_id} "
                    f"in {elapsed:.3f}s"
                )
                return True
            else:
                self.metrics["events_failed"] += 1
                logger.error(
                    f"[{self.service_name}] Failed to process {event_id} "
                    f"after {self.retry_policy.max_retries} retries"
                )

                # Move to dead letter queue
                await self._move_to_dlq(event, subject, "max_retries_exceeded")
                return False

        except Exception as e:
            logger.error(
                f"[{self.service_name}] Unexpected error processing event: {e}",
                exc_info=True
            )
            self.metrics["events_failed"] += 1
            return False

    async def _execute_with_retry(
        self,
        handler: EventHandler,
        event: BaseModel
    ) -> bool:
        """
        Execute handler with retry logic.

        Args:
            handler: Event handler to execute
            event: Event to process

        Returns:
            True if successful
        """
        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                success = await handler.handle(event)
                if success:
                    return True

                # Handler returned False, retry
                if attempt < self.retry_policy.max_retries:
                    delay = self.retry_policy.get_delay(attempt)
                    logger.warning(
                        f"[{self.service_name}] Handler failed, "
                        f"retrying in {delay}s (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(delay)

            except Exception as e:
                logger.error(
                    f"[{self.service_name}] Handler error (attempt {attempt + 1}): {e}",
                    exc_info=True
                )

                if attempt < self.retry_policy.max_retries:
                    delay = self.retry_policy.get_delay(attempt)
                    await asyncio.sleep(delay)

        return False

    def _deserialize_event(self, event_data: bytes) -> Optional[BaseModel]:
        """
        Deserialize event from JSON bytes.

        Args:
            event_data: Raw JSON bytes

        Returns:
            Deserialized event or None
        """
        try:
            import json
            data = json.loads(event_data.decode('utf-8'))
            event_type = data.get("event_type")

            # Import event classes
            from .billing_events import (
                UsageEvent,
                BillingCalculatedEvent,
                TokensDeductedEvent,
                TokensInsufficientEvent,
                BillingErrorEvent
            )

            # Map event types to classes
            event_classes = {
                "usage.recorded": UsageEvent,
                "billing.calculated": BillingCalculatedEvent,
                "wallet.tokens.deducted": TokensDeductedEvent,
                "wallet.tokens.insufficient": TokensInsufficientEvent,
                "billing.failed": BillingErrorEvent
            }

            event_class = event_classes.get(event_type)
            if event_class:
                return event_class(**data)

            logger.warning(f"Unknown event type: {event_type}")
            return None

        except Exception as e:
            logger.error(f"Error deserializing event: {e}")
            return None

    async def _move_to_dlq(
        self,
        event: BaseModel,
        original_subject: str,
        reason: str
    ):
        """
        Move failed event to dead letter queue.

        Args:
            event: Failed event
            original_subject: Original NATS subject
            reason: Failure reason
        """
        try:
            dlq_subject = f"dlq.{original_subject}"
            dlq_data = {
                "original_event": event.model_dump() if hasattr(event, 'model_dump') else {},
                "original_subject": original_subject,
                "failure_reason": reason,
                "failed_at": datetime.utcnow().isoformat(),
                "service": self.service_name
            }

            import json
            dlq_bytes = json.dumps(dlq_data).encode('utf-8')

            # Publish to DLQ
            self.nats_client.publish(dlq_subject, dlq_bytes)

            logger.warning(
                f"[{self.service_name}] Moved event to DLQ: {dlq_subject}"
            )

        except Exception as e:
            logger.error(f"Error moving event to DLQ: {e}")

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get subscriber metrics.

        Returns:
            Dictionary of metrics
        """
        avg_processing_time = 0.0
        if self.metrics["events_processed"] > 0:
            avg_processing_time = (
                self.metrics["total_processing_time"] /
                self.metrics["events_processed"]
            )

        return {
            **self.metrics,
            "avg_processing_time_seconds": round(avg_processing_time, 3),
            "subscriptions": self.subscriptions
        }

    async def health_check(self) -> Dict[str, Any]:
        """
        Health check for subscriber.

        Returns:
            Health status
        """
        return {
            "service": self.service_name,
            "status": "healthy" if self.nats_client else "unhealthy",
            "subscriptions": len(self.subscriptions),
            "metrics": self.get_metrics()
        }
