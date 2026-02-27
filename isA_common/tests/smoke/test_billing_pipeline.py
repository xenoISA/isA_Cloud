"""
Billing pipeline end-to-end smoke tests.

Validates the full billing flow across services:

    isA_Model (:8082) → BillingMiddleware → subscription_service (:8228)
    → inference → NATS → billing_service (:8216) → credit deduction

Requirements:
    - All four services running (model, billing, subscription, NATS)
    - SMOKE_USER_ID has an active subscription with credits
    - SMOKE_BROKE_USER_ID has zero credits

Run:
    pytest tests/smoke/ -m smoke -v
"""

import asyncio
import time

import httpx
import pytest

pytestmark = [pytest.mark.smoke, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_credit_balance(
    subscription_url: str,
    user_id: str,
    org_id: str = "",
) -> dict:
    """Fetch credit balance from subscription_service."""
    params = {"user_id": user_id}
    if org_id:
        params["organization_id"] = org_id
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{subscription_url}/api/v1/subscriptions/credits/balance",
            params=params,
        )
        resp.raise_for_status()
        return resp.json()


async def _get_billing_records(
    billing_url: str,
    user_id: str,
    limit: int = 10,
) -> list:
    """Fetch recent billing records from billing_service."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{billing_url}/api/v1/billing/records/user/{user_id}",
            params={"limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        # Handle both list response and envelope response
        if isinstance(data, list):
            return data
        return data.get("records", data.get("data", []))


async def _invoke_model(
    model_url: str,
    user_id: str,
    org_id: str = "",
    prompt: str = "Say 'smoke' in one word.",
) -> httpx.Response:
    """Call the model invoke endpoint with billing headers."""
    headers = {"X-User-ID": user_id}
    if org_id:
        headers["X-Organization-ID"] = org_id
    payload = {
        "input_data": prompt,
        "service_type": "text",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.0,
        "max_tokens": 10,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await client.post(
            f"{model_url}/api/v1/invoke",
            json=payload,
            headers=headers,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBillingPipeline:
    """Cross-service smoke tests for the billing pipeline."""

    async def test_subscription_credit_balance(
        self,
        subscription_service_url,
        smoke_user_id,
        smoke_org_id,
    ):
        """Smoke user has a positive credit balance."""
        balance = await _get_credit_balance(
            subscription_service_url, smoke_user_id, smoke_org_id,
        )
        assert balance.get("success") is True, f"Balance check failed: {balance}"
        remaining = balance.get("credits_remaining", 0)
        assert remaining > 0, (
            f"Smoke user {smoke_user_id} has no credits ({remaining}). "
            "Cannot run billing pipeline tests."
        )

    async def test_model_invoke_succeeds(
        self,
        model_service_url,
        smoke_user_id,
        smoke_org_id,
    ):
        """Model invoke returns 200 for a user with credits."""
        resp = await _invoke_model(
            model_service_url, smoke_user_id, smoke_org_id,
        )
        assert resp.status_code == 200, (
            f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        )
        body = resp.json()
        assert body.get("success") is True, f"Invoke did not succeed: {body}"

    async def test_invoke_creates_billing_record(
        self,
        model_service_url,
        billing_service_url,
        smoke_user_id,
        smoke_org_id,
    ):
        """After a model invoke, a billing record appears in billing_service.

        Flow: invoke → NATS event → billing_service consumes → record created.
        We poll with a short backoff because event processing is async.
        """
        # Snapshot existing record count
        before = await _get_billing_records(billing_service_url, smoke_user_id)
        count_before = len(before)

        # Trigger inference
        resp = await _invoke_model(
            model_service_url, smoke_user_id, smoke_org_id,
        )
        assert resp.status_code == 200, f"Invoke failed: {resp.status_code}"

        # Poll for new billing record (async pipeline, give it up to 15s)
        new_record = None
        for attempt in range(15):
            await asyncio.sleep(1)
            after = await _get_billing_records(billing_service_url, smoke_user_id)
            if len(after) > count_before:
                new_record = after[0]  # Most recent
                break

        assert new_record is not None, (
            f"No new billing record after 15s. "
            f"Before: {count_before}, After: {len(after)}"
        )
        assert new_record.get("user_id") == smoke_user_id

    async def test_invoke_consumes_credits(
        self,
        model_service_url,
        subscription_service_url,
        smoke_user_id,
        smoke_org_id,
    ):
        """Credits decrease after a model invoke completes the billing cycle."""
        # Snapshot balance before
        balance_before = await _get_credit_balance(
            subscription_service_url, smoke_user_id, smoke_org_id,
        )
        remaining_before = balance_before.get("credits_remaining", 0)
        assert remaining_before > 0, "Need credits to test consumption"

        # Trigger inference
        resp = await _invoke_model(
            model_service_url, smoke_user_id, smoke_org_id,
        )
        assert resp.status_code == 200, f"Invoke failed: {resp.status_code}"

        # Wait for async billing pipeline to settle
        credits_decreased = False
        for attempt in range(15):
            await asyncio.sleep(1)
            balance_after = await _get_credit_balance(
                subscription_service_url, smoke_user_id, smoke_org_id,
            )
            remaining_after = balance_after.get("credits_remaining", 0)
            if remaining_after < remaining_before:
                credits_decreased = True
                break

        assert credits_decreased, (
            f"Credits did not decrease after 15s. "
            f"Before: {remaining_before}, After: {remaining_after}"
        )

    async def test_insufficient_credits_returns_402(
        self,
        model_service_url,
        smoke_broke_user_id,
    ):
        """A user with zero credits gets 402 Payment Required."""
        resp = await _invoke_model(
            model_service_url, smoke_broke_user_id,
        )
        assert resp.status_code == 402, (
            f"Expected 402 for broke user, got {resp.status_code}: "
            f"{resp.text[:300]}"
        )


class TestBillingServiceHealth:
    """Quick health checks for individual billing-related services."""

    async def test_billing_service_health(self, billing_service_url):
        """billing_service /health returns a healthy response."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{billing_service_url}/health")
        assert resp.status_code < 500, (
            f"billing_service unhealthy: {resp.status_code}"
        )

    async def test_subscription_service_health(self, subscription_service_url):
        """subscription_service /health returns a healthy response."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{subscription_service_url}/health")
        assert resp.status_code < 500, (
            f"subscription_service unhealthy: {resp.status_code}"
        )

    async def test_model_service_health(self, model_service_url):
        """isA_Model /health returns a healthy response."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{model_service_url}/health")
        assert resp.status_code < 500, (
            f"isA_Model unhealthy: {resp.status_code}"
        )

    async def test_billing_service_info(self, billing_service_url):
        """billing_service /info returns service capabilities."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{billing_service_url}/api/v1/billing/info")
        assert resp.status_code == 200, (
            f"billing_service /info failed: {resp.status_code}"
        )
