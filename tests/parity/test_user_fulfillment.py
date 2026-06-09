"""Parity smoke for the **user-fulfillment** service (fulfillment_service).

Public at the HTTP layer: the FastAPI handlers in
`microservices/fulfillment_service/main.py` take only a raw `Dict[str, Any]`
payload plus a `FulfillmentService` dependency — there is NO auth dependency or
auth middleware on the app, and the SN parity audit lists this service as
`auth_required=False`. So these tests run without a bearer token (they work in
every environment, even when auth is unavailable).

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (400/401/403/404/422 are all acceptable parity outcomes),
never specific bodies or 200s — payload nuances make those brittle. The
fulfillment handlers translate inner failures into ValueError -> 400 and
LookupError -> 404; an unhandled failure (e.g. an unreachable postgres/NATS
backend) surfaces as a 5xx, which is exactly the cross-service regression this
suite hunts for.

Endpoints exercised (from microservices/fulfillment_service/main.py):
  - GET  /health                                          (public liveness)
  - GET  /api/v1/fulfillment/health                       (detailed health)
  - POST /api/v1/fulfillment/shipments                    (create shipment)
        body: {order_id, items[{sku_id, quantity}], address{}, user_id}
  - GET  /api/v1/fulfillment/shipments/{order_id}         (read by order_id)
  - POST /api/v1/fulfillment/shipments/{shipment_id}/label  (purchase label)
  - POST /api/v1/fulfillment/shipments/{shipment_id}/cancel (cancel shipment)
  - GET  /api/v1/fulfillment/tracking/{tracking_number}   (read by tracking #)

CRUD/cleanup note: shipments are NOT a REST resource with a DELETE route, so the
generic `cleanup` (DELETE-based) fixture cannot remove one. We instead self-clean
in-test via the cancel endpoint (POST .../{shipment_id}/cancel), keeping the test
prod-safe. The fake order_id is namespaced so it never collides with real data.
"""

from __future__ import annotations


SERVICE = "user-fulfillment"

# Clearly-fake parity test identity (never collides with real orders/users).
FAKE_ORDER_ID = "ord_parity-smoke"
FAKE_USER_ID = "user_parity-smoke"


def _shipment_payload() -> dict:
    """Minimal VALID create-shipment payload derived from the handler."""
    return {
        "order_id": FAKE_ORDER_ID,
        "user_id": FAKE_USER_ID,
        "items": [{"sku_id": "sku_parity-smoke", "quantity": 1}],
        "address": {
            "name": "parity-smoke",
            "street": "1 Parity Way",
            "city": "Testville",
            "postal_code": "00000",
            "country": "US",
        },
    }


def test_user_fulfillment_health(http):
    """Liveness + detailed health must resolve without a 5xx."""
    client = http(SERVICE)

    r = client.get("/health")
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"/health returned {r.status}: {r.text}"

    r = client.get("/api/v1/fulfillment/health")
    assert r.status < 500, f"fulfillment health returned {r.status}: {r.text}"


def test_user_fulfillment_read_shipment_by_order(http):
    """GET a shipment by order_id — a missing shipment is a clean 404, not 5xx."""
    client = http(SERVICE)
    r = client.get(f"/api/v1/fulfillment/shipments/{FAKE_ORDER_ID}")
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"get shipment returned {r.status}: {r.text}"


def test_user_fulfillment_read_tracking(http):
    """GET a shipment by tracking number — unknown tracking is a clean 404."""
    client = http(SERVICE)
    r = client.get("/api/v1/fulfillment/tracking/trk_parity-smoke")
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"get tracking returned {r.status}: {r.text}"


def test_user_fulfillment_shipment_lifecycle(http):
    """Create -> read-back -> (best-effort label) -> cancel (self-cleaning).

    The only mutating create endpoint is POST /shipments; it has no DELETE route,
    so we self-clean via the cancel endpoint instead of the `cleanup` fixture.
    Every call asserts only `r.status < 500`.
    """
    client = http(SERVICE)

    created = client.post(
        "/api/v1/fulfillment/shipments", json_body=_shipment_payload()
    )
    assert created.status != 0, "service unreachable"
    assert created.status < 500, (
        f"create shipment returned {created.status}: {created.text}"
    )

    shipment_id = None
    if created.ok:
        try:
            body = created.json()
        except Exception:
            body = None
        if isinstance(body, dict):
            shipment_id = body.get("shipment_id") or body.get("id")

    # Read the shipment back by its order_id (parity: must not 5xx).
    read_back = client.get(f"/api/v1/fulfillment/shipments/{FAKE_ORDER_ID}")
    assert read_back.status < 500, (
        f"read-back returned {read_back.status}: {read_back.text}"
    )

    if shipment_id:
        # Best-effort label purchase — only checked for absence of a 5xx.
        label = client.post(
            f"/api/v1/fulfillment/shipments/{shipment_id}/label",
            json_body={},
        )
        assert label.status < 500, f"create label returned {label.status}: {label.text}"

        # Self-clean: cancel the shipment we created (prod-safe teardown).
        cancel = client.post(
            f"/api/v1/fulfillment/shipments/{shipment_id}/cancel",
            json_body={"reason": "parity-smoke cleanup"},
        )
        assert cancel.status < 500, (
            f"cancel shipment returned {cancel.status}: {cancel.text}"
        )
