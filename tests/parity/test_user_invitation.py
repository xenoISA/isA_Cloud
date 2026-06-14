"""Parity smoke for the **user-invitation** service (invitation_service).

Mostly auth-gated: invitation create/list/accept/cancel/resend all resolve the
caller via `get_user_id`, which raises 401 without a valid bearer/api-key/internal
secret. The `auth_headers` fixture supplies a real bootstrapped token (and
auto-skips when auth is unavailable). Health/info and get-by-token are public.

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (401/403/404/422 are all acceptable parity outcomes),
never specific bodies or 200s — payload/auth/org-membership nuances make those
brittle. (Create routes call out to the organization service to authz the
caller; a 5xx there is exactly the cross-service breakage we hunt.)

Endpoints exercised (from microservices/invitation_service/main.py):
  - GET    /health                                              (public liveness)
  - GET    /api/v1/invitations/health                           (public)
  - GET    /api/v1/invitations/info                             (public)
  - GET    /api/v1/invitations/organizations/{org_id}           (list, auth)
  - POST   /api/v1/invitations/organizations/{org_id}           (create, auth)
        body: InvitationCreateRequest{email (req), role, message}
  - GET    /api/v1/invitations/{invitation_token}              (read by token, public)
  - DELETE /api/v1/invitations/{invitation_id}                 (cancel, auth -> cleanup)
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-invitation"

# A clearly-fake org id for the auth-gated list/create parity calls. The service
# will reject membership/permission (403/404) or validate (422) — all < 500.
ORG_ID = "org_parity_smoke"


def test_user_invitation_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_invitation_info():
    """Public service-info endpoint — reachable, no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/invitations/info")
    assert r.status < 500, f"info 5xx: {r.text[:160]}"


def test_user_invitation_list(auth_headers):
    """List an org's invitations (auth-gated) — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get(
        f"/api/v1/invitations/organizations/{ORG_ID}?limit=10&offset=0",
        headers=auth_headers,
    )
    assert r.status < 500, f"list invitations 5xx: {r.text[:160]}"


def test_user_invitation_get_by_token():
    """Public get-by-token path — a fake token should resolve to 404/400, never 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/invitations/tok_parity_does_not_exist")
    assert r.status < 500, f"get-by-token 5xx: {r.text[:160]}"


def test_user_invitation_create_read_delete(auth_headers, cleanup):
    """CRUD parity: create invitation -> read by token -> auto-cancel on teardown.

    Self-cleaning so it is safe to run against prod. We register the DELETE the
    moment the resource is (or may have been) created, then read it back by its
    returned token. Only parity-level assertions: every call must be < 500.

    The minimal valid body for InvitationCreateRequest is just an email; role
    defaults to "member". Org-membership/permission checks (which fan out to the
    organization service) may reject with 4xx — that is acceptable parity.
    """
    c = Client(SERVICE)
    payload = {
        "email": "parity-smoke@example.com",
        "role": "member",
        "message": "parity-smoke",
    }

    r = c.post(
        f"/api/v1/invitations/organizations/{ORG_ID}",
        json_body=payload,
        headers=auth_headers,
    )
    assert r.status < 500, f"create invitation 5xx: {r.text[:160]}"

    # Register cleanup immediately if the create succeeded, then read back.
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        inv_id = body.get("invitation_id")
        token = body.get("invitation_token")
        if inv_id:
            cleanup(c, f"/api/v1/invitations/{inv_id}")
        if token:
            r2 = c.get(f"/api/v1/invitations/{token}")
            assert r2.status < 500, f"get invitation by token 5xx: {r2.text[:160]}"
