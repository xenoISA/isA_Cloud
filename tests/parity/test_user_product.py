"""Parity smoke tests for the isA **user-product** service.

Derived from the real route handlers in
`isA_user/microservices/product_service/main.py` and the per-service spec in
`docs/saas-deployment/SN-PARITY-AUDIT.md` (### user-product, auth_required=True).

Parity contract: we only assert `r.status < 500`. A 5xx is the bug we hunt
(unresolved inter-service call, broken dependency, crash). 401/403/404/422 are
all acceptable parity outcomes — auth/payload nuances vary per environment.

Every created resource is registered with `cleanup` immediately after creation
so the suite is safe to run against production.
"""

from __future__ import annotations

import uuid

from conftest import Client  # noqa: F401  (re-exported harness type)

SERVICE = "user-product"


def _ok(r):
    """Parity assertion: reachable and no server-side (5xx) failure."""
    assert r.status != 0, f"unreachable: {r.text}"
    assert r.status < 500, f"5xx from {SERVICE}: {r.status} {r.text}"


# ---------------------------------------------------------------------------
# 1. List / read flow — product catalog
# ---------------------------------------------------------------------------
def test_user_product_catalog_read(http, auth_headers):
    """Product Catalog Read Flow: categories -> products list -> single product."""
    c = http(SERVICE)

    _ok(c.get("/api/v1/product/categories", headers=auth_headers))

    r = c.get("/api/v1/product/products", headers=auth_headers)
    _ok(r)

    # If the catalog returned products, read one back by id (still parity-level).
    product_id = None
    body = r.json()
    if isinstance(body, list) and body:
        first = body[0]
        if isinstance(first, dict):
            product_id = first.get("product_id") or first.get("id")
    if not product_id:
        product_id = "parity-smoke-nonexistent"

    _ok(c.get(f"/api/v1/product/products/{product_id}", headers=auth_headers))


# ---------------------------------------------------------------------------
# 2. Health probes
# ---------------------------------------------------------------------------
def test_user_product_health(http):
    """Basic + detailed health probes (public)."""
    c = http(SERVICE)
    _ok(c.get("/health"))
    _ok(c.get("/api/v1/products/health"))


# ---------------------------------------------------------------------------
# 3. Pricing lookup flow
# ---------------------------------------------------------------------------
def test_user_product_pricing(http, auth_headers):
    """Pricing lookup: per-product pricing + compatibility calculate endpoint."""
    c = http(SERVICE)

    _ok(
        c.get(
            "/api/v1/product/products/parity-smoke/pricing?user_id=parity-smoke",
            headers=auth_headers,
        )
    )

    # POST /api/v1/pricing/calculate — request model: product_id, quantity, unit_type, tier_code
    _ok(
        c.post(
            "/api/v1/pricing/calculate",
            json_body={
                "product_id": "parity-smoke",
                "quantity": 1,
                "unit_type": "request",
                "tier_code": "standard",
            },
            headers=auth_headers,
        )
    )


# ---------------------------------------------------------------------------
# 4. Subscription CRUD flow (create -> verify -> status update as soft cleanup)
# ---------------------------------------------------------------------------
def test_user_product_subscription_crud(http, auth_headers):
    """POST subscription -> GET by id -> list by user -> PUT status (canceled).

    The public API exposes no DELETE for subscriptions; the closest self-clean
    is a status update to "canceled". We register no cleanup() here because there
    is no DELETE endpoint, and we proactively cancel any subscription we create.
    """
    c = http(SERVICE)
    user_id = f"parity-smoke-{uuid.uuid4().hex[:8]}"

    r = c.post(
        "/api/v1/product/subscriptions",
        json_body={
            "user_id": user_id,
            "plan_id": "parity-smoke-plan",
            "billing_cycle": "monthly",
        },
        headers=auth_headers,
    )
    _ok(r)

    sub_id = None
    if r.ok:
        body = r.json()
        if isinstance(body, dict):
            sub_id = body.get("subscription_id") or body.get("id")

    if sub_id:
        # Soft-clean immediately: cancel the subscription we just created.
        c.put(
            f"/api/v1/product/subscriptions/{sub_id}/status",
            json_body={"status": "canceled"},
            headers=auth_headers,
        )
        _ok(c.get(f"/api/v1/product/subscriptions/{sub_id}", headers=auth_headers))

    _ok(
        c.get(
            f"/api/v1/product/subscriptions/user/{user_id}",
            headers=auth_headers,
        )
    )


# ---------------------------------------------------------------------------
# 5. Admin product CRUD (create -> verify -> DELETE) — self-cleaning
# ---------------------------------------------------------------------------
def test_user_product_admin_product_crud(http, auth_headers, cleanup):
    """POST admin product -> register DELETE cleanup -> GET by id.

    Admin endpoints are gated by `require_admin`; a non-admin token yields 401/403
    (acceptable parity outcomes). If creation succeeds, the soft-delete endpoint
    is registered for teardown so no test data is left active.
    """
    c = http(SERVICE)
    pid = f"parity-smoke-{uuid.uuid4().hex[:10]}"

    r = c.post(
        "/api/v1/product/admin/products",
        json_body={
            "product_id": pid,
            "product_name": "parity-smoke",
            "product_code": pid,
            "product_type": "other",
            "base_price": 0.0,
            "currency": "USD",
        },
        headers=auth_headers,
    )
    _ok(r)

    if r.ok:
        # Register the soft-delete immediately so teardown always runs.
        cleanup(c, f"/api/v1/product/admin/products/{pid}")
        _ok(c.get(f"/api/v1/product/products/{pid}", headers=auth_headers))
