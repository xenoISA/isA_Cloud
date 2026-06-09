"""Parity smoke for the **user-event** service (event_service).

Mostly auth-gated: per routes_registry.py, the functional event endpoints
(`/api/v1/events/create`, `/batch`, `/{event_id}`, `/query`, `/statistics`,
`/subscriptions*`, `/processors*`, `/stream/*`, `/replay`, `/projections/*`)
are all `auth_required=True`. Only `/`, `/health`, `/api/v1/events/health`,
`/api/v1/events/frontend[/batch]` and `/webhooks/rudderstack` are public.

The `auth_headers` fixture supplies a real bootstrapped token and auto-skips
the authed tests when auth is unavailable. We attach it to every gated call.

Identity note: the handlers take `user_id` inside the request body (NOT derived
from the JWT). We pass a clearly-fake test user id AND the bearer token.

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (401/403/404/422 are all acceptable parity outcomes),
never specific bodies or 200s — payload/auth nuances make those brittle.

CRUD coverage: the cleanest create->delete lifecycle this service exposes is
event *subscriptions* (POST/GET/DELETE /api/v1/events/subscriptions). Raw
events have a create + read-back but no DELETE, so we exercise create->read
without leaving anything DELETE-able behind (events are append-only by design).

Endpoints exercised (from microservices/event_service/main.py + routes_registry.py):
  - GET  /health                                   (public liveness)
  - GET  /api/v1/events/health                     (public liveness, API v1)
  - POST /api/v1/events/frontend                   (public frontend collection)
  - GET  /api/v1/events/statistics                 (auth, list/read aggregate)
  - POST /api/v1/events/query                      (auth, list events)
  - GET  /api/v1/events/subscriptions              (auth, list)
  - POST /api/v1/events/create                     (auth, create event)
        body: EventCreateRequest{event_type required; event_source/category opt}
  - GET  /api/v1/events/{event_id}                 (auth, read back)
  - POST /api/v1/events/subscriptions              (auth, create -> cleanup)
        body: EventSubscription{event_types required}
  - DELETE /api/v1/events/subscriptions/{id}       (auth, delete -> cleanup)
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-event"

# Clearly-fake parity test identity (not a real user).
TEST_USER = "usr_parity_smoke"


def test_user_event_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_event_health_apiv1():
    """API-v1 health endpoint — touches the service deps probe; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/events/health")
    assert r.status < 500, f"/api/v1/events/health 5xx: {r.text[:160]}"


def test_user_event_frontend_collect():
    """Public frontend-event collection — exercises the ingest path; no 5xx.

    FrontendEvent requires only `event_type`; `category` defaults. If the NATS
    stream is unavailable the handler returns a structured error (still <500).
    """
    c = Client(SERVICE)
    payload = {
        "event_type": "parity_smoke",
        "category": "user_interaction",
        "user_id": TEST_USER,
        "data": {"source": "parity-smoke"},
    }
    r = c.post("/api/v1/events/frontend", json_body=payload)
    assert r.status < 500, f"frontend collect 5xx: {r.text[:160]}"


def test_user_event_statistics(auth_headers):
    """Statistics aggregate read — auth-gated; resolves without a 5xx."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/events/statistics?user_id={TEST_USER}", headers=auth_headers)
    assert r.status < 500, f"statistics 5xx: {r.text[:160]}"


def test_user_event_query(auth_headers):
    """Query the main events collection — must resolve without a 5xx.

    Required fields (from EventQueryRequest): none are mandatory; limit/offset
    have defaults. We pass a clearly-fake user filter and a small page.
    """
    c = Client(SERVICE)
    payload = {"user_id": TEST_USER, "limit": 10, "offset": 0}
    r = c.post("/api/v1/events/query", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"query events 5xx: {r.text[:160]}"


def test_user_event_list_subscriptions(auth_headers):
    """List event subscriptions — auth-gated read path; no 5xx expected."""
    c = Client(SERVICE)
    r = c.get("/api/v1/events/subscriptions", headers=auth_headers)
    assert r.status < 500, f"list subscriptions 5xx: {r.text[:160]}"


def test_user_event_create_and_read(auth_headers):
    """Create an event -> read it back by id. Parity-level (no 5xx).

    Events are append-only (no DELETE endpoint), so nothing is registered for
    cleanup here — a single fake test event is the minimal, prod-safe footprint.
    Required field (from EventCreateRequest): event_type. event_source and
    event_category default to backend/user_action server-side.
    """
    c = Client(SERVICE)
    payload = {
        "event_type": "parity.smoke",
        "event_source": "backend",
        "event_category": "user_action",
        "user_id": TEST_USER,
        "data": {"name": "parity-smoke"},
    }

    r = c.post("/api/v1/events/create", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"create event 5xx: {r.text[:160]}"

    # Resolve the returned event_id when the create succeeded; fall back to a
    # representative id otherwise (still a valid read path).
    event_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        event_id = body.get("event_id") or body.get("id")

    lookup_id = event_id if event_id is not None else "parity-smoke-missing"
    r2 = c.get(f"/api/v1/events/{lookup_id}", headers=auth_headers)
    assert r2.status < 500, f"get event 5xx: {r2.text[:160]}"


def test_user_event_subscription_create_delete(auth_headers, cleanup):
    """CRUD parity: create subscription -> read-back via list -> auto-delete.

    Self-cleaning so it is safe to run against prod. We register the DELETE the
    moment the resource may have been created (keyed on the returned
    subscription_id). Only parity-level assertions: every call must be < 500.

    Required field (from EventSubscription): event_types (list). subscriber_name
    and subscriber_type default server-side.
    """
    c = Client(SERVICE)
    payload = {
        "subscriber_name": "parity-smoke",
        "subscriber_type": "service",
        "event_types": ["parity.smoke"],
        "enabled": True,
    }

    r = c.post("/api/v1/events/subscriptions", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"create subscription 5xx: {r.text[:160]}"

    # Register cleanup immediately if the create succeeded.
    sub_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        sub_id = body.get("subscription_id") or body.get("id")
        if sub_id is not None:
            cleanup(c, f"/api/v1/events/subscriptions/{sub_id}")

    # Read-back via the list endpoint (no per-id GET for subscriptions).
    r2 = c.get("/api/v1/events/subscriptions", headers=auth_headers)
    assert r2.status < 500, f"list subscriptions 5xx: {r2.text[:160]}"
