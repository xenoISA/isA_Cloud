# Generic Event-Driven Architecture Framework

## Overview

This module provides **generic base classes** for building event-driven microservices using NATS. It contains **NO business logic** - only infrastructure.

Business-specific implementations (like billing events, user events, etc.) should **extend these base classes** in their respective projects.

## Architecture

```
isA_Cloud/grpc_clients/events/          # Generic infrastructure (THIS MODULE)
├── base_event_models.py                # BaseEvent, EventMetadata
├── base_event_publisher.py             # BaseEventPublisher
├── base_event_subscriber.py            # BaseEventSubscriber, EventHandler
└── __init__.py

isA_user/core/events/                   # Business implementation (BILLING)
├── billing_events.py                   # UsageEvent, BillingCalculatedEvent (extends BaseEvent)
├── event_publisher.py                  # BillingEventPublisher (extends BaseEventPublisher)
└── README.md

isA_Model/events/                       # Business implementation (AI MODEL)
├── model_events.py                     # InferenceEvent, ModelLoadedEvent (extends BaseEvent)
├── event_publisher.py                  # ModelEventPublisher (extends BaseEventPublisher)
└── README.md
```

## Components

### 1. Base Event Models

**File:** `base_event_models.py`

Provides:
- `BaseEvent` - Base class for all events
- `EventMetadata` - Standard metadata (event_id, timestamp, source_service, etc.)
- Helper functions: `create_event_id()`, `get_nats_subject_from_event_type()`

**Usage:**

```python
from grpc_clients.events import BaseEvent, EventMetadata

class UserCreatedEvent(BaseEvent):
    event_type: str = "user.created"
    user_id: str
    email: str
    username: str

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
```

### 2. Base Event Publisher

**File:** `base_event_publisher.py`

Provides:
- `BaseEventPublisher` - Abstract base class for event publishers
- NATS connection management
- Event serialization
- Context manager support

**Usage:**

```python
from grpc_clients.events import BaseEventPublisher

class UserEventPublisher(BaseEventPublisher):
    def service_name(self) -> str:
        return "user_service"

    async def publish_user_created(
        self,
        user_id: str,
        email: str,
        username: str
    ) -> bool:
        event = UserCreatedEvent(
            event_type="user.created",
            user_id=user_id,
            email=email,
            username=username
        )
        return await self.publish_event(
            event=event,
            subject="user.created"
        )

# Use it
async with UserEventPublisher(nats_host='localhost', nats_port=50056) as publisher:
    await publisher.publish_user_created(
        user_id="user_123",
        email="test@example.com",
        username="testuser"
    )
```

### 3. Base Event Subscriber

**File:** `base_event_subscriber.py`

Provides:
- `BaseEventSubscriber` - Base class for event consumers
- `EventHandler` - Abstract handler interface
- `IdempotencyChecker` - Prevent duplicate processing
- `RetryPolicy` - Automatic retry with exponential backoff

**Usage:**

```python
from grpc_clients.events import BaseEventSubscriber, EventHandler

class UserCreatedEventHandler(EventHandler):
    def __init__(self, user_service):
        self.user_service = user_service

    def event_type(self) -> str:
        return "user.created"

    async def handle(self, event: UserCreatedEvent) -> bool:
        # Process event
        print(f"User created: {event.user_id}")
        return True

class UserEventSubscriber(BaseEventSubscriber):
    def __init__(self, user_service, nats_client):
        super().__init__("user_service", nats_client)
        self.register_handler(UserCreatedEventHandler(user_service))

    async def start(self):
        await self.subscribe(
            subject="user.created",
            queue="user-workers",
            durable="user-consumer"
        )
```

## Integration Guide

### For isA_Model Project

1. **Create model-specific events:**

```python
# isA_Model/events/model_events.py
from grpc_clients.events import BaseEvent
from decimal import Decimal

class InferenceEvent(BaseEvent):
    event_type: str = "inference.completed"
    model_name: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    latency_ms: float
```

2. **Create model event publisher:**

```python
# isA_Model/events/event_publisher.py
from grpc_clients.events import BaseEventPublisher
from .model_events import InferenceEvent

class ModelEventPublisher(BaseEventPublisher):
    def service_name(self) -> str:
        return "isa_model"

    async def publish_inference(
        self,
        user_id: str,
        model_name: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal
    ) -> bool:
        event = InferenceEvent(
            event_type="inference.completed",
            user_id=user_id,
            model_name=model_name,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd
        )
        return await self.publish_event(
            event=event,
            subject=f"inference.completed.{model_name}"
        )
```

3. **Use in inference code:**

```python
# isA_Model/isa_model/inference/services/base_service.py
from events.event_publisher import ModelEventPublisher

class BaseInferenceService:
    def __init__(self):
        self.event_publisher = ModelEventPublisher(
            nats_host='localhost',
            nats_port=50056
        )

    async def generate(self, prompt: str, user_id: str):
        # Run inference
        result = await self.model.generate(prompt)

        # Publish event
        await self.event_publisher.publish_inference(
            user_id=user_id,
            model_name=self.model_name,
            provider=self.provider_name,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=result.cost_usd
        )

        return result
```

## Key Principles

1. **isA_Cloud/grpc_clients/events/** = Generic infrastructure only
   - No business logic
   - Reusable across all projects
   - Pure base classes

2. **Each project** creates its own event implementations
   - Extends BaseEvent for domain events
   - Extends BaseEventPublisher for publishing
   - Extends BaseEventSubscriber for consuming

3. **Separation of concerns**
   - Infrastructure (isA_Cloud): HOW to publish/subscribe
   - Business logic (isA_user, isA_Model): WHAT events to publish

## Installation

### Option 1: Add to PYTHONPATH

```bash
export PYTHONPATH="/Users/xenodennis/Documents/Fun/isA_Cloud:$PYTHONPATH"
```

### Option 2: Development Install

```bash
cd /Users/xenodennis/Documents/Fun/isA_Cloud
pip install -e .
```

### Option 3: Symlink (Quick)

```bash
ln -s /Users/xenodennis/Documents/Fun/isA_Cloud/grpc_clients /Users/xenodennis/Documents/Fun/isA_Model/grpc_clients
```

## Examples

See:
- `isA_user/core/events/` - Billing event implementation
- `isA_user/microservices/billing_service/events/` - Billing event handlers
- `isA_user/microservices/wallet_service/events/` - Wallet event handlers

## Features

- ✅ Generic base classes for events
- ✅ NATS integration via gRPC
- ✅ Automatic idempotency checking
- ✅ Retry with exponential backoff
- ✅ Dead letter queue support
- ✅ Context manager support
- ✅ Type hints throughout
- ✅ Pydantic validation

## Next Steps

1. Each service should create its own `events/` directory
2. Define domain-specific events extending `BaseEvent`
3. Create service-specific publisher extending `BaseEventPublisher`
4. Create event handlers extending `EventHandler`
5. Register handlers in subscriber extending `BaseEventSubscriber`
