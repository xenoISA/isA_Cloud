"""Parity smoke for the **user-billing** service (billing_service).

Public at the HTTP layer: the FastAPI handlers in
`microservices/billing_service/main.py` take only a `BillingService` dependency
— there is NO auth dependency or auth middleware on the app, and the SN parity
audit lists this service as `auth_required=False`. So these tests run without a
bearer token (they work in every environment, even when auth is unavailable).

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (400/401/403/404/422 are all acceptable parity outcomes),
never specific bodies or 200s — payload/auth nuances make those brittle. The
billing handlers wrap their bodies in `raise HTTPException(500, ...)` on any
inner failure (e.g. an unreachable wallet/product/agent client), so a 5xx here
is exactly the cross-service regression this suite hunts for.

Endpoints exercised (from microservices/billing_service/main.py):
  - GET  /health                                  (public liveness)
  - GET  /api/v1/billing/health                   (detailed health)
  - GET  /api/v1/billing/info                      (service capabilities)
  - GET  /api/v1/billing/records?user_id=...        (list records, paginated)
  - GET  /api/v1/billing/quota/{user_id}            (user quota status)
  - POST /api/v1/billing/calculate                  (cost calc, no side effects)
  - POST /api/v1/billing/quota/check                (quota check, no side effects)
  - POST /api/v1/billing/usage/record               (create+bill -> record)
        body: RecordUsageRequest{user_id, product_id, service_type,
              usage_amount}  (required) -- self-cleans via admin/refund.

CRUD note: usage/record returns a ProcessBillingResponse, not a REST resource
with a DELETE route, so the generic `cleanup` (DELETE-based) fixture cannot
remove it. We instead self-clean in-test via the admin refund endpoint
(POST /api/v1/billing/admin/refund) so the test is prod-safe.
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-billing"

# Clearly-fake parity test identity (never collides with real users).
TEST_USER_ID = "usr_parity_billing_smoke"


def test_user_billing_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_billing_detailed_health_and_info():
    """Detailed health + info endpoints — surface dependency wiring; no 5xx."""
    c = Client(SERVICE)
    rh = c.get("/api/v1/billing/health")
    assert rh.status < 500, f"billing/health 5xx: {rh.text[:160]}"
    ri = c.get("/api/v1/billing/info")
    assert ri.status < 500, f"billing/info 5xx: {ri.text[:160]}"


def test_user_billing_list_records():
    """List the main billing records collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/billing/records?user_id={TEST_USER_ID}&page=1&page_size=50")
    assert r.status < 500, f"list records 5xx: {r.text[:160]}"


def test_user_billing_quota_status():
    """Read a user's quota status by id — auth-free read path; no 5xx."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/billing/quota/{TEST_USER_ID}")
    assert r.status < 500, f"quota status 5xx: {r.text[:160]}"


def test_user_billing_calculate():
    """Cost calculation — side-effect-free, exercises product-client resolution."""
    c = Client(SERVICE)
    payload = {
        "user_id": TEST_USER_ID,
        "product_id": "parity-smoke-product",
        "usage_amount": 1,
    }
    r = c.post("/api/v1/billing/calculate", json_body=payload)
    assert r.status < 500, f"calculate 5xx: {r.text[:160]}"


def test_user_billing_quota_check():
    """Quota check — side-effect-free, exercises the quota read path."""
    c = Client(SERVICE)
    payload = {
        "user_id": TEST_USER_ID,
        "service_type": "model_inference",
        "requested_amount": 1,
    }
    r = c.post("/api/v1/billing/quota/check", json_body=payload)
    assert r.status < 500, f"quota check 5xx: {r.text[:160]}"


def test_user_billing_record_usage_and_verify():
    """CRUD parity: record usage (create+bill) -> read records back.

    `usage/record` is the closest thing to a create in this service. It returns
    a ProcessBillingResponse rather than a DELETE-able REST resource, so we
    self-clean in-test via the admin refund endpoint (prod-safe). All assertions
    stay parity-level: every call must be < 500.
    """
    c = Client(SERVICE)
    payload = {
        "user_id": TEST_USER_ID,
        "product_id": "parity-smoke-product",
        "service_type": "model_inference",
        "usage_amount": 1,
        "billing_metadata": {"source": "parity-smoke"},
    }

    r = c.post("/api/v1/billing/usage/record", json_body=payload)
    assert r.status < 500, f"usage/record 5xx: {r.text[:160]}"

    # Self-clean immediately if a record was created (refund is the only undo;
    # there is no DELETE route, so the generic cleanup fixture can't apply).
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        billing_id = body.get("billing_record_id")
        if billing_id:
            refund = c.post(
                f"/api/v1/billing/admin/refund?billing_id={billing_id}"
                "&reason=parity-smoke-cleanup"
            )
            # Refund itself must not 5xx (parity signal for the admin path).
            assert refund.status < 500, f"admin/refund 5xx: {refund.text[:160]}"

    # Read the records collection back by user — still parity-level (no 5xx).
    r2 = c.get(f"/api/v1/billing/records?user_id={TEST_USER_ID}&page=1&page_size=50")
    assert r2.status < 500, f"records read-back 5xx: {r2.text[:160]}"
