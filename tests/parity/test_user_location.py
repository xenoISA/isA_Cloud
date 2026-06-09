"""Parity smoke for the **user-location** service (location_service).

Auth-gated: every functional endpoint requires a user JWT (auth_required=True in
routes_registry.py; main.py guards them with Depends(get_authenticated_user_id),
which fans out to auth_service). The `auth_headers` fixture supplies a real
bootstrapped token and auto-skips when auth is unavailable, so the public health
checks still run everywhere.

Parity signal = no 5xx + inter-service calls resolve (location fans out to
auth_service / account_service / device_service / notification_service — a 5xx is
the regression we hunt). We assert ONLY `r.status < 500`; 401/403/404/422 are all
acceptable parity outcomes. We never assert specific bodies or 200s — payload/auth
nuances make those brittle.

Endpoints exercised (from microservices/location_service/main.py + routes_registry.py):
  - GET    /health                              (public liveness)
  - GET    /api/v1/location/health               (public service health, singular)
  - GET    /api/v1/geofences?limit=&offset=      (list user geofences, auth)
  - POST   /api/v1/geofences                     (create geofence, auth -> cleanup)
        body: GeofenceCreateRequest{name, shape_type, center_lat, center_lon,
              radius} (required for a circle)
  - GET    /api/v1/geofences/{geofence_id}       (read back, auth)
  - POST   /api/v1/places                        (create place, auth -> cleanup)
        body: PlaceCreateRequest{name, category, latitude, longitude} (required)
  - GET    /api/v1/places/{place_id}             (read back, auth)
  - POST   /api/v1/locations                     (report location, auth -> cleanup)
        body: LocationReportRequest{device_id, latitude, longitude, accuracy} (required)
  - GET    /api/v1/locations/device/{device_id}  (read device location, auth)
  - DELETE endpoints used for cleanup: /api/v1/geofences/{id}, /api/v1/places/{id},
        /api/v1/locations/{id}
"""

from __future__ import annotations

import os
import time

from conftest import Client

SERVICE = "user-location"


def _suffix() -> str:
    return f"{int(time.time())}-{os.getpid()}"


def test_user_location_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_location_service_health():
    """Public service-health endpoint (singular path, auth_required=False)."""
    c = Client(SERVICE)
    r = c.get("/api/v1/location/health")
    assert r.status < 500, f"/api/v1/location/health 5xx: {r.text[:160]}"


def test_user_location_list_geofences(auth_headers):
    """List the main geofences collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/geofences?limit=10&offset=0", headers=auth_headers)
    assert r.status < 500, f"list geofences 5xx: {r.text[:160]}"


def test_user_location_geofence_create_read_delete(auth_headers, cleanup):
    """CRUD parity: create geofence -> read back -> auto-delete on teardown.

    Self-cleaning so it is safe to run against prod. We register the DELETE the
    moment the geofence is created (resolving the real geofence_id from the
    response), then read it back. Only parity-level assertions: every call < 500.
    """
    c = Client(SERVICE)
    payload = {
        "name": f"parity-smoke-{_suffix()}",
        "description": "parity-smoke",
        "shape_type": "circle",
        "center_lat": 40.7128,
        "center_lon": -74.0060,
        "radius": 100.0,
        "trigger_on_enter": True,
        "trigger_on_exit": True,
    }

    r = c.post("/api/v1/geofences", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"create geofence 5xx: {r.text[:160]}"

    geofence_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        geofence_id = body.get("geofence_id") or (body.get("data") or {}).get(
            "geofence_id"
        )
        if geofence_id:
            cleanup(c, f"/api/v1/geofences/{geofence_id}")

    lookup_id = geofence_id or f"parity-smoke-{_suffix()}"
    r2 = c.get(f"/api/v1/geofences/{lookup_id}", headers=auth_headers)
    assert r2.status < 500, f"get geofence 5xx: {r2.text[:160]}"


def test_user_location_place_create_read_delete(auth_headers, cleanup):
    """CRUD parity: create place -> read back -> auto-delete on teardown."""
    c = Client(SERVICE)
    payload = {
        "name": f"parity-smoke-{_suffix()}",
        "category": "home",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "address": "123 Parity St",
    }

    r = c.post("/api/v1/places", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"create place 5xx: {r.text[:160]}"

    place_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        place_id = body.get("place_id") or (body.get("data") or {}).get("place_id")
        if place_id:
            cleanup(c, f"/api/v1/places/{place_id}")

    lookup_id = place_id or f"parity-smoke-{_suffix()}"
    r2 = c.get(f"/api/v1/places/{lookup_id}", headers=auth_headers)
    assert r2.status < 500, f"get place 5xx: {r2.text[:160]}"


def test_user_location_report_read_delete(auth_headers, cleanup):
    """CRUD parity: report a location -> read device location -> auto-delete.

    Exercises the core location-tracking write path and the device-location read
    path (which fans out to device_service). Parity-level only: no 5xx.
    """
    c = Client(SERVICE)
    device_id = f"parity-smoke-{_suffix()}"
    payload = {
        "device_id": device_id,
        "latitude": 40.7128,
        "longitude": -74.0060,
        "accuracy": 5.0,
        "location_method": "gps",
        "source": "device",
    }

    r = c.post("/api/v1/locations", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"report location 5xx: {r.text[:160]}"

    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        location_id = body.get("location_id") or (body.get("data") or {}).get(
            "location_id"
        )
        if location_id:
            cleanup(c, f"/api/v1/locations/{location_id}")

    r2 = c.get(f"/api/v1/locations/device/{device_id}", headers=auth_headers)
    assert r2.status < 500, f"get device location 5xx: {r2.text[:160]}"
