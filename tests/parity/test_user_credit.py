"""Parity smoke for the **user-credit** service (credit_service).

Public endpoints: the actual route handlers in
microservices/credit_service/main.py carry NO auth dependency — every endpoint
is reachable without a bearer token (the routes_registry `auth_required` flags
are not wired to a real dependency). So we exercise them unauthenticated.

Parity signal = no 5xx + inter-service calls (account_client / subscription_client,
postgres, NATS) resolve. We deliberately assert ONLY `r.status < 500`
(400/401/403/404/422 are all acceptable parity outcomes), never specific bodies
or 200s — payload/auth nuances make those brittle. The bug we hunt is a 5xx.

Endpoints exercised (from microservices/credit_service/main.py):
  - GET  /health                                          (public liveness)
  - GET  /api/v1/credits/accounts?user_id=...             (list accounts)
  - GET  /api/v1/credits/balance?user_id=...              (balance summary)
  - GET  /api/v1/credits/transactions?user_id=...         (transaction history)
  - GET  /api/v1/credits/campaigns                        (list campaigns)
  - POST /api/v1/credits/accounts                         (create account)
        body: CreateAccountRequest{user_id, credit_type, expiration_policy,
                                    expiration_days}
  - GET  /api/v1/credits/accounts/{account_id}            (read back by id)
  - DELETE /api/v1/credits/accounts/{account_id}          (cleanup, if supported)
  - POST /api/v1/credits/check-availability               (availability check)
  - POST /api/v1/credits/campaigns                        (create campaign)
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-credit"

# Clearly-fake parity test users — safe to create/delete against prod.
TEST_USER = "parity-smoke-user"


def test_user_credit_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_credit_list_accounts():
    """List the main accounts collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/credits/accounts?user_id={TEST_USER}")
    assert r.status < 500, f"list accounts 5xx: {r.text[:160]}"


def test_user_credit_balance():
    """Aggregated balance summary — exercises the read path; no 5xx expected."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/credits/balance?user_id={TEST_USER}")
    assert r.status < 500, f"balance 5xx: {r.text[:160]}"


def test_user_credit_transactions():
    """Transaction history read path — must not 5xx."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/credits/transactions?user_id={TEST_USER}&limit=50")
    assert r.status < 500, f"transactions 5xx: {r.text[:160]}"


def test_user_credit_list_campaigns():
    """List campaigns collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/credits/campaigns")
    assert r.status < 500, f"list campaigns 5xx: {r.text[:160]}"


def test_user_credit_account_create_read_delete(cleanup):
    """CRUD parity: create credit account -> read back by id -> auto-delete.

    Self-cleaning so it is safe to run against prod. We register the DELETE the
    moment the resource is created (resolving the real account_id from the
    response), then read it back. Only parity-level assertions: every call < 500.
    Required fields derived from CreateAccountRequest: user_id, credit_type
    (must be a valid CreditTypeEnum value), expiration_policy (valid
    ExpirationPolicyEnum value), expiration_days.
    """
    c = Client(SERVICE)
    payload = {
        "user_id": TEST_USER,
        "credit_type": "promotional",
        "expiration_policy": "fixed_days",
        "expiration_days": 90,
        "metadata": {"source": "parity-smoke"},
    }

    r = c.post("/api/v1/credits/accounts", json_body=payload)
    assert r.status < 500, f"create account 5xx: {r.text[:160]}"

    # Register cleanup immediately if the create succeeded — resolve the real
    # account_id from the response (CreditAccountResponse.account_id).
    account_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        account_id = body.get("account_id")
        if account_id:
            cleanup(c, f"/api/v1/credits/accounts/{account_id}")

    # Read the resource back by id — still parity-level (no 5xx).
    if account_id:
        r2 = c.get(f"/api/v1/credits/accounts/{account_id}")
        assert r2.status < 500, f"get account 5xx: {r2.text[:160]}"


def test_user_credit_check_availability():
    """Availability check POST path — exercises consumption-planning logic.

    Minimal valid CheckAvailabilityRequest: user_id + positive amount. No 5xx
    expected (an empty/absent balance yields available=false, still < 500).
    """
    c = Client(SERVICE)
    payload = {"user_id": TEST_USER, "amount": 50}
    r = c.post("/api/v1/credits/check-availability", json_body=payload)
    assert r.status < 500, f"check-availability 5xx: {r.text[:160]}"


def test_user_credit_campaign_create(cleanup):
    """Create a campaign with a minimal valid payload — parity-level only.

    Required fields from CreateCampaignRequest: name, credit_type, credit_amount,
    total_budget, start_date, end_date. There is no DELETE route for campaigns,
    so we cannot auto-clean; we keep data clearly-fake (name="parity-smoke") and
    rely on test isolation. No id-bearing cleanup is registered.
    """
    c = Client(SERVICE)
    payload = {
        "name": "parity-smoke",
        "description": "parity smoke campaign",
        "credit_type": "promotional",
        "credit_amount": 10,
        "total_budget": 1000,
        "start_date": "2026-06-09T00:00:00Z",
        "end_date": "2026-12-31T23:59:59Z",
        "expiration_days": 90,
    }
    r = c.post("/api/v1/credits/campaigns", json_body=payload)
    assert r.status < 500, f"create campaign 5xx: {r.text[:160]}"
