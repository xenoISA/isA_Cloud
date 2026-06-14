"""Parity smoke for the **user-sharing** service (sharing_service).

Token-based share-link generation for sessions. The service splits into two
surfaces (microservices/sharing_service/main.py + routes_registry.py):

  - **auth-gated** (auth_required=True): create / list / revoke shares. Every one
    of these also takes a `user_id` query param (the auth-scoped owner) and a
    `session_id` path param. Creating a share fans out to the *session service*
    (clients/session_client.py) to snapshot the session — a 5xx there is exactly
    the cross-service breakage this parity suite hunts.
  - **public** (auth_required=False, "the token IS the auth"): health and
    GET share-by-token. A bogus token must resolve to 404/410, never 5xx.

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (401/403/404/410/422 are all acceptable parity outcomes),
never specific bodies or 200s — payload / auth / session-existence nuances make
those brittle.

Endpoints exercised:
  - GET    /health                                      (public liveness)
  - GET    /api/v1/sharing/health                       (public)
  - GET    /api/v1/sessions/{session_id}/shares         (list, auth + user_id)
  - POST   /api/v1/sessions/{session_id}/share          (create, auth + user_id)
        body: ShareCreateRequest{permissions, expires_in_hours, ...} (all optional)
  - GET    /api/v1/shares/{token}                        (public read by token)
  - DELETE /api/v1/shares/{token}?user_id=...            (revoke, auth -> cleanup)
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-sharing"

# Clearly-fake owner + session ids for the auth-gated parity calls. The service
# will reject ownership/permission (403/404) or find no session (4xx) — all < 500.
USER_ID = "usr_parity_smoke"
SESSION_ID = "sess_parity_smoke"


def test_user_sharing_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_sharing_api_health():
    """Public API-v1 health endpoint — reachable, no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/sharing/health")
    assert r.status < 500, f"api health 5xx: {r.text[:160]}"


def test_user_sharing_list(auth_headers):
    """List a session's shares (auth-gated + user_id) — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get(
        f"/api/v1/sessions/{SESSION_ID}/shares?user_id={USER_ID}",
        headers=auth_headers,
    )
    assert r.status < 500, f"list shares 5xx: {r.text[:160]}"


def test_user_sharing_access_by_token():
    """Public read-by-token path — a fake token resolves to 404/410, never 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/shares/tok_parity_does_not_exist")
    assert r.status < 500, f"access share by token 5xx: {r.text[:160]}"


def test_user_sharing_create_read_delete(auth_headers, cleanup):
    """CRUD parity: create share -> read by token (public) -> auto-revoke on teardown.

    Self-cleaning so it is safe to run against prod. We register the revoke DELETE
    (with the owner's user_id baked into the path) the moment the resource is
    created, then read it back by its returned public token. Only parity-level
    assertions: every call must be < 500.

    ShareCreateRequest has no required fields (all optional, permissions defaults
    to view_only); we send a minimal valid body. The session-snapshot fan-out to
    the session service may reject (4xx) when the fake session does not exist —
    that is acceptable parity; a 5xx is the bug.
    """
    c = Client(SERVICE)
    payload = {"permissions": "view_only", "expires_in_hours": 24}

    r = c.post(
        f"/api/v1/sessions/{SESSION_ID}/share?user_id={USER_ID}",
        json_body=payload,
        headers=auth_headers,
    )
    assert r.status < 500, f"create share 5xx: {r.text[:160]}"

    # Register revoke cleanup immediately if the create succeeded, then read back.
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        token = body.get("share_token")
        if token:
            # Revoke is owner-only and needs user_id as a query param.
            cleanup(c, f"/api/v1/shares/{token}?user_id={USER_ID}")
            # Public read-by-token (no auth — the token is the auth).
            r2 = c.get(f"/api/v1/shares/{token}")
            assert r2.status < 500, f"access created share 5xx: {r2.text[:160]}"
