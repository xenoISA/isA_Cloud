#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base Event Models

Generic event models that can be extended by business-specific implementations.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, Field


class EventMetadata(BaseModel):
    """
    Standard metadata for all events.

    This provides consistent tracking across all event types.
    """
    event_id: str = Field(
        default_factory=lambda: f"evt_{datetime.utcnow().timestamp()}",
        description="Unique event identifier"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Event creation timestamp"
    )
    source_service: Optional[str] = Field(
        None,
        description="Service that generated this event"
    )
    correlation_id: Optional[str] = Field(
        None,
        description="ID to correlate related events"
    )
    causation_id: Optional[str] = Field(
        None,
        description="ID of the event that caused this event"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class BaseEvent(BaseModel):
    """
    Base class for all domain events.

    Extend this for your specific event types.

    Example:
        class UserCreatedEvent(BaseEvent):
            event_type: str = "user.created"
            user_id: str
            email: str

            class Config:
                json_encoders = {
                    datetime: lambda v: v.isoformat()
                }
    """
    event_type: str = Field(..., description="Type of event (e.g., 'user.created')")
    metadata: EventMetadata = Field(default_factory=EventMetadata)

    # Common context fields
    user_id: Optional[str] = Field(None, description="User who triggered the event")
    organization_id: Optional[str] = Field(None, description="Organization context")
    session_id: Optional[str] = Field(None, description="Session context")
    request_id: Optional[str] = Field(None, description="Request trace ID")

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat()
        }


def create_event_id() -> str:
    """Generate a unique event ID"""
    import uuid
    return f"evt_{uuid.uuid4().hex}"


def get_nats_subject_from_event_type(event_type: str, entity_id: Optional[str] = None) -> str:
    """
    Generate NATS subject from event type.

    Args:
        event_type: Event type string (e.g., "user.created", "order.updated")
        entity_id: Optional entity ID to append to subject

    Returns:
        NATS subject string

    Examples:
        get_nats_subject_from_event_type("user.created")
        # Returns: "user.created"

        get_nats_subject_from_event_type("usage.recorded", "gpt-4")
        # Returns: "usage.recorded.gpt-4"
    """
    if entity_id:
        return f"{event_type}.{entity_id}"
    return event_type
