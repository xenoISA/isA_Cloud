"""Parity tests for the isA `user-developer` (developer_service).

Source of truth: isA_user/microservices/developer_service
  GET  /health                             (public — basic health)
  GET  /api/v1/developer/health            (public — dependency health)
  GET  /api/v1/developer/overview          (auth) ?organization_id=&project_id=&period_days=
  POST /api/v1/developer/first-call        (auth — FirstCallRequest)

This is an aggregation / read-and-verify service: it has NO persistent CRUD
(no create/delete of a resource), so there is nothing to register with
`cleanup`. The overview endpoint requires an `organization_id` query param
(min_length=1) and the first-call endpoint requires a FirstCallRequest body
(organization_id, project_id required). We send clearly-fake test context.

Parity contract: assert ONLY `r.status < 500`. A 5xx is the bug we hunt;
401/403/404/422 are acceptable parity signals — they prove the route resolved
and downstream inter-service calls (org/project/auth/billing/model) did not
blow up. We do NOT assert == 200 or specific bodies (auth/dependency nuances
make that brittle).
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-developer"

# Clearly-fake parity context — never collides with real org/project data.
FAKE_ORG = "parity-smoke-org"
FAKE_PROJECT = "parity-smoke-proj"


def test_user_developer_health(http):
    """GET the public health endpoints — reachability + no 5xx."""
    client: Client = http(SERVICE)

    r = client.get("/health")
    assert r.status != 0, f"/health unreachable: {r.text}"
    assert r.status < 500, f"5xx on /health: {r.status} {r.text}"

    r2 = client.get("/api/v1/developer/health")
    assert r2.status != 0, f"developer health unreachable: {r2.text}"
    assert r2.status < 500, f"5xx on developer health: {r2.status} {r2.text}"


def test_user_developer_overview(http, auth_headers):
    """GET the developer overview (the main read surface).

    Requires `organization_id` (query, min_length=1); project_id and period_days
    are optional. A missing/invalid org or project resolves to 4xx (often with
    partial-data warnings), never a 5xx — that is the parity signal.
    """
    client: Client = http(SERVICE)

    # With org only.
    r = client.get(
        f"/api/v1/developer/overview?organization_id={FAKE_ORG}",
        headers=auth_headers,
    )
    assert r.status != 0, f"overview unreachable: {r.text}"
    assert r.status < 500, f"5xx on overview: {r.status} {r.text}"

    # With org + project + period — exercises the full aggregation path.
    r2 = client.get(
        f"/api/v1/developer/overview?organization_id={FAKE_ORG}"
        f"&project_id={FAKE_PROJECT}&period_days=7",
        headers=auth_headers,
    )
    assert r2.status < 500, f"5xx on full overview: {r2.status} {r2.text}"


def test_user_developer_overview_missing_org(http, auth_headers):
    """GET overview without the required org param — must 4xx (422), not 5xx."""
    client: Client = http(SERVICE)

    r = client.get("/api/v1/developer/overview", headers=auth_headers)
    assert r.status != 0, f"overview (no org) unreachable: {r.text}"
    assert r.status < 500, f"5xx on overview without org: {r.status} {r.text}"


def test_user_developer_first_call(http, auth_headers):
    """POST first-call verification with a minimal valid FirstCallRequest.

    Required fields: organization_id, project_id (both min_length=1). `model`,
    `prompt` have server defaults. With a fake org/project and no real
    credential, the service returns a non-2xx failure (e.g. 400/404/422 with a
    remediation object) rather than a 5xx — that is an acceptable parity
    outcome. First-call does not persist a resource, so no cleanup is needed.
    """
    client: Client = http(SERVICE)

    payload = {
        "organization_id": FAKE_ORG,
        "project_id": FAKE_PROJECT,
        "model": "gpt-4.1-nano",
        "prompt": "Reply with a short JSON object confirming readiness.",
    }

    r = client.post(
        "/api/v1/developer/first-call",
        json_body=payload,
        headers=auth_headers,
    )
    assert r.status != 0, f"first-call unreachable: {r.text}"
    assert r.status < 500, f"5xx on first-call: {r.status} {r.text}"
