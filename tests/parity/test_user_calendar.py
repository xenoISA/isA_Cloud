"""Parity smoke for the **user-calendar** service (calendar_service).

Auth-gated: per routes_registry.py, every `/api/v1/calendar/*` functional
endpoint is `auth_required=True` (only `/`, `/health`, `/api/v1/calendar/health`
are public). The `auth_headers` fixture supplies a real bootstrapped token and
auto-skips when auth is unavailable.

Note on identity: the handlers in microservices/calendar_service/main.py take
`user_id` as an explicit query/body param (NOT derived from the JWT). So we pass
a clearly-fake test user id AND the bearer token. The DELETE/read-back endpoints
key on the returned `event_id`, so we register cleanup the moment a create may
have succeeded.

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (401/403/404/422 are all acceptable parity outcomes),
never specific bodies or 200s — payload/auth nuances make those brittle.

Endpoints exercised (from microservices/calendar_service/main.py):
  - GET  /health                                      (public liveness)
  - GET  /api/v1/calendar/events?user_id=...          (list, auth)
  - POST /api/v1/calendar/events                      (create, auth)
        body: EventCreateRequest{user_id, title, start_time, end_time} required
  - GET  /api/v1/calendar/events/{event_id}?user_id=  (read back, auth)
  - DELETE /api/v1/calendar/events/{event_id}?user_id=(delete, auth -> cleanup)
  - GET  /api/v1/calendar/upcoming?user_id=...        (upcoming view, auth)
  - GET  /api/v1/calendar/today?user_id=...           (today view, auth)
  - GET  /api/v1/calendar/sync/status?user_id=...     (sync status, auth)
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-calendar"

# Clearly-fake parity test identity (not a real user).
TEST_USER = "usr_parity_smoke"


def test_user_calendar_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_calendar_list(auth_headers):
    """List the main events collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get(
        f"/api/v1/calendar/events?user_id={TEST_USER}&limit=10&offset=0",
        headers=auth_headers,
    )
    assert r.status < 500, f"list events 5xx: {r.text[:160]}"


def test_user_calendar_upcoming(auth_headers):
    """Upcoming-events view — exercises the auth-gated read path; no 5xx."""
    c = Client(SERVICE)
    r = c.get(
        f"/api/v1/calendar/upcoming?user_id={TEST_USER}&days=7",
        headers=auth_headers,
    )
    assert r.status < 500, f"upcoming events 5xx: {r.text[:160]}"


def test_user_calendar_today(auth_headers):
    """Today-events view — auth-gated read path; no 5xx expected."""
    c = Client(SERVICE)
    r = c.get(
        f"/api/v1/calendar/today?user_id={TEST_USER}",
        headers=auth_headers,
    )
    assert r.status < 500, f"today events 5xx: {r.text[:160]}"


def test_user_calendar_sync_status(auth_headers):
    """Sync-status read — touches the external-sync code path; no 5xx."""
    c = Client(SERVICE)
    r = c.get(
        f"/api/v1/calendar/sync/status?user_id={TEST_USER}",
        headers=auth_headers,
    )
    assert r.status < 500, f"sync status 5xx: {r.text[:160]}"


def test_user_calendar_create_read_delete(auth_headers, cleanup):
    """CRUD parity: create event -> read back -> auto-delete on teardown.

    Self-cleaning so it is safe to run against prod. We register the DELETE the
    moment the resource may have been created (keyed on the returned event_id),
    then read it back. Only parity-level assertions: every call must be < 500.

    Required fields (from EventCreateRequest): user_id, title, start_time,
    end_time. Times are ISO-8601 datetimes; we use a clearly-fake test window.
    """
    c = Client(SERVICE)
    payload = {
        "user_id": TEST_USER,
        "title": "parity-smoke",
        "description": "parity smoke test event",
        "start_time": "2026-12-01T10:00:00+00:00",
        "end_time": "2026-12-01T11:00:00+00:00",
        "all_day": False,
        "timezone": "UTC",
        "category": "other",
    }

    r = c.post("/api/v1/calendar/events", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"create event 5xx: {r.text[:160]}"

    # Register cleanup immediately if the create succeeded — resolve the real
    # event_id from the response so teardown deletes the right resource.
    event_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        event_id = body.get("event_id") or body.get("id")
        if event_id is not None:
            cleanup(
                c,
                f"/api/v1/calendar/events/{event_id}?user_id={TEST_USER}",
            )

    # Read the resource back by id — still parity-level (no 5xx). Fall back to a
    # representative id when the create did not return one (still valid path).
    lookup_id = event_id if event_id is not None else "parity-smoke-missing"
    r2 = c.get(
        f"/api/v1/calendar/events/{lookup_id}?user_id={TEST_USER}",
        headers=auth_headers,
    )
    assert r2.status < 500, f"get event 5xx: {r2.text[:160]}"
