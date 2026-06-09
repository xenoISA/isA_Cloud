"""Parity smoke for the **user-project-sharing** service (project_sharing_service).

Public service (auth_required=False per SN-PARITY-AUDIT): the invite/list/accept/
revoke endpoints do NOT go through an auth dependency — the accept path is gated
by the invite token itself, not a bearer. So no `auth_headers` are passed here.

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (400/403/404/422/429 are all acceptable parity outcomes),
never specific bodies or 200s — payload/idempotency/rate-limit nuances make
those brittle.

Endpoints exercised (from microservices/project_sharing_service/main.py):
  - GET    /health                                              (public liveness)
  - GET    /api/v1/projects/{project_id}/shares                 (list, optional ?status=)
  - POST   /api/v1/projects/{project_id}/shares                 (invite -> create)
        body: CreateShareRequest{invitee_email (required), role (default viewer)}
  - PATCH  /api/v1/projects/{project_id}/shares/{share_id}      (update role)
        body: UpdateShareRequest{role (required)}
  - DELETE /api/v1/projects/{project_id}/shares/{share_id}      (revoke -> cleanup)
  - POST   /api/v1/shares/accept/{token}                        (public accept via token)
        body: AcceptShareRequest{invitee_user_id (required)}
"""

from __future__ import annotations

from conftest import Client, request

SERVICE = "user-project-sharing"

# A stable, clearly-fake project UUID for parity test data.
PARITY_PROJECT_ID = "550e8400-e29b-41d4-a716-446655440099"


def test_user_project_sharing_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_project_sharing_list():
    """List shares for a project — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/projects/{PARITY_PROJECT_ID}/shares")
    assert r.status < 500, f"list shares 5xx: {r.text[:160]}"


def test_user_project_sharing_list_filtered():
    """List shares filtered by status — exercises the query-param read path."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/projects/{PARITY_PROJECT_ID}/shares?status=pending")
    assert r.status < 500, f"list filtered shares 5xx: {r.text[:160]}"


def test_user_project_sharing_invite_read_update_revoke(cleanup):
    """CRUD parity: invite -> list/read -> update role -> auto-revoke on teardown.

    Self-cleaning so it is safe to run against prod. We register the DELETE the
    moment a share id is returned, then read it back and update its role. Only
    parity-level assertions: every call must be < 500.
    """
    c = Client(SERVICE)
    payload = {
        "invitee_email": "parity-smoke@example.com",
        "role": "editor",
    }

    r = c.post(f"/api/v1/projects/{PARITY_PROJECT_ID}/shares", json_body=payload)
    assert r.status < 500, f"invite 5xx: {r.text[:160]}"

    share_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        share_id = body.get("id")
        if share_id:
            # Register revoke immediately so test data is never left behind.
            cleanup(c, f"/api/v1/projects/{PARITY_PROJECT_ID}/shares/{share_id}")

    # Read back via the list endpoint — still parity-level (no 5xx).
    r2 = c.get(f"/api/v1/projects/{PARITY_PROJECT_ID}/shares")
    assert r2.status < 500, f"list after invite 5xx: {r2.text[:160]}"

    # Update the role if we got a real share id back. The route is PATCH (not
    # PUT), so we use the harness `request` helper directly to hit it honestly
    # rather than send a PUT that would only ever 405.
    if share_id:
        r3 = request(
            "PATCH",
            c.base + f"/api/v1/projects/{PARITY_PROJECT_ID}/shares/{share_id}",
            json_body={"role": "viewer"},
        )
        assert r3.status < 500, f"update role 5xx: {r3.text[:160]}"


def test_user_project_sharing_accept_token_public():
    """Public accept-via-token path — token IS the auth, no bearer required.

    Uses a clearly-fake token; we expect a 404/400/422 (no such invite), never a
    5xx. This confirms the public accept route is wired and resolves cleanly.
    """
    c = Client(SERVICE)
    r = c.post(
        "/api/v1/shares/accept/parity-smoke-nonexistent-token",
        json_body={"invitee_user_id": "usr_parity_smoke"},
    )
    assert r.status < 500, f"accept token 5xx: {r.text[:160]}"
