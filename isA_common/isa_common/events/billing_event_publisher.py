#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NATS Event Publisher for Billing System

Provides helper functions to publish billing events to NATS message bus.
"""

import json
import logging
from typing import Optional, Dict, Any, TYPE_CHECKING
from decimal import Decimal
from datetime import datetime

from ..nats_client import NATSClient
from .billing_events import (
    UsageEvent,
    BillingCalculatedEvent,
    TokensDeductedEvent,
    TokensInsufficientEvent,
    BillingErrorEvent,
    get_nats_subject
)

if TYPE_CHECKING:
    from ..consul_client import ConsulRegistry

logger = logging.getLogger(__name__)


class BillingEventPublisher:
    """
    Publishes billing events to NATS message bus.

    Usage:
        publisher = BillingEventPublisher(nats_host='localhost', nats_port=50056)

        # Publish usage event
        await publisher.publish_usage(
            user_id="user_123",
            product_id="mcp-tool-web-search",
            usage_amount=1,
            unit_type="request",
            usage_details={"model_cost_usd": 0.0015, "tokens": 500}
        )
    """

    def __init__(
        self,
        nats_host: Optional[str] = None,
        nats_port: Optional[int] = None,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        enable_compression: bool = False,
        consul_registry: Optional['ConsulRegistry'] = None
    ):
        """
        Initialize event publisher.

        Args:
            nats_host: NATS service host (optional, will use Consul discovery if not provided)
            nats_port: NATS service gRPC port (optional, will use Consul discovery if not provided)
            user_id: Default user ID for events
            organization_id: Default organization ID
            enable_compression: Enable message compression
            consul_registry: ConsulRegistry instance for service discovery (optional)
        """
        self.nats_client = NATSClient(
            host=nats_host,
            port=nats_port,
            user_id=user_id,
            organization_id=organization_id,
            enable_compression=enable_compression,
            consul_registry=consul_registry
        )
        self.default_user_id = user_id
        self.default_org_id = organization_id
        self.consul_registry = consul_registry

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.aclose()

    def close(self):
        """Close NATS connection"""
        if hasattr(self.nats_client, 'close'):
            self.nats_client.close()

    async def aclose(self):
        """Async close NATS connection"""
        if hasattr(self.nats_client, 'aclose'):
            await self.nats_client.aclose()
        elif hasattr(self.nats_client, 'close'):
            self.nats_client.close()

    def _serialize_event(self, event) -> bytes:
        """
        Serialize Pydantic event to JSON bytes.

        Args:
            event: Pydantic event model

        Returns:
            JSON bytes ready for NATS
        """
        # Use Pydantic's JSON serialization with custom encoders
        json_str = event.model_dump_json()
        return json_str.encode('utf-8')

    async def publish_usage(
        self,
        user_id: str,
        product_id: str,
        usage_amount: Decimal,
        unit_type: str,
        organization_id: Optional[str] = None,
        subscription_id: Optional[str] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        usage_details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Publish a usage event.

        Args:
            user_id: User who triggered the usage
            product_id: Product being used (e.g., "mcp-tool-web-search", "gpt-4")
            usage_amount: Amount used in native units
            unit_type: Unit type (token, image, minute, request, etc.)
            organization_id: Organization context
            subscription_id: Active subscription
            session_id: User session ID
            request_id: Request trace ID
            usage_details: Additional context (model costs, metadata, etc.)

        Returns:
            True if published successfully, False otherwise

        Example:
            await publisher.publish_usage(
                user_id="user_123",
                product_id="mcp-tool-web-search",
                usage_amount=Decimal("1"),
                unit_type="request",
                usage_details={
                    "model_cost_usd": 0.0015,
                    "model_tokens": 500,
                    "model_product": "gpt-4",
                    "tool_result_size": 1024
                }
            )
        """
        try:
            event = UsageEvent(
                user_id=user_id,
                product_id=product_id,
                usage_amount=usage_amount,
                unit_type=unit_type,
                organization_id=organization_id or self.default_org_id,
                subscription_id=subscription_id,
                session_id=session_id,
                request_id=request_id,
                usage_details=usage_details or {}
            )

            subject = get_nats_subject(event)
            data = self._serialize_event(event)

            result = self.nats_client.publish(
                subject=subject,
                data=data,
                headers={"event_type": "usage.recorded"}
            )

            if result and result.get('success'):
                logger.info(f"Published usage event: {product_id} for user {user_id}")
                return True
            else:
                logger.error(f"Failed to publish usage event: {result}")
                return False

        except Exception as e:
            logger.error(f"Error publishing usage event: {e}", exc_info=True)
            return False

    async def publish_billing_calculated(
        self,
        user_id: str,
        billing_record_id: str,
        usage_event_id: str,
        product_id: str,
        actual_usage: Decimal,
        unit_type: str,
        token_equivalent: Decimal,
        cost_usd: Decimal,
        unit_price: Decimal,
        token_conversion_rate: Decimal,
        is_free_tier: bool = False,
        is_included_in_subscription: bool = False
    ) -> bool:
        """
        Publish a billing calculated event.

        Args:
            user_id: User ID
            billing_record_id: Created billing record ID
            usage_event_id: Original usage event ID
            product_id: Product ID
            actual_usage: Original usage amount
            unit_type: Unit type
            token_equivalent: Normalized to token equivalents
            cost_usd: Actual USD cost
            unit_price: Price per unit in USD
            token_conversion_rate: How many tokens this represents
            is_free_tier: Whether this is free tier usage
            is_included_in_subscription: Whether included in subscription

        Returns:
            True if published successfully
        """
        try:
            event = BillingCalculatedEvent(
                user_id=user_id,
                billing_record_id=billing_record_id,
                usage_event_id=usage_event_id,
                product_id=product_id,
                actual_usage=actual_usage,
                unit_type=unit_type,
                token_equivalent=token_equivalent,
                cost_usd=cost_usd,
                unit_price=unit_price,
                token_conversion_rate=token_conversion_rate,
                is_free_tier=is_free_tier,
                is_included_in_subscription=is_included_in_subscription
            )

            subject = get_nats_subject(event)
            data = self._serialize_event(event)

            result = self.nats_client.publish(
                subject=subject,
                data=data,
                headers={"event_type": "billing.calculated"}
            )

            if result and result.get('success'):
                logger.info(f"Published billing calculated event: {billing_record_id}")
                return True
            else:
                logger.error(f"Failed to publish billing calculated event: {result}")
                return False

        except Exception as e:
            logger.error(f"Error publishing billing calculated event: {e}", exc_info=True)
            return False

    async def publish_tokens_deducted(
        self,
        user_id: str,
        billing_record_id: str,
        transaction_id: str,
        tokens_deducted: Decimal,
        balance_before: Decimal,
        balance_after: Decimal,
        monthly_quota: Optional[Decimal] = None,
        monthly_used: Optional[Decimal] = None,
        percentage_used: Optional[float] = None
    ) -> bool:
        """
        Publish a tokens deducted event.

        Args:
            user_id: User ID
            billing_record_id: Billing record ID
            transaction_id: Wallet transaction ID
            tokens_deducted: Tokens deducted
            balance_before: Balance before deduction
            balance_after: Balance after deduction
            monthly_quota: Monthly token quota
            monthly_used: Tokens used this month
            percentage_used: % of monthly quota used

        Returns:
            True if published successfully
        """
        try:
            event = TokensDeductedEvent(
                user_id=user_id,
                billing_record_id=billing_record_id,
                transaction_id=transaction_id,
                tokens_deducted=tokens_deducted,
                balance_before=balance_before,
                balance_after=balance_after,
                monthly_quota=monthly_quota,
                monthly_used=monthly_used,
                percentage_used=percentage_used
            )

            subject = get_nats_subject(event)
            data = self._serialize_event(event)

            result = self.nats_client.publish(
                subject=subject,
                data=data,
                headers={"event_type": "wallet.tokens.deducted"}
            )

            if result and result.get('success'):
                logger.info(f"Published tokens deducted event: {transaction_id}")
                return True
            else:
                logger.error(f"Failed to publish tokens deducted event: {result}")
                return False

        except Exception as e:
            logger.error(f"Error publishing tokens deducted event: {e}", exc_info=True)
            return False

    async def publish_tokens_insufficient(
        self,
        user_id: str,
        billing_record_id: str,
        tokens_required: Decimal,
        tokens_available: Decimal,
        suggested_action: str = "upgrade_plan"
    ) -> bool:
        """
        Publish a tokens insufficient event.

        Args:
            user_id: User ID
            billing_record_id: Billing record ID
            tokens_required: Tokens required
            tokens_available: Tokens available
            suggested_action: Suggested action (upgrade_plan, purchase_tokens)

        Returns:
            True if published successfully
        """
        try:
            tokens_deficit = tokens_required - tokens_available

            event = TokensInsufficientEvent(
                user_id=user_id,
                billing_record_id=billing_record_id,
                tokens_required=tokens_required,
                tokens_available=tokens_available,
                tokens_deficit=tokens_deficit,
                suggested_action=suggested_action
            )

            subject = get_nats_subject(event)
            data = self._serialize_event(event)

            result = self.nats_client.publish(
                subject=subject,
                data=data,
                headers={"event_type": "wallet.tokens.insufficient"}
            )

            if result and result.get('success'):
                logger.info(f"Published tokens insufficient event for user {user_id}")
                return True
            else:
                logger.error(f"Failed to publish tokens insufficient event: {result}")
                return False

        except Exception as e:
            logger.error(f"Error publishing tokens insufficient event: {e}", exc_info=True)
            return False

    async def publish_billing_error(
        self,
        user_id: str,
        usage_event_id: str,
        product_id: str,
        error_code: str,
        error_message: str,
        retry_count: int = 0
    ) -> bool:
        """
        Publish a billing error event.

        Args:
            user_id: User ID
            usage_event_id: Usage event ID
            product_id: Product ID
            error_code: Error code (PRICING_NOT_FOUND, etc.)
            error_message: Error message
            retry_count: Retry count

        Returns:
            True if published successfully
        """
        try:
            event = BillingErrorEvent(
                user_id=user_id,
                usage_event_id=usage_event_id,
                product_id=product_id,
                error_code=error_code,
                error_message=error_message,
                retry_count=retry_count
            )

            subject = get_nats_subject(event)
            data = self._serialize_event(event)

            result = self.nats_client.publish(
                subject=subject,
                data=data,
                headers={"event_type": "billing.failed"}
            )

            if result and result.get('success'):
                logger.warning(f"Published billing error event: {error_code}")
                return True
            else:
                logger.error(f"Failed to publish billing error event: {result}")
                return False

        except Exception as e:
            logger.error(f"Error publishing billing error event: {e}", exc_info=True)
            return False


# Convenience function for quick usage event publishing
async def publish_usage_event(
    user_id: str,
    product_id: str,
    usage_amount: Decimal,
    unit_type: str,
    nats_host: str = 'localhost',
    nats_port: int = 50056,
    **kwargs
) -> bool:
    """
    Quick helper to publish a usage event.

    Example:
        from core.events.event_publisher import publish_usage_event

        success = await publish_usage_event(
            user_id="user_123",
            product_id="mcp-tool-web-search",
            usage_amount=Decimal("1"),
            unit_type="request",
            usage_details={"model_cost": 0.0015}
        )
    """
    async with BillingEventPublisher(
        nats_host=nats_host,
        nats_port=nats_port,
        user_id=user_id
    ) as publisher:
        return await publisher.publish_usage(
            user_id=user_id,
            product_id=product_id,
            usage_amount=usage_amount,
            unit_type=unit_type,
            **kwargs
        )
