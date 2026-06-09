"""Parity smoke for the **user-organization** service (organization_service).

Auth-gated at the HTTP layer: every functional route in
`microservices/organization_service/main.py` resolves the caller via a
`get_current_user_id` dependency and the SN parity audit lists this service as
`auth_required=True`. So the functional tests pass `auth_headers` (a real
bootstrapped bearer token; the fixture auto-skips when auth is unavailable).
The health/info/stats endpoints are public (`auth_required=False` in
`routes_registry.py`) and are exercised without a token so they run everywhere.

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (400/401/403/404/409/422 are all acceptable parity
outcomes), never specific bodies or 200s — payload/auth nuances make those
brittle. The organization handlers wrap inner failures in HTTPException and the
app has a global handler, so a 5xx here is exactly the cross-service / DB
regression this suite hunts for.

Endpoints exercised (from main.py + routes_registry.py):
  - GET  /health                                          (public liveness)
  - GET  /api/v1/organization/info                         (service info, public)
  - GET  /api/v1/organization/stats                        (service stats, public)
  - GET  /api/v1/organization/organizations                (list user orgs)
  - GET  /api/v1/organization/organizations/context        (current org context)
  - GET  /api/v1/organization/admin/organizations          (admin list all)
  - POST /api/v1/organization/organizations                (create — the create)
        body: OrganizationCreateRequest{name, billing_email} (required)
  - GET  /api/v1/organization/organizations/{id}           (read by id)
  - DELETE /api/v1/organization/organizations/{id}         (delete — cleanup)

CRUD note: create returns an OrganizationResponse with a top-level
`organization_id`. The moment we get one back we register the DELETE path with
the `cleanup` fixture so no parity org is ever left behind (prod-safe), then
read it back by id — all assertions stay parity-level (< 500).
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-organization"

# Clearly-fake parity test data (never collides with real orgs/users).
TEST_ORG_NAME = "parity-smoke"
TEST_BILLING_EMAIL = "parity-smoke@example.com"


def test_user_organization_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_organization_info_and_stats():
    """Public info + stats endpoints — surface dependency wiring; no 5xx."""
    c = Client(SERVICE)
    ri = c.get("/api/v1/organization/info")
    assert ri.status < 500, f"organization/info 5xx: {ri.text[:160]}"
    rs = c.get("/api/v1/organization/stats")
    assert rs.status < 500, f"organization/stats 5xx: {rs.text[:160]}"


def test_user_organization_list(auth_headers):
    """List the caller's organizations — auth-gated read; must not 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/organization/organizations", headers=auth_headers)
    assert r.status < 500, f"list organizations 5xx: {r.text[:160]}"


def test_user_organization_context(auth_headers):
    """Read current org context — exercises the context path; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/organization/organizations/context", headers=auth_headers)
    assert r.status < 500, f"organizations/context 5xx: {r.text[:160]}"


def test_user_organization_admin_list(auth_headers):
    """Admin list-all (likely 403 for a normal token) — parity-level; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/organization/admin/organizations", headers=auth_headers)
    assert r.status < 500, f"admin/organizations 5xx: {r.text[:160]}"


def test_user_organization_create_verify_delete(auth_headers, cleanup):
    """CRUD parity: create -> register cleanup -> read by id (all < 500).

    POST a minimal valid OrganizationCreateRequest (name + billing_email are the
    only required fields). If a 2xx returns an organization_id we IMMEDIATELY
    register the DELETE path with `cleanup` (prod-safe self-cleaning) before any
    further calls, then read the org back by id. Assertions stay parity-level.
    """
    c = Client(SERVICE)

    payload = {
        "name": TEST_ORG_NAME,
        "billing_email": TEST_BILLING_EMAIL,
        "plan": "free",
    }

    r = c.post(
        "/api/v1/organization/organizations",
        json_body=payload,
        headers=auth_headers,
    )
    assert r.status < 500, f"create organization 5xx: {r.text[:160]}"

    org_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        org_id = body.get("organization_id")

    if org_id:
        # Register teardown DELETE the moment we have an id — never leak a resource.
        cleanup(c, f"/api/v1/organization/organizations/{org_id}")

        # Read the created resource back by id — still parity-level (no 5xx).
        rg = c.get(
            f"/api/v1/organization/organizations/{org_id}",
            headers=auth_headers,
        )
        assert rg.status < 500, f"get organization 5xx: {rg.text[:160]}"
