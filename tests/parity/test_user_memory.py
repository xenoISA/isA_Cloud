"""Parity smoke for the **user-memory** service (memory_service).

Mixed auth surface (from microservices/memory_service/main.py):
  - The generic CRUD routes (`GET /api/v1/memories`, `GET/PUT/DELETE
    /api/v1/memories/{memory_type}/{memory_id}`) are auth-gated via
    `require_auth_or_internal_service` and enforce per-user ownership (#485).
  - Health, stats, the factual-extract create path, and the state lifecycle
    routes have no FastAPI auth dependency (the extract path *forwards* the
    bearer token to isA_Model but does not require it). We still pass
    `auth_headers` on the gated reads so they exercise the real authed path.

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (401/403/404/422 are all acceptable parity outcomes),
never specific bodies or 200s — payload/auth/vector nuances make those brittle.

Endpoints exercised:
  - GET  /api/v1/memories/health                                   (liveness)
  - GET  /api/v1/memories/stats?user_id=...                        (stats)
  - GET  /api/v1/memories?user_id=...&memory_type=factual          (list, auth)
  - POST /api/v1/memories/factual/extract                          (create)
        body: StoreFactualMemoryRequest{user_id, dialog_content, importance_score}
  - GET  /api/v1/memories/factual/{memory_id}?user_id=...          (read back, auth)
  - DELETE /api/v1/memories/factual/{memory_id}?user_id=...        (cleanup, auth)
  - GET  /api/v1/memories/state?user_id=...                        (state read)
  - POST /api/v1/memories/pause   body {user_id}                   (pause)
  - POST /api/v1/memories/resume  body {user_id}                   (resume)
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-memory"
USER_ID = "parity-smoke-user"


def test_user_memory_health():
    """Service health endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/memories/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/api/v1/memories/health 5xx: {r.text[:160]}"


def test_user_memory_stats():
    """Per-user stats — empty user should resolve (no 5xx)."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/memories/stats?user_id={USER_ID}")
    assert r.status < 500, f"memory stats 5xx: {r.text[:160]}"


def test_user_memory_list(auth_headers):
    """List the main memories collection — auth-gated read, must not 5xx."""
    c = Client(SERVICE)
    r = c.get(
        f"/api/v1/memories?user_id={USER_ID}&memory_type=factual&limit=50",
        headers=auth_headers,
    )
    assert r.status < 500, f"list memories 5xx: {r.text[:160]}"


def test_user_memory_extract_read_delete(auth_headers, cleanup):
    """CRUD parity: extract a factual memory -> read back -> auto-delete on teardown.

    Self-cleaning so it is safe to run against prod. We register the DELETE the
    moment a memory id is observed in the create response, then read it back.
    Only parity-level assertions: every call must be < 500.
    """
    c = Client(SERVICE)
    payload = {
        "user_id": USER_ID,
        "dialog_content": "parity-smoke fact: the capital of France is Paris",
        "importance_score": 0.5,
    }

    r = c.post(
        "/api/v1/memories/factual/extract",
        json_body=payload,
        headers=auth_headers,
    )
    assert r.status < 500, f"factual extract 5xx: {r.text[:160]}"

    # Resolve a memory id from the MemoryOperationResult, if the extract
    # produced one, and register cleanup immediately.
    memory_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        memory_id = body.get("memory_id") or body.get("id")
        data = body.get("data")
        if not memory_id and isinstance(data, dict):
            memory_id = data.get("memory_id") or data.get("id")
        if not memory_id and isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                memory_id = first.get("memory_id") or first.get("id")
        if memory_id:
            cleanup(
                c,
                f"/api/v1/memories/factual/{memory_id}?user_id={USER_ID}",
            )

    # Read the resource back by id (auth-gated, ownership-enforced) — no 5xx.
    if memory_id:
        r2 = c.get(
            f"/api/v1/memories/factual/{memory_id}?user_id={USER_ID}",
            headers=auth_headers,
        )
        assert r2.status < 500, f"get memory 5xx: {r2.text[:160]}"


def test_user_memory_state_lifecycle():
    """State lifecycle: read state -> pause -> resume. Parity-level (no 5xx)."""
    c = Client(SERVICE)

    r = c.get(f"/api/v1/memories/state?user_id={USER_ID}")
    assert r.status < 500, f"get state 5xx: {r.text[:160]}"

    rp = c.post("/api/v1/memories/pause", json_body={"user_id": USER_ID})
    assert rp.status < 500, f"pause 5xx: {rp.text[:160]}"

    rr = c.post("/api/v1/memories/resume", json_body={"user_id": USER_ID})
    assert rr.status < 500, f"resume 5xx: {rr.text[:160]}"
