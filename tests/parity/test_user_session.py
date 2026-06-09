"""Parity smoke for the **user-session** service (session_service).

Auth surface (from microservices/session_service/routes_registry.py + main.py):
  - Health routes (`/health`, `/api/v1/sessions/health`) are public.
  - The session stats endpoint (`/api/v1/sessions/stats`) has no FastAPI auth
    dependency on the handler.
  - All session CRUD, message, search, star and listing routes are declared
    `auth_required=True`. We pass `auth_headers` on those so they exercise the
    real authed path.

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (401/403/404/422 are all acceptable parity outcomes),
never specific bodies or 200s — auth/ownership/db nuances make those brittle.

Endpoints exercised (real paths + request models):
  - GET    /api/v1/sessions/health                                  (liveness, public)
  - GET    /api/v1/sessions/stats                                   (stats)
  - GET    /api/v1/sessions?user_id=...                             (list, auth)
  - POST   /api/v1/sessions                                         (create, auth)
        body: SessionCreateRequest{user_id, conversation_data, metadata}
  - GET    /api/v1/sessions/{session_id}?user_id=...               (read back, auth)
  - DELETE /api/v1/sessions/{session_id}?user_id=...              (end/cleanup, auth)
  - POST   /api/v1/sessions/{session_id}/messages                  (add message, auth)
        body: MessageCreateRequest{role, content, ...}
  - GET    /api/v1/sessions/{session_id}/messages                  (list messages, auth)
  - GET    /api/v1/sessions/search?q=...&user_id=...              (full-text search, auth)
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-session"
USER_ID = "parity-smoke-user"


def test_user_session_health():
    """Service health endpoint must be reachable and not 5xx (public)."""
    c = Client(SERVICE)
    r = c.get("/api/v1/sessions/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/api/v1/sessions/health 5xx: {r.text[:160]}"


def test_user_session_stats():
    """Session service stats — must resolve (no 5xx)."""
    c = Client(SERVICE)
    r = c.get("/api/v1/sessions/stats")
    assert r.status < 500, f"session stats 5xx: {r.text[:160]}"


def test_user_session_list(auth_headers):
    """List the main sessions collection — auth-gated read, must not 5xx.

    The handler requires a `user_id` query param (FastAPI Query(...)).
    """
    c = Client(SERVICE)
    r = c.get(
        f"/api/v1/sessions?user_id={USER_ID}&page=1&page_size=50",
        headers=auth_headers,
    )
    assert r.status < 500, f"list sessions 5xx: {r.text[:160]}"


def test_user_session_create_read_delete(auth_headers, cleanup):
    """CRUD parity: create a session -> read back -> auto-delete on teardown.

    Self-cleaning so it is safe to run against prod. We register the DELETE the
    moment a session_id is observed in the create response, then read it back.
    Only parity-level assertions: every call must be < 500.
    """
    c = Client(SERVICE)
    payload = {
        "user_id": USER_ID,
        "conversation_data": {},
        "metadata": {"source": "parity-smoke"},
    }

    r = c.post("/api/v1/sessions", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"create session 5xx: {r.text[:160]}"

    # Resolve a session_id from the SessionResponse, if create succeeded, and
    # register cleanup immediately (DELETE ends the session).
    session_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        session_id = body.get("session_id") or body.get("id")
        data = body.get("data")
        if not session_id and isinstance(data, dict):
            session_id = data.get("session_id") or data.get("id")
        if session_id:
            cleanup(
                c,
                f"/api/v1/sessions/{session_id}?user_id={USER_ID}",
            )

    # Read the resource back by id (auth-gated) — no 5xx.
    if session_id:
        r2 = c.get(
            f"/api/v1/sessions/{session_id}?user_id={USER_ID}",
            headers=auth_headers,
        )
        assert r2.status < 500, f"get session 5xx: {r2.text[:160]}"


def test_user_session_messages(auth_headers, cleanup):
    """Message flow parity: create session -> add message -> list messages.

    Each step is parity-level (no 5xx). Cleanup is registered as soon as a
    session_id is known so no test data is left behind.
    """
    c = Client(SERVICE)

    r = c.post(
        "/api/v1/sessions",
        json_body={"user_id": USER_ID, "conversation_data": {}, "metadata": {}},
        headers=auth_headers,
    )
    assert r.status < 500, f"create session 5xx: {r.text[:160]}"

    session_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        session_id = body.get("session_id") or body.get("id")
        if session_id:
            cleanup(c, f"/api/v1/sessions/{session_id}?user_id={USER_ID}")

    if session_id:
        msg = {
            "role": "user",
            "content": "parity-smoke test message",
            "message_type": "chat",
            "tokens_used": 10,
            "cost_usd": 0.001,
        }
        rm = c.post(
            f"/api/v1/sessions/{session_id}/messages",
            json_body=msg,
            headers=auth_headers,
        )
        assert rm.status < 500, f"add message 5xx: {rm.text[:160]}"

        rl = c.get(
            f"/api/v1/sessions/{session_id}/messages?page=1",
            headers=auth_headers,
        )
        assert rl.status < 500, f"list messages 5xx: {rl.text[:160]}"


def test_user_session_search(auth_headers):
    """Full-text search across sessions — auth-gated read, must not 5xx.

    Handler requires `q` and `user_id` query params (FastAPI Query(...)).
    """
    c = Client(SERVICE)
    r = c.get(
        f"/api/v1/sessions/search?q=parity&user_id={USER_ID}&limit=10",
        headers=auth_headers,
    )
    assert r.status < 500, f"session search 5xx: {r.text[:160]}"
