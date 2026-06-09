"""Parity smoke for the **user-account** service (account_service).

Auth-gated: every functional endpoint goes through `get_authenticated_caller`,
which raises 401 without a valid bearer/api-key. The `auth_headers` fixture
supplies a real bootstrapped token (and auto-skips when auth is unavailable).

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (401/403/404/422 are all acceptable parity outcomes),
never specific bodies or 200s — payload/auth nuances make those brittle.

Endpoints exercised (from microservices/account_service/main.py):
  - GET  /health                                 (public liveness)
  - GET  /api/v1/accounts                         (list, paginated, auth)
  - GET  /api/v1/accounts/search?query=...        (search, auth)
  - POST /api/v1/accounts/ensure                  (create/ensure, auth)
        body: AccountEnsureRequest{user_id, email, name}  (all required)
  - GET  /api/v1/accounts/profile/{user_id}       (read back, auth)
  - DELETE /api/v1/accounts/profile/{user_id}     (soft delete, auth -> cleanup)
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-account"


def test_user_account_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_account_list(auth_headers):
    """List the main accounts collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/accounts?page=1&page_size=50", headers=auth_headers)
    assert r.status < 500, f"list accounts 5xx: {r.text[:160]}"


def test_user_account_search(auth_headers):
    """Search endpoint — exercises the auth-gated read path; no 5xx expected."""
    c = Client(SERVICE)
    r = c.get("/api/v1/accounts/search?query=parity&limit=10", headers=auth_headers)
    assert r.status < 500, f"search accounts 5xx: {r.text[:160]}"


def test_user_account_ensure_read_delete(auth_headers, cleanup):
    """CRUD parity: ensure account -> read back -> auto soft-delete on teardown.

    Self-cleaning so it is safe to run against prod. We register the DELETE the
    moment the resource is (or may have been) created, then read it back. Only
    parity-level assertions: every call must be < 500.
    """
    c = Client(SERVICE)
    user_id = "usr_parity_smoke"
    payload = {
        "user_id": user_id,
        "email": "parity-smoke@example.com",
        "name": "parity-smoke",
    }

    r = c.post("/api/v1/accounts/ensure", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"ensure account 5xx: {r.text[:160]}"

    # Register cleanup immediately if the create succeeded (idempotent ensure):
    # resolve the real id from the response when present, else fall back to ours.
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        created_id = body.get("user_id") or user_id
        cleanup(c, f"/api/v1/accounts/profile/{created_id}")

    # Read the resource back by id — still parity-level (no 5xx).
    r2 = c.get(f"/api/v1/accounts/profile/{user_id}", headers=auth_headers)
    assert r2.status < 500, f"get profile 5xx: {r2.text[:160]}"
