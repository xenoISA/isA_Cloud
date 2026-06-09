"""Parity smoke for the **user-device** service (device_service).

Auth-gated: device management endpoints require a user JWT (auth_required=True
in routes_registry.py). The `auth_headers` fixture supplies a real bootstrapped
token and auto-skips when auth is unavailable, so the public health checks still
run everywhere.

Parity signal = no 5xx + inter-service calls resolve (the device service fans out
to auth_service / account_service / MQTT — a 5xx is the regression we hunt). We
assert ONLY `r.status < 500`; 401/403/404/422 are all acceptable parity outcomes.
We never assert specific bodies or 200s — payload/auth nuances make those brittle.

Endpoints exercised (from microservices/device_service/routes_registry.py + main.py):
  - GET  /health                          (public liveness)
  - GET  /api/v1/devices/health            (public service health)
  - GET  /api/v1/service/stats             (public service stats)
  - GET  /api/v1/devices?limit=&offset=    (list user devices, auth)
  - GET  /api/v1/devices?device_type=...   (filter by type, auth)
  - GET  /api/v1/devices/stats             (device statistics, auth)
  - POST /api/v1/devices                   (register device, auth)
        body: DeviceRegistrationRequest{device_name, device_type, manufacturer,
              model, serial_number, firmware_version, connectivity_type} (required)
  - GET  /api/v1/devices/{device_id}       (read back, auth)
  - DELETE /api/v1/devices/{device_id}     (decommission, auth -> cleanup)
"""

from __future__ import annotations

import os
import time

from conftest import Client

SERVICE = "user-device"


def test_user_device_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_device_service_stats():
    """Public service-stats endpoint (auth_required=False) — no 5xx expected."""
    c = Client(SERVICE)
    r = c.get("/api/v1/service/stats")
    assert r.status < 500, f"/api/v1/service/stats 5xx: {r.text[:160]}"


def test_user_device_list(auth_headers):
    """List the main devices collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/devices?limit=10&offset=0", headers=auth_headers)
    assert r.status < 500, f"list devices 5xx: {r.text[:160]}"


def test_user_device_list_filtered(auth_headers):
    """Filtered list (by device_type) — exercises the query-param read path."""
    c = Client(SERVICE)
    r = c.get("/api/v1/devices?device_type=smart_frame", headers=auth_headers)
    assert r.status < 500, f"filtered list devices 5xx: {r.text[:160]}"


def test_user_device_stats(auth_headers):
    """Device statistics endpoint — auth-gated aggregate read; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/devices/stats", headers=auth_headers)
    assert r.status < 500, f"device stats 5xx: {r.text[:160]}"


def test_user_device_register_read_delete(auth_headers, cleanup):
    """CRUD parity: register device -> read back -> auto-decommission on teardown.

    Self-cleaning so it is safe to run against prod. We register the DELETE the
    moment the device is created (resolving the real device_id from the response),
    then read it back. Only parity-level assertions: every call must be < 500.
    """
    c = Client(SERVICE)
    # Clearly-fake, unique test data so repeat runs don't collide on serial_number.
    suffix = f"{int(time.time())}-{os.getpid()}"
    payload = {
        "device_name": "parity-smoke",
        "device_type": "smart_frame",
        "manufacturer": "parity-smoke",
        "model": "PARITY-SMOKE",
        "serial_number": f"PARITY-{suffix}",
        "firmware_version": "1.0.0",
        "connectivity_type": "wifi",
    }

    r = c.post("/api/v1/devices", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"register device 5xx: {r.text[:160]}"

    # Register cleanup immediately if the create succeeded — resolve the real id.
    device_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        device_id = body.get("device_id")
        if device_id:
            cleanup(c, f"/api/v1/devices/{device_id}")

    # Read the resource back by id — still parity-level (no 5xx). Fall back to a
    # synthetic id when the create did not return one, so the read path is still
    # exercised against the service (a 404 is an acceptable parity outcome).
    lookup_id = device_id or f"parity-smoke-{suffix}"
    r2 = c.get(f"/api/v1/devices/{lookup_id}", headers=auth_headers)
    assert r2.status < 500, f"get device 5xx: {r2.text[:160]}"
