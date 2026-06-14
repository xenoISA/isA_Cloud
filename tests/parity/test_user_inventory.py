"""Parity smoke tests for the user-inventory service (isA_user inventory_service).

Parity goal: confirm the inventory backend is reachable in the target environment
and that its inter-service-shaped routes (reserve -> commit -> release, plus the
reservation read) do NOT 5xx. We assert ONLY ``status < 500`` (a 5xx is the bug
we hunt) — auth/validation nuances (400/404/422) are acceptable parity outcomes.

The service is PUBLIC (auth_required=False per SN-PARITY-AUDIT.md): it carries
caller identity via a ``user_id`` field in the request body rather than a JWT, so
no ``auth_headers`` are needed. Endpoints/payloads derive from the real route
handlers in ``inventory_service/main.py`` (FastAPI app):

  - GET  /health                                  health (also /api/v1/inventory/health)
  - GET  /api/v1/inventory/health                 health w/ NATS + PostgreSQL status
  - POST /api/v1/inventory/reserve                body {"order_id", "items":[{sku_id, quantity, unit_price}], "user_id"}
  - POST /api/v1/inventory/commit                 body {"order_id", "reservation_id"}
  - POST /api/v1/inventory/release                body {"order_id", "reservation_id", "reason"}
  - GET  /api/v1/inventory/reservations/{order_id}  read reservation by order_id

NOTE: this service exposes NO DELETE endpoint — a reservation's lifecycle ends
via POST /release (order canceled) rather than a REST delete. Reservations also
require backing stock (a finite SKU with on_hand) to actually succeed, so in a
target with no seeded inventory the reserve may legitimately return 400/404; that
is still a valid parity outcome (no 5xx). To remain prod-safe and self-cleaning,
each test that does manage to create a live reservation issues a POST /release
inline in a ``finally`` block, and the order_id is a clearly-fake parity value.
"""

from __future__ import annotations

import os
import time


SERVICE = "user-inventory"

# A clearly-fake parity user id — keeps any rows created during the run obviously
# synthetic and easy to spot if cleanup is ever interrupted.
PARITY_USER = "parity-smoke-user"


def _fake_order_id() -> str:
    """Unique, obviously-synthetic order id so parallel/repeat runs don't collide."""
    return f"parity-smoke-order-{int(time.time() * 1000)}-{os.getpid()}"


def _reserve_body(order_id: str) -> dict:
    """Smallest VALID reserve payload per the reserve handler.

    Required shape: order_id, a non-empty items list (each with sku_id + quantity),
    and a user_id. unit_price is included for realism; the SKU is fake so the
    reservation may be rejected for lack of stock — still a < 500 parity signal.
    """
    return {
        "order_id": order_id,
        "user_id": PARITY_USER,
        "items": [
            {
                "sku_id": "parity-smoke-sku",
                "quantity": 1,
                "unit_price": 0.0,
            }
        ],
    }


def _release(client, order_id: str, reservation_id) -> None:
    """Best-effort inline teardown — release any reservation we may have created.

    The service has no DELETE route, so the harness ``cleanup`` (DELETE-only) does
    not apply here; we POST /release directly and swallow any error so teardown can
    never fail the test or leave the run in a bad state.
    """
    try:
        client.post(
            "/api/v1/inventory/release",
            json_body={
                "order_id": order_id,
                "reservation_id": reservation_id,
                "reason": "parity_test_cleanup",
            },
        )
    except Exception:  # noqa: BLE001
        pass


def test_user_inventory_health(http):
    """Service is reachable and the health route does not 5xx."""
    client = http(SERVICE)
    r = client.get("/api/v1/inventory/health")
    assert r.status != 0, f"{SERVICE} unreachable: {r.text}"
    assert r.status < 500, f"health 5xx: {r.status} {r.text}"


def test_user_inventory_reservation_read(http):
    """GET the reservation read endpoint for a fake order — must not 5xx.

    With no such reservation present a 404 is expected; the parity signal is that
    the route resolves (and its backing PostgreSQL lookup runs) without a 5xx.
    """
    client = http(SERVICE)
    r = client.get(f"/api/v1/inventory/reservations/{_fake_order_id()}")
    assert r.status != 0, f"{SERVICE} unreachable: {r.text}"
    assert r.status < 500, f"reservation read 5xx: {r.status} {r.text}"


def test_user_inventory_reserve_read_release(http):
    """Reserve -> read-by-order -> release lifecycle, self-cleaning and prod-safe.

    Asserts only ``status < 500`` at every hop. If reserve succeeds and returns a
    reservation_id we release it inline (no DELETE route exists) so no live
    reservation is left behind, even on assertion failure.
    """
    client = http(SERVICE)
    order_id = _fake_order_id()

    reserve = client.post(
        "/api/v1/inventory/reserve", json_body=_reserve_body(order_id)
    )
    assert reserve.status != 0, f"{SERVICE} unreachable: {reserve.text}"
    assert reserve.status < 500, f"reserve 5xx: {reserve.status} {reserve.text}"

    if not reserve.ok:
        # Reserve rejected (e.g. no seeded stock / validation in this env) — no
        # live reservation was created, nothing to release. The < 500 above is the
        # parity signal.
        return

    body = reserve.json() or {}
    reservation_id = body.get("reservation_id") or body.get("id")

    try:
        read = client.get(f"/api/v1/inventory/reservations/{order_id}")
        assert read.status < 500, f"reservation read 5xx: {read.status} {read.text}"
    finally:
        # Always release whatever we may have created, regardless of read outcome.
        _release(client, order_id, reservation_id)


def test_user_inventory_reserve_commit(http):
    """Reserve -> commit, exercising the post-payment commit path — must not 5xx.

    Commit is also driven by payment.completed NATS events in production; this
    HTTP path is the inter-service-shaped surface we parity-check. Self-cleaning:
    if reserve created a live reservation we release it inline in ``finally``.
    """
    client = http(SERVICE)
    order_id = _fake_order_id()

    reserve = client.post(
        "/api/v1/inventory/reserve", json_body=_reserve_body(order_id)
    )
    assert reserve.status != 0, f"{SERVICE} unreachable: {reserve.text}"
    assert reserve.status < 500, f"reserve 5xx: {reserve.status} {reserve.text}"

    if not reserve.ok:
        return

    body = reserve.json() or {}
    reservation_id = body.get("reservation_id") or body.get("id")

    try:
        commit = client.post(
            "/api/v1/inventory/commit",
            json_body={"order_id": order_id, "reservation_id": reservation_id},
        )
        assert commit.status < 500, f"commit 5xx: {commit.status} {commit.text}"
    finally:
        # A committed reservation may no longer be releasable; release is best-effort
        # and swallows errors, so this stays safe either way.
        _release(client, order_id, reservation_id)
