"""Parity smoke tests for the isA **isa-model** service.

Derived from the real route handlers in
`isA_Model/isa_model/serving/api/routes/` (mounted in
`isa_model/serving/api/fastapi_server.py`) and the per-service spec in
`docs/saas-deployment/SN-PARITY-AUDIT.md` (### isa-model, auth_required=True).

Reality check vs the audit's suggested flow: the audit proposes a model CRUD at
`POST /api/v1/models`, but no such create endpoint exists — `/api/v1/models`
(inference router) is a GET-only listing. The real admin CRUD with a matching
DELETE is the provider-config API at `/api/v1/config/providers`
(`provider_config_routes.py`), whose create model is `ProviderConfigCreateRequest`
(required field: `provider_name`; optional `config_data`, `is_active`). That is
what the create->verify->delete flow exercises here.

Parity contract: we only assert `r.status < 500`. A 5xx is the bug we hunt
(unresolved DB DSN, broken inter-service call, crash). 401/403/404/422 are all
acceptable parity outcomes — auth/payload nuances vary per environment. The
admin routes are gated by `require_admin_access`, so a non-admin token yields
401/403 (still < 500, still a pass).

Every created resource is registered with `cleanup` immediately after creation
so the suite is safe to run against production.
"""

from __future__ import annotations

import uuid

from conftest import Client  # noqa: F401  (re-exported harness type)

SERVICE = "isa-model"


def _ok(r):
    """Parity assertion: reachable and no server-side (5xx) failure."""
    assert r.status != 0, f"unreachable: {r.text}"
    assert r.status < 500, f"5xx from {SERVICE}: {r.status} {r.text}"


# ---------------------------------------------------------------------------
# 1. List / read flow — public listing + admin collections
# ---------------------------------------------------------------------------
def test_isa_model_list_read(http, auth_headers):
    """GET the main collection endpoints.

    `/api/v1/models` (inference) lists routed models; `/api/v1/config/providers`
    and `/api/v1/config/backups` are admin collections (auth-gated). All must
    resolve without a 5xx.
    """
    c = http(SERVICE)

    # Inference model listing (read-only).
    _ok(c.get("/api/v1/models", headers=auth_headers))

    # Provider-config admin listing.
    _ok(c.get("/api/v1/config/providers", headers=auth_headers))

    # Backup listing (admin/read-access gated).
    _ok(c.get("/api/v1/config/backups", headers=auth_headers))


# ---------------------------------------------------------------------------
# 2. Analytics read flow
# ---------------------------------------------------------------------------
def test_isa_model_analytics(http, auth_headers):
    """Analytics endpoints touch the usage DB — a 5xx flags a broken DSN/conn.

    `/api/v1/analytics/usage` takes a `period` query param (1d/7d/30d/90d).
    """
    c = http(SERVICE)
    _ok(c.get("/api/v1/analytics/usage?period=7d", headers=auth_headers))
    _ok(c.get("/api/v1/analytics/overview?period=7d", headers=auth_headers))


# ---------------------------------------------------------------------------
# 3. Provider-config CRUD flow (create -> verify -> DELETE) — self-cleaning
# ---------------------------------------------------------------------------
def test_isa_model_provider_config_crud(http, auth_headers, cleanup):
    """POST provider config -> register DELETE cleanup -> GET by name -> probe.

    Request model `ProviderConfigCreateRequest`: required `provider_name`,
    optional `config_data` (dict) and `is_active` (bool). Admin-gated via
    `require_admin_access` (non-admin -> 401/403, an acceptable parity outcome).
    If creation succeeds, the DELETE is registered immediately so teardown
    always runs and no test data is left behind.
    """
    c = http(SERVICE)
    name = f"parity-smoke-{uuid.uuid4().hex[:10]}"

    r = c.post(
        "/api/v1/config/providers",
        json_body={
            "provider_name": name,
            "config_data": {
                "api_key": "sk-parity-smoke",
                "base_url": "https://api.example.com",
            },
            "is_active": False,
        },
        headers=auth_headers,
    )
    _ok(r)

    if r.ok:
        # Register teardown DELETE immediately so it always runs.
        cleanup(c, f"/api/v1/config/providers/{name}")

        # Verify by reading the resource back.
        _ok(c.get(f"/api/v1/config/providers/{name}", headers=auth_headers))

        # Connectivity probe (POST .../test) — expected to fail the probe but
        # must not 5xx.
        _ok(
            c.post(
                f"/api/v1/config/providers/{name}/test",
                json_body={},
                headers=auth_headers,
            )
        )


# ---------------------------------------------------------------------------
# 4. Health probe (public)
# ---------------------------------------------------------------------------
def test_isa_model_health(http):
    """Service health endpoint (mounted at /health) should resolve without 5xx."""
    c = http(SERVICE)
    _ok(c.get("/health"))
