"""Parity smoke tests for the user-vault service (isA_user vault_service).

Parity goal: confirm the secret/credential vault backend is reachable in the
target environment and that its inter-service-shaped routes don't 5xx. We assert
ONLY ``status < 500`` (a 5xx is the bug we hunt) — auth/validation nuances
(401/403/422/404) are acceptable parity outcomes.

The service is AUTH-GATED (auth_required=True per SN-PARITY-AUDIT.md and
routes_registry.py): the caller identity comes from a JWT, so the authed flows
pass ``headers=auth_headers`` (which auto-skips when auth is unavailable).
Endpoints/payloads derive from the real route handlers in
``vault_service/main.py`` + request models in ``models.py``:

  - GET    /api/v1/vault/health                     public health check
  - GET    /info                                    public service info
  - GET    /api/v1/vault/secrets                    list (auth) — VaultListResponse
  - POST   /api/v1/vault/secrets                    create (auth) — VaultCreateRequest -> 201
  - GET    /api/v1/vault/secrets/{vault_id}         read decrypted (auth)
  - DELETE /api/v1/vault/secrets/{vault_id}         delete (auth)
  - GET    /api/v1/vault/shared                     list shared secrets (auth)
  - GET    /api/v1/vault/audit-logs                 audit logs (auth)
  - GET    /api/v1/vault/stats                      vault statistics (auth)

VaultCreateRequest required fields: ``secret_type``, ``name``, ``secret_value``.
"""

from __future__ import annotations


SERVICE = "user-vault"


def _minimal_secret_body() -> dict:
    """Smallest VALID create payload per VaultCreateRequest.

    Required fields: secret_type, name, secret_value. Uses a clearly-fake test
    value so any row created during the run is obviously synthetic.
    """
    return {
        "secret_type": "api_key",
        "name": "parity-smoke",
        "secret_value": "sk_parity_smoke_do_not_use",
        "provider": "custom",
        "description": "parity smoke test secret",
        "metadata": {"environment": "parity-test"},
        "tags": ["parity-smoke"],
    }


def test_user_vault_health(http):
    """Public health route is reachable and does not 5xx."""
    client = http(SERVICE)
    r = client.get("/api/v1/vault/health")
    assert r.status != 0, f"{SERVICE} unreachable: {r.text}"
    assert r.status < 500, f"health 5xx: {r.status} {r.text}"


def test_user_vault_info(http):
    """Public service-info route does not 5xx."""
    client = http(SERVICE)
    r = client.get("/info")
    assert r.status != 0, f"{SERVICE} unreachable: {r.text}"
    assert r.status < 500, f"info 5xx: {r.status} {r.text}"


def test_user_vault_list(http, auth_headers):
    """GET the main collection endpoint (auth) — must not 5xx."""
    client = http(SERVICE)
    r = client.get("/api/v1/vault/secrets?page=1&page_size=10", headers=auth_headers)
    assert r.status != 0, f"{SERVICE} unreachable: {r.text}"
    assert r.status < 500, f"list 5xx: {r.status} {r.text}"


def test_user_vault_crud(http, auth_headers, cleanup):
    """Create -> verify (read by id) -> delete, self-cleaning and prod-safe.

    Asserts only ``status < 500`` at every hop. If create succeeds and returns
    a vault_id, cleanup is registered IMMEDIATELY so no test data is left behind.
    """
    client = http(SERVICE)

    create = client.post(
        "/api/v1/vault/secrets",
        json_body=_minimal_secret_body(),
        headers=auth_headers,
    )
    assert create.status != 0, f"{SERVICE} unreachable: {create.text}"
    assert create.status < 500, f"create 5xx: {create.status} {create.text}"

    if not create.ok:
        # Create rejected (e.g. validation/auth in this env) — no resource made,
        # nothing to clean up. The < 500 assertion above is the parity signal.
        return

    body = create.json() or {}
    vault_id = body.get("vault_id")
    if not vault_id:
        return

    # Register teardown BEFORE any further calls so an exception can't leak the row.
    cleanup(client, f"/api/v1/vault/secrets/{vault_id}")

    read = client.get(f"/api/v1/vault/secrets/{vault_id}", headers=auth_headers)
    assert read.status < 500, f"read-by-id 5xx: {read.status} {read.text}"

    delete = client.delete(f"/api/v1/vault/secrets/{vault_id}", headers=auth_headers)
    assert delete.status < 500, f"delete 5xx: {delete.status} {delete.text}"


def test_user_vault_shared(http, auth_headers):
    """Listing shared secrets (auth) must not 5xx."""
    client = http(SERVICE)
    r = client.get("/api/v1/vault/shared", headers=auth_headers)
    assert r.status != 0, f"{SERVICE} unreachable: {r.text}"
    assert r.status < 500, f"shared 5xx: {r.status} {r.text}"


def test_user_vault_audit_and_stats(http, auth_headers):
    """Audit-log and stats read endpoints (auth) must not 5xx."""
    client = http(SERVICE)

    logs = client.get("/api/v1/vault/audit-logs", headers=auth_headers)
    assert logs.status != 0, f"{SERVICE} unreachable: {logs.text}"
    assert logs.status < 500, f"audit-logs 5xx: {logs.status} {logs.text}"

    stats = client.get("/api/v1/vault/stats", headers=auth_headers)
    assert stats.status < 500, f"stats 5xx: {stats.status} {stats.text}"
