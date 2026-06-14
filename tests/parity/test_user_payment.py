"""Parity smoke for the **user-payment** service (payment_service).

Source of truth: `microservices/payment_service/main.py` (FastAPI app) plus
`crypto_routes.py` (mounted at `/api/v1/payment/crypto`). The SN parity audit
lists this service as `auth_required=True`: every write/read of user-scoped data
goes through the `get_authenticated_user_id` dependency (JWT / API key / internal
service). A handful of endpoints are NOT auth-gated and work in every env:
  - GET  /health, /api/v1/payments/health        (liveness)
  - GET  /api/v1/payment/info                      (capabilities)
  - GET  /api/v1/payment/plans                     (list plans — no auth dep)
  - GET  /api/v1/payment/crypto/info|providers|chains|tokens|health  (public)

Parity signal = no 5xx + inter-service calls resolve. We assert ONLY
`r.status < 500` (400/401/403/404/422 are all acceptable parity outcomes), never
specific bodies or 200s. The payment handlers wrap inner failures in
`raise HTTPException(500, ...)` (e.g. unreachable Account/Stripe clients), so a
5xx here is exactly the cross-service regression this suite hunts for.

Auth-gated flows use the `auth_headers` fixture (a real bootstrapped bearer
token); that fixture auto-skips the test when auth is unavailable.

CRUD note: the payment service exposes create endpoints (plans, payment intents)
but NO REST DELETE routes for those resources — subscriptions cancel via a POST
`/cancel` action, plans/intents have no teardown route at all. The generic
DELETE-based `cleanup` fixture therefore can't apply. We keep every create
side-effect-safe by using clearly-fake `parity-smoke` identifiers and, where an
undo action exists (subscription cancel), invoking it in-test so the suite is
prod-safe.
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-payment"

# Clearly-fake parity identities — never collide with real users/plans.
TEST_USER_ID = "usr_parity_payment_smoke"
TEST_PLAN_ID = "plan_parity_smoke"


# ---------------------------------------------------------------------------
# Public (no-auth) reachability + list endpoints
# ---------------------------------------------------------------------------


def test_user_payment_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_payment_info_and_stats():
    """Service info + revenue/subscription stats — surface dependency wiring."""
    c = Client(SERVICE)
    ri = c.get("/api/v1/payment/info")
    assert ri.status < 500, f"payment/info 5xx: {ri.text[:160]}"
    rr = c.get("/api/v1/payment/stats/revenue")
    assert rr.status < 500, f"stats/revenue 5xx: {rr.text[:160]}"
    rs = c.get("/api/v1/payment/stats/subscriptions")
    assert rs.status < 500, f"stats/subscriptions 5xx: {rs.text[:160]}"


def test_user_payment_list_plans():
    """List the subscription-plans collection — public read path; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/payment/plans")
    assert r.status < 500, f"list plans 5xx: {r.text[:160]}"


def test_user_payment_crypto_metadata():
    """Crypto provider metadata endpoints (public) — exercise provider wiring."""
    c = Client(SERVICE)
    for path in (
        "/api/v1/payment/crypto/info",
        "/api/v1/payment/crypto/providers",
        "/api/v1/payment/crypto/chains",
        "/api/v1/payment/crypto/tokens",
        "/api/v1/payment/crypto/health",
    ):
        r = c.get(path)
        assert r.status < 500, f"{path} 5xx: {r.text[:160]}"


# ---------------------------------------------------------------------------
# Auth-gated read paths
# ---------------------------------------------------------------------------


def test_user_payment_payment_history(auth_headers):
    """Read a user's payment history (auth-gated) — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get(
        f"/api/v1/payment/payments/user/{TEST_USER_ID}?limit=50",
        headers=auth_headers,
    )
    assert r.status < 500, f"payment history 5xx: {r.text[:160]}"


def test_user_payment_user_subscription(auth_headers):
    """Read a user's active subscription (auth-gated) — no 5xx (404 is fine)."""
    c = Client(SERVICE)
    r = c.get(
        f"/api/v1/payment/subscriptions/user/{TEST_USER_ID}",
        headers=auth_headers,
    )
    assert r.status < 500, f"user subscription 5xx: {r.text[:160]}"


