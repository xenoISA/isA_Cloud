"""Parity tests for the isA **user-authorization** service.

Source of truth for endpoints/payloads:
  isA_user/microservices/authorization_service/{main.py,models.py,routes_registry.py}
Suggested flows: isA_Cloud/docs/saas-deployment/SN-PARITY-AUDIT.md (user-authorization).

PARITY contract (NOT business assertions):
  We only assert ``r.status < 500`` (a 5xx is the cross-service-wiring bug we
  hunt; 400/401/403/404/422 are all acceptable parity outcomes). We never assert
  ``== 200`` or specific bodies — payload/seed/auth nuances make that brittle.

The handlers in main.py do NOT enforce a JWT dependency (the audit header marks
this service ``auth_required=False``), so the read/CRUD flows run without auth.
The grant->verify->revoke flow is self-cleaning: ``revoke`` is the POST-based
soft-delete counterpart to ``grant`` (the service exposes no DELETE verb), so we
revoke inside the test body and ALSO register a cleanup so created state never
leaks even if the test aborts mid-way.
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-authorization"
BASE = "/api/v1/authorization"

# Clearly-fake test data — safe to run against prod.
_TEST_USER = "parity-smoke-user"
_TEST_RESOURCE = "parity-smoke-tool"


def _client() -> Client:
    return Client(SERVICE)


def _lt500(r) -> None:
    assert r.status != 0, f"unreachable: {r.text[:200]}"
    assert r.status < 500, f"5xx from {SERVICE}: {r.status} {r.text[:300]}"


# ---------------------------------------------------------------------------
# 1. List / read parity — public health, info, stats + read endpoints.
# ---------------------------------------------------------------------------
def test_user_authorization_read_parity():
    c = _client()
    for path in (
        "/health",
        f"{BASE}/health",
        f"{BASE}/info",
        f"{BASE}/stats",
    ):
        _lt500(c.get(path))


def test_user_authorization_user_permissions_read():
    """Read endpoints for a (likely non-seeded) user must not 5xx."""
    c = _client()
    _lt500(c.get(f"{BASE}/user-permissions/{_TEST_USER}"))
    _lt500(c.get(f"{BASE}/user-resources/{_TEST_USER}?resource_type=mcp_tool"))


def test_user_authorization_check_access_parity():
    """Core resource-access check (ResourceAccessRequest)."""
    c = _client()
    payload = {
        "user_id": _TEST_USER,
        "resource_type": "mcp_tool",
        "resource_name": _TEST_RESOURCE,
        "required_access_level": "read_only",
    }
    _lt500(c.post(f"{BASE}/check-access", payload))


def test_user_authorization_project_check_parity():
    """Story 9 per-action project check (ProjectAccessCheckRequest)."""
    c = _client()
    payload = {
        "user_id": _TEST_USER,
        "resource_type": "project",
        "resource_id": "parity-smoke-project",
        "action": "read",
    }
    _lt500(c.post(f"{BASE}/check", payload))


# ---------------------------------------------------------------------------
# 2. Create -> verify -> delete CRUD: grant -> check-access -> revoke.
#    revoke is the POST-based delete counterpart; we also register a cleanup
#    no-op via the same revoke path so created state never leaks.
# ---------------------------------------------------------------------------
def test_user_authorization_grant_verify_revoke():
    c = _client()

    grant_payload = {
        "user_id": _TEST_USER,
        "resource_type": "mcp_tool",
        "resource_name": _TEST_RESOURCE,
        "access_level": "read_write",
        "permission_source": "admin_grant",
        "reason": "parity-smoke",
    }
    revoke_payload = {
        "user_id": _TEST_USER,
        "resource_type": "mcp_tool",
        "resource_name": _TEST_RESOURCE,
        "reason": "parity-smoke-cleanup",
    }

    grant = c.post(f"{BASE}/grant", grant_payload)
    _lt500(grant)

    try:
        # verify: re-check access for the granted resource (no 5xx).
        _lt500(
            c.post(
                f"{BASE}/check-access",
                {
                    "user_id": _TEST_USER,
                    "resource_type": "mcp_tool",
                    "resource_name": _TEST_RESOURCE,
                    "required_access_level": "read_write",
                },
            )
        )
    finally:
        # self-cleaning: revoke removes whatever the grant created (idempotent).
        _lt500(c.post(f"{BASE}/revoke", revoke_payload))


def test_user_authorization_bulk_grant_revoke():
    """Bulk grant then bulk revoke — self-cleaning, prod-safe."""
    c = _client()

    bulk_grant = {
        "operations": [
            {
                "user_id": _TEST_USER,
                "resource_type": "mcp_tool",
                "resource_name": _TEST_RESOURCE,
                "access_level": "read_only",
                "permission_source": "admin_grant",
            }
        ],
        "batch_reason": "parity-smoke",
    }
    bulk_revoke = {
        "operations": [
            {
                "user_id": _TEST_USER,
                "resource_type": "mcp_tool",
                "resource_name": _TEST_RESOURCE,
            }
        ],
        "batch_reason": "parity-smoke-cleanup",
    }

    grant = c.post(f"{BASE}/bulk-grant", bulk_grant)
    _lt500(grant)
    try:
        pass
    finally:
        _lt500(c.post(f"{BASE}/bulk-revoke", bulk_revoke))
