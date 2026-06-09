"""Parity smoke for the **user-membership** service (membership_service).

Public at the HTTP layer: the FastAPI handlers in
`microservices/membership_service/main.py` take only a `MembershipService`
dependency — there is NO auth dependency or auth middleware on the app, and the
SN parity audit lists this service as `auth_required=False`. So these tests run
without a bearer token (they work in every environment, even when auth is
unavailable).

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY `r.status < 500` (400/401/403/404/409/422 are all acceptable parity
outcomes), never specific bodies or 200s — payload/auth nuances make those
brittle. Every membership handler wraps inner failures in
`raise HTTPException(500, ...)` (and there is a global 500 exception handler), so
a 5xx here is exactly the cross-service / DB regression this suite hunts for.

Endpoints exercised (from microservices/membership_service/main.py):
  - GET  /health                                       (public liveness)
  - GET  /api/v1/membership/health                     (detailed health)
  - GET  /api/v1/memberships/info                       (service capabilities)
  - GET  /api/v1/memberships?user_id=...                 (list memberships, paged)
  - GET  /api/v1/memberships/stats                       (membership statistics)
  - GET  /api/v1/memberships/points/balance?user_id=...   (points balance)
  - GET  /api/v1/memberships/user/{user_id}              (membership by user)
  - POST /api/v1/memberships                             (enroll — the create)
        body: EnrollMembershipRequest{user_id} (required)
  - GET  /api/v1/memberships/{membership_id}            (read by id)
  - POST /api/v1/memberships/points/earn                 (earn points)
  - POST /api/v1/memberships/{membership_id}/cancel      (cancel — the undo)

CRUD note: enrollment returns an EnrollMembershipResponse and the membership has
NO DELETE route — the only undo is `POST .../{membership_id}/cancel`. So instead
of the generic DELETE-based `cleanup` fixture we self-clean in-test via cancel,
which keeps the test prod-safe and idempotent.
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-membership"

# Clearly-fake parity test identity (never collides with real users).
TEST_USER_ID = "usr_parity_membership_smoke"
TEST_ORG_ID = "org_parity_membership_smoke"


def test_user_membership_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_membership_detailed_health_and_info():
    """Detailed health + info endpoints — surface dependency wiring; no 5xx."""
    c = Client(SERVICE)
    rh = c.get("/api/v1/membership/health")
    assert rh.status < 500, f"membership/health 5xx: {rh.text[:160]}"
    ri = c.get("/api/v1/memberships/info")
    assert ri.status < 500, f"memberships/info 5xx: {ri.text[:160]}"


def test_user_membership_list():
    """List the main memberships collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get(
        f"/api/v1/memberships?user_id={TEST_USER_ID}"
        f"&organization_id={TEST_ORG_ID}&page=1&page_size=50"
    )
    assert r.status < 500, f"list memberships 5xx: {r.text[:160]}"


def test_user_membership_stats():
    """Read service-wide stats — exercises the DB aggregation path; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/memberships/stats")
    assert r.status < 500, f"memberships/stats 5xx: {r.text[:160]}"


def test_user_membership_points_balance():
    """Read a user's points balance by id — auth-free read path; no 5xx."""
    c = Client(SERVICE)
    r = c.get(
        f"/api/v1/memberships/points/balance?user_id={TEST_USER_ID}"
        f"&organization_id={TEST_ORG_ID}"
    )
    assert r.status < 500, f"points/balance 5xx: {r.text[:160]}"


def test_user_membership_get_by_user():
    """Read a membership by user id — resolves a (likely 404) read; no 5xx."""
    c = Client(SERVICE)
    r = c.get(f"/api/v1/memberships/user/{TEST_USER_ID}?organization_id={TEST_ORG_ID}")
    assert r.status < 500, f"memberships/user 5xx: {r.text[:160]}"


def test_user_membership_enroll_verify_and_cancel():
    """CRUD parity: enroll (create) -> read by id -> earn points -> cancel (undo).

    Enrollment is the create endpoint. The membership has no DELETE route, so we
    self-clean in-test via the cancel endpoint (prod-safe, idempotent) the moment
    a membership_id is returned. All assertions stay parity-level: every call
    must be < 500.
    """
    c = Client(SERVICE)

    payload = {
        "user_id": TEST_USER_ID,
        "organization_id": TEST_ORG_ID,
        "enrollment_source": "parity-smoke",
    }

    r = c.post("/api/v1/memberships", json_body=payload)
    assert r.status < 500, f"enroll 5xx: {r.text[:160]}"

    membership_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        membership = body.get("membership") or {}
        if isinstance(membership, dict):
            membership_id = membership.get("membership_id")

    try:
        if membership_id:
            # Read the created resource back by id — parity-level (no 5xx).
            rg = c.get(f"/api/v1/memberships/{membership_id}")
            assert rg.status < 500, f"get membership 5xx: {rg.text[:160]}"

        # Earn points — exercises the points write path against the enrollment.
        earn = c.post(
            "/api/v1/memberships/points/earn",
            json_body={
                "user_id": TEST_USER_ID,
                "organization_id": TEST_ORG_ID,
                "points_amount": 100,
                "source": "parity-smoke",
            },
        )
        assert earn.status < 500, f"points/earn 5xx: {earn.text[:160]}"

        # Read the balance back — still parity-level (no 5xx).
        bal = c.get(
            f"/api/v1/memberships/points/balance?user_id={TEST_USER_ID}"
            f"&organization_id={TEST_ORG_ID}"
        )
        assert bal.status < 500, f"balance read-back 5xx: {bal.text[:160]}"
    finally:
        # Self-clean: cancel is the only undo (no DELETE route). Always attempt
        # it so no parity membership is left active; the call itself must not 5xx.
        if membership_id:
            cancel = c.post(
                f"/api/v1/memberships/{membership_id}/cancel",
                json_body={"reason": "parity-smoke-cleanup", "forfeit_points": True},
            )
            assert cancel.status < 500, f"cancel 5xx: {cancel.text[:160]}"
