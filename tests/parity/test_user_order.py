"""Parity smoke tests for the **user-order** service (order_service).

Source of truth for endpoints/payloads:
  isA_user/microservices/order_service/{routes_registry.py, models.py, order_service.py}

Endpoints exercised (all under base path /api/v1/orders):
  - GET  /health                          (public — health check)
  - GET  /api/v1/orders                   (list orders; auth_required=True)
  - POST /api/v1/orders                   (create order; auth_required=True)
  - GET  /api/v1/orders/{order_id}        (read order; auth_required=True)
  - GET  /api/v1/orders/search            (search; auth_required=True)
  - GET  /api/v1/orders/statistics        (stats; auth_required=True)
  - POST /api/v1/orders/{order_id}/cancel (cancel — used for self-cleaning)

PARITY contract (see tests/parity/README.md):
  We assert ONLY `r.status < 500`. A 5xx is the bug we hunt (a service crash or an
  unresolved inter-service call). 401/403/422 are acceptable parity signals — they
  prove the service is up and routing/validation/auth middleware are wired.

CRUD/cleanup note: orders are NOT a REST resource with a DELETE route (the
routes_registry exposes no DELETE), so the generic DELETE-based `cleanup` fixture
cannot remove one. We instead self-clean in-test via the cancel endpoint
(POST /api/v1/orders/{order_id}/cancel) in a finally block, keeping the test
prod-safe. The order_service also fans out to account/payment/wallet clients, so
these create flows double as inter-service reachability checks.

The order routes are auth-gated (auth_required=True). We pass `auth_headers`;
using that fixture auto-skips the test if a bootstrapped token is unavailable.
"""

from conftest import Client

SERVICE = "user-order"

# Minimal VALID OrderCreateRequest payload. Required fields (from models.py
# OrderCreateRequest): user_id, order_type, total_amount (gt=0). Items carry a
# product_id + quantity(gt=0) + unit_price(ge=0). Clearly-fake test data.
MINIMAL_ORDER = {
    "user_id": "parity-smoke-user",
    "order_type": "purchase",
    "total_amount": 99.99,
    "currency": "USD",
    "items": [
        {
            "product_id": "parity-smoke-prod",
            "quantity": 1,
            "unit_price": 99.99,
            "fulfillment_type": "digital",
        }
    ],
    "metadata": {"source": "parity-smoke"},
}


def _extract_order_id(body):
    """Pull an order_id out of an OrderResponse-ish body (best-effort)."""
    if not isinstance(body, dict):
        return None
    if isinstance(body.get("order"), dict):
        oid = body["order"].get("order_id") or body["order"].get("id")
        if oid:
            return oid
    return body.get("order_id") or body.get("id")


def test_user_order_health():
    """Service is reachable and the public health endpoint does not 5xx."""
    client = Client(SERVICE)
    r = client.get("/health")
    assert r.status != 0, f"order service unreachable: {r.text}"
    assert r.status < 500, f"GET /health returned {r.status}: {r.text}"


def test_user_order_list(auth_headers):
    """GET the main collection endpoint — no 5xx (auth/validation 4xx is fine)."""
    client = Client(SERVICE)
    r = client.get("/api/v1/orders", headers=auth_headers)
    assert r.status != 0, f"order service unreachable: {r.text}"
    assert r.status < 500, f"GET /api/v1/orders returned {r.status}: {r.text}"


def test_user_order_search(auth_headers):
    """Search endpoint resolves without a 5xx."""
    client = Client(SERVICE)
    r = client.get(
        "/api/v1/orders/search?query=parity-smoke&limit=10", headers=auth_headers
    )
    assert r.status < 500, f"GET /api/v1/orders/search returned {r.status}: {r.text}"


def test_user_order_statistics(auth_headers):
    """Statistics endpoint exercises the DB path; must not 5xx."""
    client = Client(SERVICE)
    r = client.get("/api/v1/orders/statistics", headers=auth_headers)
    assert r.status < 500, (
        f"GET /api/v1/orders/statistics returned {r.status}: {r.text}"
    )


def test_user_order_create_read_cancel(auth_headers, cleanup):
    """Create -> read-back -> cancel (self-cleaning) CRUD parity flow.

    Orders have no DELETE route, so we self-clean via the cancel endpoint in a
    finally block. If the order also exposes a DELETE alias we additionally
    register it with the `cleanup` fixture for belt-and-suspenders teardown.
    Parity asserts only: nothing 5xxes through create/read/cancel.
    """
    client = Client(SERVICE)
    order_id = None
    try:
        created = client.post(
            "/api/v1/orders", json_body=MINIMAL_ORDER, headers=auth_headers
        )
        assert created.status < 500, (
            f"POST /api/v1/orders returned {created.status}: {created.text}"
        )

        if created.ok:
            order_id = _extract_order_id(created.json())
            if order_id:
                # Belt-and-suspenders DELETE cleanup (no-op if route absent).
                cleanup(client, f"/api/v1/orders/{order_id}")

                # Read the created resource back.
                got = client.get(f"/api/v1/orders/{order_id}", headers=auth_headers)
                assert got.status < 500, (
                    f"GET /api/v1/orders/{order_id} returned {got.status}: {got.text}"
                )
    finally:
        if order_id:
            # Self-clean via cancel (prod-safe teardown; orders have no DELETE).
            cancel = client.post(
                f"/api/v1/orders/{order_id}/cancel",
                json_body={"reason": "parity-smoke cleanup", "refund_amount": 0},
                headers=auth_headers,
            )
            assert cancel.status < 500, (
                f"POST /api/v1/orders/{order_id}/cancel returned "
                f"{cancel.status}: {cancel.text}"
            )