# ---------------------------------------------------------------------------
# Create flows (side-effect-safe; no DELETE route exists for these resources)
# ---------------------------------------------------------------------------


def test_user_payment_create_plan(auth_headers):
    """Create a subscription plan, then read it back by id.

    The plan create endpoint takes individual Body(...) fields (not a single
    request model): plan_id, name, tier, price, billing_cycle. There is no
    DELETE route for plans, so we use a clearly-fake parity plan_id and keep
    assertions parity-level (every call < 500). Re-running is idempotent enough
    for a smoke (a duplicate create surfaces as 4xx, never a 5xx).
    """
    c = Client(SERVICE)
    payload = {
        "plan_id": TEST_PLAN_ID,
        "name": "parity-smoke",
        "tier": "basic",
        "price": 9.99,
        "billing_cycle": "monthly",
        "features": {},
        "trial_days": 0,
    }
    r = c.post("/api/v1/payment/plans", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"create plan 5xx: {r.text[:160]}"

    # Read the plan back by id (public read path) — still parity-level.
    rid = TEST_PLAN_ID
    if r.ok and isinstance(r.json(), dict) and r.json().get("plan_id"):
        rid = r.json()["plan_id"]
    r2 = c.get(f"/api/v1/payment/plans/{rid}")
    assert r2.status < 500, f"get plan 5xx: {r2.text[:160]}"


def test_user_payment_create_payment_intent(auth_headers):
    """Create a payment intent (auth-gated; validates user via Account Service).

    Body derived from CreatePaymentIntentRequest: required `amount` + `user_id`
    (currency defaults to USD). This exercises the synchronous Account-Service
    dependency and (when configured) Stripe — a 5xx here means an inter-service
    call failed, which is exactly the parity regression we hunt. Payment intents
    have no DELETE route; we use a fake user_id so nothing real is charged and
    keep assertions to < 500.
    """
    c = Client(SERVICE)
    payload = {
        "amount": 10.00,
        "currency": "USD",
        "user_id": TEST_USER_ID,
        "description": "parity-smoke",
    }
    r = c.post(
        "/api/v1/payment/payments/intent",
        json_body=payload,
        headers=auth_headers,
    )
    assert r.status < 500, f"create payment intent 5xx: {r.text[:160]}"

    # If an intent came back, read the user's history back (parity-level).
    if r.ok:
        r2 = c.get(
            f"/api/v1/payment/payments/user/{TEST_USER_ID}?limit=50",
            headers=auth_headers,
        )
        assert r2.status < 500, f"history read-back 5xx: {r2.text[:160]}"


def test_user_payment_create_subscription(auth_headers):
    """Create a subscription, then self-clean via the cancel action.

    Body derived from CreateSubscriptionRequest: required `user_id` + `plan_id`.
    There is no DELETE route for subscriptions; cancellation is a POST action
    (`/subscriptions/{id}/cancel`). We invoke it in-test (with immediate=True)
    so the create is prod-safe. All assertions stay parity-level (< 500); a
    missing plan/user surfaces as 4xx, never a 5xx.
    """
    c = Client(SERVICE)
    payload = {
        "user_id": TEST_USER_ID,
        "plan_id": TEST_PLAN_ID,
        "metadata": {"source": "parity-smoke"},
    }
    r = c.post(
        "/api/v1/payment/subscriptions",
        json_body=payload,
        headers=auth_headers,
    )
    assert r.status < 500, f"create subscription 5xx: {r.text[:160]}"

    # Self-clean: cancel the subscription if one was created (the only undo).
    if r.ok and isinstance(r.json(), dict):
        body = r.json()
        sub = body.get("subscription") or {}
        sub_id = sub.get("subscription_id") if isinstance(sub, dict) else None
        if sub_id:
            cancel = c.post(
                f"/api/v1/payment/subscriptions/{sub_id}/cancel",
                json_body={"immediate": True, "reason": "parity-smoke-cleanup"},
                headers=auth_headers,
            )
            assert cancel.status < 500, f"cancel subscription 5xx: {cancel.text[:160]}"
