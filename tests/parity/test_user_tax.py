"""Parity smoke for the **user-tax** service (tax_service).

Public (auth_required=False): the tax endpoints are NOT behind
`get_authenticated_caller` — `/api/v1/tax/calculate` and the calculation
read take a free-form JSON dict and resolve regardless of bearer token, so
no `auth_headers` are used here.

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (400/404/422 are all acceptable parity outcomes),
never specific bodies or 200s — payload nuances make those brittle.

Endpoints exercised (from microservices/tax_service/main.py):
  - GET  /health                              (public liveness)
  - GET  /api/v1/tax/health                   (public versioned health)
  - POST /api/v1/tax/calculate                (calculate; dict payload)
        body: {items:[{sku_id,unit_price,quantity}], address:{country,state,...},
               currency, order_id (optional -> persists when present)}
  - GET  /api/v1/tax/calculations/{order_id}  (read stored calc by order_id)

Note: this service exposes NO DELETE endpoint and the mock provider keeps
calculations only by caller-supplied order_id. To stay prod-safe we use a
unique, clearly-fake order_id per run so we never collide with real orders;
there is nothing to register with `cleanup` because no delete route exists.
"""

from __future__ import annotations

import os
import time

from conftest import Client

SERVICE = "user-tax"


def _fake_order_id() -> str:
    """Unique, clearly-fake order id so we never touch real order data."""
    return f"ord_parity_smoke_{int(time.time())}_{os.getpid()}"


def test_user_tax_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_tax_health_versioned():
    """Versioned health endpoint — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/tax/health")
    assert r.status < 500, f"/api/v1/tax/health 5xx: {r.text[:160]}"


def test_user_tax_preview_calculate():
    """Preview calc WITHOUT order_id — exercises the calc path; no 5xx."""
    c = Client(SERVICE)
    payload = {
        "items": [{"sku_id": "sku_parity_smoke", "unit_price": 50, "quantity": 2}],
        "address": {"country": "US", "state": "TX"},
        "currency": "USD",
    }
    r = c.post("/api/v1/tax/calculate", json_body=payload)
    assert r.status < 500, f"preview calculate 5xx: {r.text[:160]}"


def test_user_tax_calculate_and_retrieve():
    """Calculate-with-order_id -> read it back by order_id.

    A unique fake order_id keeps this prod-safe (no collision with real
    orders) and there is no DELETE route to register, so no cleanup is
    needed. Both calls are parity-level only (no 5xx).
    """
    c = Client(SERVICE)
    order_id = _fake_order_id()
    payload = {
        "items": [{"sku_id": "sku_parity_smoke", "unit_price": 100, "quantity": 1}],
        "address": {
            "country": "US",
            "state": "CA",
            "city": "San Francisco",
            "postal_code": "94102",
        },
        "currency": "USD",
        "order_id": order_id,
        "user_id": "usr_parity_smoke",
    }

    r = c.post("/api/v1/tax/calculate", json_body=payload)
    assert r.status < 500, f"calculate 5xx: {r.text[:160]}"

    # Read the stored calculation back by order_id — still parity-level.
    r2 = c.get(f"/api/v1/tax/calculations/{order_id}")
    assert r2.status < 500, f"get calculation 5xx: {r2.text[:160]}"
