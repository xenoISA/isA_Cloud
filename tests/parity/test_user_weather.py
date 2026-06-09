"""Parity smoke tests for the user-weather service.

Source of truth: isA_user/microservices/weather_service (main.py, models.py).

Endpoints exercised:
  - GET  /api/v1/weather/current?location=&units=        (public read)
  - GET  /api/v1/weather/forecast?location=&days=&units= (public read)
  - GET  /api/v1/weather/alerts?location=                (public read)
  - POST /api/v1/weather/locations                       (create favorite)
  - GET  /api/v1/weather/locations/{user_id}             (list by user)
  - DELETE /api/v1/weather/locations/{id}?user_id=       (cleanup)

Parity-level assertions only: we assert no 5xx (the cross-service / config bug
we hunt). 401/403/404/422 are all acceptable — upstream weather-API keys may be
absent, locations may need auth, etc. The signal is "service reachable + no 5xx".
"""

SERVICE = "user-weather"


def test_user_weather_current_read(http):
    """GET current weather for a known location must not 5xx."""
    c = http(SERVICE)
    r = c.get("/api/v1/weather/current?location=London&units=metric")
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"5xx from current weather: {r.status} {r.text}"


def test_user_weather_forecast_read(http):
    """GET multi-day forecast must not 5xx."""
    c = http(SERVICE)
    r = c.get("/api/v1/weather/forecast?location=London&days=5&units=metric")
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"5xx from forecast: {r.status} {r.text}"


def test_user_weather_alerts_read(http):
    """GET active alerts must not 5xx (alerts array may be empty)."""
    c = http(SERVICE)
    r = c.get("/api/v1/weather/alerts?location=Miami")
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"5xx from alerts: {r.status} {r.text}"


def test_user_weather_locations_list(http, auth_headers):
    """GET a user's saved locations must not 5xx."""
    c = http(SERVICE)
    r = c.get("/api/v1/weather/locations/parity-smoke-user", headers=auth_headers)
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"5xx from locations list: {r.status} {r.text}"


def test_user_weather_location_crud(http, auth_headers, cleanup):
    """Create -> verify -> delete a favorite location; self-cleaning, prod-safe.

    Required fields per LocationSaveRequest: user_id, location.
    """
    c = http(SERVICE)
    user_id = "parity-smoke-user"
    payload = {
        "user_id": user_id,
        "location": "parity-smoke",
        "latitude": 0.0,
        "longitude": 0.0,
        "is_default": False,
        "nickname": "parity-smoke",
    }

    r = c.post("/api/v1/weather/locations", json_body=payload, headers=auth_headers)
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"5xx from create location: {r.status} {r.text}"

    if r.ok:
        body = r.json() or {}
        loc_id = body.get("id")
        if loc_id is not None:
            # Register cleanup immediately so test data never lingers.
            cleanup(c, f"/api/v1/weather/locations/{loc_id}?user_id={user_id}")
            # Read back via the user's location list.
            g = c.get(f"/api/v1/weather/locations/{user_id}", headers=auth_headers)
            assert g.status != 0, "service unreachable on read-back"
            assert g.status < 500, f"5xx reading back location: {g.status} {g.text}"
