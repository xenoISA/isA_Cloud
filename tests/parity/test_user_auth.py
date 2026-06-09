"""Parity suite for the isA service: user-auth (auth_service).

Real functional flows, parity-level assertions only. The signal we hunt is a
5xx (a service that errored, or an inter-service call that failed to resolve) —
NOT business-logic correctness. So every check asserts `r.status < 500`.
401/403/404/422 are all acceptable here.

Endpoints exercised (verified against
isA_user/microservices/auth_service/main.py):
  - GET  /health                              (public)
  - GET  /api/v1/auth/health                  (public)
  - GET  /api/v1/auth/info                     (public)
  - GET  /api/v1/auth/stats                    (public)
  - POST   /api/v1/auth/api-keys               (auth-gated create)
  - GET    /api/v1/auth/api-keys/{org_id}      (auth-gated list)
  - DELETE /api/v1/auth/api-keys/{key_id}?organization_id=...  (auth-gated revoke)

The api-key CRUD is self-cleaning (cleanup() registers the revoke DELETE the
instant a key id comes back), so it is safe to run against prod.
"""

from __future__ import annotations


SERVICE = "user-auth"
ORG_ID = "org-parity-smoke"


def test_user_auth_read_health(http):
    """Public health/read endpoints must not 5xx."""
    client = http(SERVICE)
    for path in (
        "/health",
        "/api/v1/auth/health",
        "/api/v1/auth/info",
        "/api/v1/auth/stats",
    ):
        r = client.get(path)
        assert r.status != 0, f"{path} unreachable: {r.text[:160]}"
        assert r.status < 500, f"{path} 5xx: {r.status} {r.text[:160]}"


def test_user_auth_list_api_keys(http, auth_headers):
    """Listing api-keys for an org is auth-gated; assert no 5xx."""
    client = http(SERVICE)
    r = client.get(f"/api/v1/auth/api-keys/{ORG_ID}", headers=auth_headers)
    assert r.status != 0, f"list api-keys unreachable: {r.text[:160]}"
    assert r.status < 500, f"list api-keys 5xx: {r.status} {r.text[:160]}"


def test_user_auth_api_key_crud(http, auth_headers, cleanup):
    """Create -> verify-by-id -> (auto) revoke an api-key, parity-level.

    Minimal VALID payload per ApiKeyCreateRequest: organization_id + name are
    required; permissions defaults to []. Fake test data only. If creation
    succeeds and returns a key_id, the revoke DELETE is registered for teardown
    immediately, then we read the key back via the org listing.
    """
    client = http(SERVICE)

    payload = {
        "organization_id": ORG_ID,
        "name": "parity-smoke",
        "permissions": ["read"],
    }
    r = client.post("/api/v1/auth/api-keys", json_body=payload, headers=auth_headers)
    assert r.status != 0, f"create api-key unreachable: {r.text[:160]}"
    assert r.status < 500, f"create api-key 5xx: {r.status} {r.text[:160]}"

    # If the create actually succeeded, self-clean and verify the read path.
    if r.ok:
        body = r.json() or {}
        key_id = body.get("key_id")
        if key_id:
            # Register teardown IMMEDIATELY so we never leak a key (prod-safe).
            cleanup(
                client,
                f"/api/v1/auth/api-keys/{key_id}?organization_id={ORG_ID}",
            )
            # Read it back via the org listing — still parity-level (< 500).
            r2 = client.get(f"/api/v1/auth/api-keys/{ORG_ID}", headers=auth_headers)
            assert r2.status != 0, f"read-back unreachable: {r2.text[:160]}"
            assert r2.status < 500, f"read-back 5xx: {r2.status} {r2.text[:160]}"
