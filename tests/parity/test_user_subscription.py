"""Parity smoke for the **user-subscription** service (subscription_service).

Public at the HTTP layer: the FastAPI handlers in
`microservices/subscription_service/main.py` take only a `SubscriptionService`
dependency — there is NO auth dependency or auth middleware on the app, and the
SN parity audit lists this service as `auth_required=False`. So these tests run
without a bearer token (they work in every environment, even when auth is
unavailable). The only gated endpoints are the `/admin/*` routes, which require
an `X-Admin-Role: true` header — those are intentionally NOT exercised here.

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (400/401/402/403/404/409/422 are all acceptable parity
outcomes), never specific bodies or 200s — payload/auth/state nuances make those
brittle. The subscription handlers wrap inner failures (e.g. an unreachable
product/wallet client, or a DB error) in `HTTPException(500, ...)`, so a 5xx
here is exactly the cross-service regression this suite hunts for.

Endpoints exercised (from microservices/subscription_service/main.py):
  - GET  /health                                              (public liveness)
  - GET  /api/v1/subscriptions/health                          (detailed health)
  - GET  /api/v1/subscriptions?user_id=...                     (list collection)
  - GET  /api/v1/subscriptions/user/{user_id}                  (active sub lookup)
  - GET  /api/v1/subscriptions/credits/balance?user_id=...     (credit balance)
  - POST /api/v1/subscriptions                                 (create)
        body: CreateSubscriptionRequest{user_id, tier_code}  (required;
              billing_cycle defaults to monthly)
  - GET  /api/v1/subscriptions/{subscription_id}               (read by id)
  - GET  /api/v1/subscriptions/{subscription_id}/history       (history)
  - POST /api/v1/subscriptions/{subscription_id}/cancel?user_id=... (cancel)
        body: CancelSubscriptionRequest{immediate, reason}

CRUD / cleanup note: subscriptions have NO DELETE route — the lifecycle "undo"
is POST .../cancel?user_id=... with {immediate: true}. The generic DELETE-based
`cleanup` fixture therefore cannot remove a created subscription, so we
self-clean in-test by calling cancel immediately after a successful create.
This keeps the test prod-safe. We use a clearly-fake test user id that will
never collide with a real user.
"""

from __future__ import annotations

import time

from conftest import Client

SERVICE = "user-subscription"

# Clearly-fake parity test identity (never collides with real users). Unique per
# run so repeated/parallel executions don't trip the "already has active sub"
# guard in create_subscription.
TEST_USER_ID = f"usr_parity_subscription_smoke_{int(time.time())}"


def test_user_subscription_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_subscription_detailed_health():
    """API-v1 health endpoint — surfaces postgres wiring; must not 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/subscriptions/health")
    assert r.status < 500, f"subscriptions/health 5xx: {r.text[:160]}"


def test_user_subscription_list():
    """List the main subscriptions collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/subscriptions?user_id={TEST_USER_ID}&page=1&page_size=50")
    assert r.status < 500, f"list subscriptions 5xx: {r.text[:160]}"


def test_user_subscription_user_lookup():
    """Active-subscription lookup by user id — auth-free read path; no 5xx."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/subscriptions/user/{TEST_USER_ID}")
    assert r.status < 500, f"user subscription lookup 5xx: {r.text[:160]}"


def test_user_subscription_credit_balance():
    """Credit balance read — exercises tier-cache + repository resolution."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/subscriptions/credits/balance?user_id={TEST_USER_ID}")
    assert r.status < 500, f"credit balance 5xx: {r.text[:160]}"


def test_user_subscription_create_verify_cancel():
    """CRUD parity: create -> read-by-id -> self-clean via cancel.

    POST /api/v1/subscriptions creates a subscription from a minimal valid
    CreateSubscriptionRequest (user_id + tier_code; billing_cycle defaults to
    monthly). On the free tier this is side-effect-light. There is no DELETE
    route, so we self-clean by calling the cancel endpoint with immediate=true
    as soon as we have a subscription_id, keeping the test prod-safe.

    All assertions stay parity-level: every call must be < 500.
    """
    c = Client(SERVICE)
    payload = {
        "user_id": TEST_USER_ID,
        "tier_code": "free",
        "billing_cycle": "monthly",
        "metadata": {"source": "parity-smoke"},
    }

    r = c.post("/api/v1/subscriptions", json_body=payload)
    assert r.status < 500, f"create subscription 5xx: {r.text[:160]}"

    subscription_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        sub = body.get("subscription") or {}
        subscription_id = sub.get("subscription_id") if isinstance(sub, dict) else None

    # Self-clean immediately: cancel is the only "undo" (no DELETE route exists),
    # so the generic cleanup fixture can't apply. Cancel before the read-back so
    # a created subscription never lingers even if a later assert fails.
    if subscription_id:
        cancel = c.post(
            f"/api/v1/subscriptions/{subscription_id}/cancel?user_id={TEST_USER_ID}",
            json_body={"immediate": True, "reason": "parity-smoke-cleanup"},
        )
        # The cancel path itself must not 5xx (parity signal for the lifecycle).
        assert cancel.status < 500, f"cancel subscription 5xx: {cancel.text[:160]}"

        # Read the resource back by id — still parity-level (no 5xx).
        r2 = c.get(f"/api/v1/subscriptions/{subscription_id}")
        assert r2.status < 500, f"read-by-id 5xx: {r2.text[:160]}"

        # History endpoint for the created subscription — must resolve.
        r3 = c.get(f"/api/v1/subscriptions/{subscription_id}/history")
        assert r3.status < 500, f"history 5xx: {r3.text[:160]}"
