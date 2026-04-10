"""
Billing event models for event-driven billing.

Usage events are transported over NATS. Control-plane operations such as
pricing, reservations, and reporting remain API-driven.
"""

import re
from enum import Enum
from typing import Optional, Dict, Any, Iterable, List
from datetime import datetime, timezone
from decimal import Decimal
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Event types for the billing system."""
    USAGE_RECORDED = "billing.usage.recorded"
    LEGACY_USAGE_RECORDED = "usage.recorded"

    # Billing events (published by billing_service)
    COST_CALCULATED = "billing.calculated"
    BILLING_FAILED = "billing.failed"

    # Wallet events (published by wallet_service)
    TOKENS_DEDUCTED = "wallet.tokens.deducted"
    TOKENS_INSUFFICIENT = "wallet.tokens.insufficient"

    # Product events (published by product_service)
    USAGE_METRICS_RECORDED = "product.usage.recorded"


class UnitType(str, Enum):
    """Unit types for different services."""
    TOKEN = "token"
    IMAGE = "image"
    MINUTE = "minute"
    HOUR = "hour"
    CHARACTER = "character"
    REQUEST = "request"
    URL = "url"
    BYTE = "byte"
    GB = "gb"
    GB_MONTH = "gb_month"
    EXECUTION = "execution"
    OPERATION = "operation"
    UNIT = "unit"
    SECOND = "second"


class BillingAccountType(str, Enum):
    """Canonical payer types."""
    USER = "user"
    ORGANIZATION = "organization"


class BillingSurface(str, Enum):
    """Customer-facing abstraction for a billing event."""
    ABSTRACT_SERVICE = "abstract_service"
    ADD_ON = "add_on"


class CostComponentType(str, Enum):
    """Underlying component classes bundled into an abstract service."""
    RUNTIME = "runtime"
    TOKEN_COMPUTE = "token_compute"
    STORAGE = "storage"
    NETWORK = "network"
    EXTERNAL_API = "external_api"


class CostComponent(BaseModel):
    """Underlying resource or external API component for a usage event."""
    component_id: str = Field(..., description="Stable component identifier")
    component_type: CostComponentType = Field(
        ..., description="Underlying resource or API class"
    )
    bundled: bool = Field(
        default=True,
        description="Whether the component is bundled into the abstract service price",
    )
    customer_visible: bool = Field(
        default=False,
        description="Whether the component is intentionally exposed to customers",
    )
    provider: Optional[str] = Field(
        default=None,
        description="Provider or implementation behind the component",
    )
    meter_type: Optional[str] = Field(
        default=None,
        description="Internal meter for the component when known",
    )
    unit_type: Optional[UnitType] = Field(
        default=None,
        description="Native unit used by the component when known",
    )
    usage_amount: Optional[Decimal] = Field(
        default=None,
        description="Underlying usage amount when the producer provides it",
    )
    notes: Optional[str] = None


# ====================
# Usage Events (Source: isA_Model, isA_Agent)
# ====================

class UsageEvent(BaseModel):
    """
    Published when any service uses a billable resource.

    Publishers: `isA_Model`, `isA_Agent`, `isA_MCP`, `isA_OS`, `isA_Data`,
    `storage_service`, and other usage producers.

    Subscribers: `billing_service`, `product_service` metrics consumers, and
    analytics consumers.

    Canonical NATS subject family: `billing.usage.recorded.>`
    """
    event_type: str = Field(default=EventType.USAGE_RECORDED.value)
    event_id: str = Field(default_factory=lambda: f"evt_{datetime.now(timezone.utc).timestamp()}")
    schema_version: str = Field(default="1.0", description="Billing usage event schema version")

    # Payer and actor context
    user_id: str = Field(..., description="User who triggered the usage")
    actor_user_id: Optional[str] = Field(None, description="Human actor responsible for the action")
    billing_account_type: Optional[BillingAccountType] = Field(
        None, description="Canonical payer type"
    )
    billing_account_id: Optional[str] = Field(
        None, description="Canonical payer identifier"
    )
    organization_id: Optional[str] = Field(None, description="Organization context")
    agent_id: Optional[str] = Field(None, description="Agent that executed the work")
    subscription_id: Optional[str] = Field(None, description="Active subscription")

    # Billable identity
    product_id: str = Field(..., description="Product being used (gpt-4, dall-e-3, etc)")
    service_type: Optional[str] = Field(None, description="Canonical service category")
    operation_type: Optional[str] = Field(None, description="Canonical operation type")
    source_service: Optional[str] = Field(None, description="Originating service name")
    resource_name: Optional[str] = Field(None, description="Resource name within the source service")
    meter_type: Optional[str] = Field(None, description="Billing meter type")
    usage_amount: Decimal = Field(..., description="Amount used in native units")
    unit_type: UnitType = Field(..., description="Unit type (token, image, etc)")

    # Session tracking
    session_id: Optional[str] = Field(None, description="User session ID")
    request_id: Optional[str] = Field(None, description="Request trace ID")

    # Metadata
    usage_details: Dict[str, Any] = Field(default_factory=dict, description="Additional context")
    billing_surface: BillingSurface = Field(
        default=BillingSurface.ABSTRACT_SERVICE,
        description="Customer-facing abstraction for the invoiceable event",
    )
    cost_components: List[CostComponent] = Field(
        default_factory=list,
        description="Bundled underlying resource or external API components",
    )
    credits_used: Optional[Decimal] = Field(None, description="Credits already computed upstream")
    cost_usd: Optional[Decimal] = Field(None, description="USD cost already computed upstream")
    credit_consumption_handled: bool = Field(
        False,
        description="Whether the producer already consumed or reconciled payer credits",
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    event_id: str = Field(default_factory=lambda: f"evt_{datetime.now(timezone.utc).timestamp()}")

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

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    event_id: str = Field(default_factory=lambda: f"evt_{datetime.now(timezone.utc).timestamp()}")

    user_id: str
    usage_event_id: str
    product_id: str

    error_code: str = Field(..., description="Error code (PRICING_NOT_FOUND, etc)")
    error_message: str
    retry_count: int = 0

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    event_id: str = Field(default_factory=lambda: f"evt_{datetime.now(timezone.utc).timestamp()}")

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

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    event_id: str = Field(default_factory=lambda: f"evt_{datetime.now(timezone.utc).timestamp()}")

    user_id: str
    billing_record_id: str

    tokens_required: Decimal
    tokens_available: Decimal
    tokens_deficit: Decimal

    suggested_action: str = "upgrade_plan"  # or "purchase_tokens"

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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


_INVALID_SUBJECT_TOKEN = re.compile(r"[^A-Za-z0-9_-]+")


def _sanitize_subject_token(value: Optional[str], fallback: str) -> str:
    """Return a NATS-safe subject token."""
    if not value:
        return fallback
    token = _INVALID_SUBJECT_TOKEN.sub("-", value.strip().lower()).strip("-")
    return token or fallback


def _usage_subject_tokens(event: UsageEvent) -> Iterable[str]:
    """Build canonical subject tokens for a usage event."""
    primary = (
        event.source_service
        or event.service_type
        or event.product_id
    )
    yield _sanitize_subject_token(primary, "unknown")

    secondary = event.resource_name
    if not secondary:
        details = event.usage_details or {}
        secondary = (
            details.get("resource_name")
            or details.get("tool_name")
            or details.get("model")
            or details.get("operation_type")
            or details.get("operation")
        )

    if secondary:
        yield _sanitize_subject_token(str(secondary), "resource")


def get_nats_subject(event: BaseModel) -> str:
    """
    Get the NATS subject for an event.

    Returns:
        - billing.usage.recorded.<source>[.<resource>] for UsageEvent
        - billing.calculated for BillingCalculatedEvent
        - wallet.tokens.deducted for TokensDeductedEvent
        - etc.
    """
    if isinstance(event, UsageEvent):
        return ".".join(("billing", "usage", "recorded", *_usage_subject_tokens(event)))
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
