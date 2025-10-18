"""
Generic Event-Driven Architecture Components

Provides base classes for building event-driven microservices using NATS.
Business-specific implementations should extend these base classes.
"""

from .base_event_models import BaseEvent, EventMetadata
from .base_event_publisher import BaseEventPublisher
from .base_event_subscriber import BaseEventSubscriber, EventHandler, IdempotencyChecker, RetryPolicy

# Billing-specific event implementations
from .billing_events import (
    EventType,
    UnitType,
    UsageEvent,
    BillingCalculatedEvent,
    TokensDeductedEvent,
    TokensInsufficientEvent,
    BillingErrorEvent,
    create_usage_event,
    get_nats_subject
)
from .billing_event_publisher import (
    BillingEventPublisher,
    publish_usage_event
)

__all__ = [
    # Base event models
    'BaseEvent',
    'EventMetadata',

    # Base publisher
    'BaseEventPublisher',

    # Base subscriber
    'BaseEventSubscriber',
    'EventHandler',
    'IdempotencyChecker',
    'RetryPolicy',

    # Billing event types
    'EventType',
    'UnitType',

    # Billing event models
    'UsageEvent',
    'BillingCalculatedEvent',
    'TokensDeductedEvent',
    'TokensInsufficientEvent',
    'BillingErrorEvent',

    # Billing helper functions
    'create_usage_event',
    'get_nats_subject',

    # Billing publishers
    'BillingEventPublisher',
    'publish_usage_event',
]
