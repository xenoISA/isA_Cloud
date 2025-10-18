"""
Billing Event Models for Event-Driven Architecture

All services use NATS to communicate via events instead of direct HTTP calls.
This provides loose coupling, better scalability, and fault tolerance.
"""

from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Event types for billing system"""
    # Usage events (published by isA_Model, isA_Agent, etc.)
    USAGE_RECORDED = "usage.recorded"

    # Billing events (published by billing_service)
    COST_CALCULATED = "billing.calculated"
    BILLING_FAILED = "billing.failed"

    # Wallet events (published by wallet_service)
    TOKENS_DEDUCTED = "wallet.tokens.deducted"
    TOKENS_INSUFFICIENT = "wallet.tokens.insufficient"

    # Product events (published by product_service)
    USAGE_METRICS_RECORDED = "product.usage.recorded"


class UnitType(str, Enum):
    """Unit types for different services"""
    TOKEN = "token"           # LLM tokens (GPT-4, GPT-3.5, embeddings)
    IMAGE = "image"           # Image generation (DALL-E, Stable Diffusion)
    MINUTE = "minute"         # Audio processing (STT, TTS)
    CHARACTER = "character"   # TTS character count
    REQUEST = "request"       # API calls (agent tools, searches)
    BYTE = "byte"            # Storage (Minio, S3)
    SECOND = "second"        # Video processing


# ====================
# Usage Events (Source: isA_Model, isA_Agent)
# ====================

class UsageEvent(BaseModel):
    """
    Published when any service uses a billable resource.

    Publishers: isA_Model, isA_Agent, storage_service, etc.
    Subscribers: billing_service, product_service (for metrics)

    NATS Subject: usage.recorded.{product_id}
    Example: usage.recorded.gpt-4, usage.recorded.dall-e-3
    """
    event_type: str = EventType.USAGE_RECORDED
    event_id: str = Field(default_factory=lambda: f"evt_{datetime.utcnow().timestamp()}")

    # User context
    user_id: str = Field(..., description="User who triggered the usage")
    organization_id: Optional[str] = Field(None, description="Organization context")
    subscription_id: Optional[str] = Field(None, description="Active subscription")

    # Usage details
    product_id: str = Field(..., description="Product being used (gpt-4, dall-e-3, etc)")
    usage_amount: Decimal = Field(..., description="Amount used in native units")
    unit_type: UnitType = Field(..., description="Unit type (token, image, etc)")

    # Session tracking
    session_id: Optional[str] = Field(None, description="User session ID")
    request_id: Optional[str] = Field(None, description="Request trace ID")

    # Metadata
    usage_details: Dict[str, Any] = Field(default_factory=dict, description="Additional context")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat()
        }


# ====================
# Billing Events (Source: billing_service)
# ====================

class BillingCalculatedEvent(BaseModel):
    """
    Published after billing_service calculates the cost.

    Publisher: billing_service
    Subscribers: wallet_service (to deduct tokens), analytics_service

    NATS Subject: billing.calculated
    """
    event_type: str = EventType.COST_CALCULATED
    event_id: str = Field(default_factory=lambda: f"evt_{datetime.utcnow().timestamp()}")

    # References
    user_id: str
    billing_record_id: str = Field(..., description="Created billing record ID")
    usage_event_id: str = Field(..., description="Original usage event ID")

    # Product info
    product_id: str
    actual_usage: Decimal = Field(..., description="Original usage amount")
    unit_type: UnitType

    # Cost calculation
    token_equivalent: Decimal = Field(..., description="Normalized to token equivalents")
    cost_usd: Decimal = Field(..., description="Actual USD cost")
    unit_price: Decimal = Field(..., description="Price per unit in USD")

    # Token conversion rate
    token_conversion_rate: Decimal = Field(
        ...,
        description="How many tokens this represents (e.g., 1 image = 1333 tokens)"
    )

    # Billing status
    is_free_tier: bool = False
    is_included_in_subscription: bool = False

    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat()
        }


class BillingErrorEvent(BaseModel):
    """
    Published when billing calculation fails.

    Publisher: billing_service
    Subscribers: notification_service, monitoring_service

    NATS Subject: billing.failed
    """
    event_type: str = EventType.BILLING_FAILED
    event_id: str = Field(default_factory=lambda: f"evt_{datetime.utcnow().timestamp()}")

    user_id: str
    usage_event_id: str
    product_id: str

    error_code: str = Field(..., description="Error code (PRICING_NOT_FOUND, etc)")
    error_message: str
    retry_count: int = 0

    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ====================
# Wallet Events (Source: wallet_service)
# ====================

class TokensDeductedEvent(BaseModel):
    """
    Published after wallet_service successfully deducts tokens.

    Publisher: wallet_service
    Subscribers: analytics_service, notification_service

    NATS Subject: wallet.tokens.deducted
    """
    event_type: str = EventType.TOKENS_DEDUCTED
    event_id: str = Field(default_factory=lambda: f"evt_{datetime.utcnow().timestamp()}")

    # References
    user_id: str
    billing_record_id: str
    transaction_id: str = Field(..., description="Wallet transaction ID")

    # Token info
    tokens_deducted: Decimal
    balance_before: Decimal
    balance_after: Decimal

    # Quota tracking
    monthly_quota: Optional[Decimal] = Field(None, description="Monthly token quota")
    monthly_used: Optional[Decimal] = Field(None, description="Tokens used this month")
    percentage_used: Optional[float] = Field(None, description="% of monthly quota used")

    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat()
        }


class TokensInsufficientEvent(BaseModel):
    """
    Published when user doesn't have enough tokens.

    Publisher: wallet_service
    Subscribers: notification_service (alert user), billing_service (mark failed)

    NATS Subject: wallet.tokens.insufficient
    """
    event_type: str = EventType.TOKENS_INSUFFICIENT
    event_id: str = Field(default_factory=lambda: f"evt_{datetime.utcnow().timestamp()}")

    user_id: str
    billing_record_id: str

    tokens_required: Decimal
    tokens_available: Decimal
    tokens_deficit: Decimal

    suggested_action: str = "upgrade_plan"  # or "purchase_tokens"

    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat()
        }


# ====================
# Helper Functions
# ====================

def create_usage_event(
    user_id: str,
    product_id: str,
    usage_amount: Decimal,
    unit_type: UnitType,
    **kwargs
) -> UsageEvent:
    """
    Helper to create a usage event.

    Usage:
        event = create_usage_event(
            user_id="user_123",
            product_id="gpt-4",
            usage_amount=Decimal("1500"),
            unit_type=UnitType.TOKEN,
            session_id="session_abc"
        )
    """
    return UsageEvent(
        user_id=user_id,
        product_id=product_id,
        usage_amount=usage_amount,
        unit_type=unit_type,
        **kwargs
    )


def get_nats_subject(event: BaseModel) -> str:
    """
    Get the NATS subject for an event.

    Returns:
        - usage.recorded.{product_id} for UsageEvent
        - billing.calculated for BillingCalculatedEvent
        - wallet.tokens.deducted for TokensDeductedEvent
        - etc.
    """
    if isinstance(event, UsageEvent):
        return f"usage.recorded.{event.product_id}"
    elif isinstance(event, BillingCalculatedEvent):
        return "billing.calculated"
    elif isinstance(event, TokensDeductedEvent):
        return "wallet.tokens.deducted"
    elif isinstance(event, TokensInsufficientEvent):
        return "wallet.tokens.insufficient"
    elif isinstance(event, BillingErrorEvent):
        return "billing.failed"
    else:
        return "unknown.event"
