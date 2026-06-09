"""Parity smoke tests for the **isa-agent-mt** (multitenant Agent CRUD) service.

Real endpoints (from isA_Agent/src/isa_agent/api/v1/agents.py + agent_runs.py,
mounted under /api/v1 by api/router.py):

    POST   /api/v1/agents              create an agent              -> 201
    GET    /api/v1/agents              list (tenant/status filters)
    GET    /api/v1/agents/{id}         fetch one
    DELETE /api/v1/agents/{id}         soft-delete (status=archived)-> 204
    POST   /api/v1/agents/{id}/runs    create a manual run          -> 201
    GET    /api/v1/runs/{run_id}       fetch one run

The service is auth-gated (audit: auth_required=True) and multitenant — writes
are scoped to the resolved tenant (X-Tenant-Id header / default). These tests
use the bootstrapped user token via `auth_headers`.

PARITY-LEVEL ASSERTIONS ONLY: we assert `r.status < 500`. A 5xx is the bug we
hunt (crash / unresolved inter-service call). 401/403/404/422/429 are all
acceptable parity outcomes — payload, tenant, and quota nuances make exact-status
assertions brittle. Every created resource is registered for cleanup so the
suite is safe to run against prod.
"""

from __future__ import annotations

from conftest import Client

SERVICE = "isa-agent-mt"

# A clearly-fake, well-formed UUID for the required character_id FK. The FK may
# not resolve (-> 4xx) which is an acceptable parity outcome; what matters is no
# 5xx and that inter-service / DB calls resolve.
FAKE_CHARACTER_ID = "00000000-0000-0000-0000-000000000001"


def _minimal_agent_payload() -> dict:
    """Minimal VALID AgentCreate body derived from the request model.

    Required: template_name, template_version, character_id (UUID).
    bound_personas defaults to [] and binding_policy defaults to 'fixed'.
    tenant_id is server-resolved from the request, so we leave it unset.
    """
    return {
        "template_name": "parity-smoke",
        "template_version": "1.0",
        "character_id": FAKE_CHARACTER_ID,
        "bound_personas": [],
        "binding_policy": "fixed",
    }


def test_isa_agent_mt_list_agents(http, auth_headers):
    """GET the main collection endpoint — must not 5xx."""
    client: Client = http(SERVICE)
    r = client.get("/api/v1/agents", headers=auth_headers)
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"5xx on GET /api/v1/agents: {r.status} {r.text}"


def test_isa_agent_mt_list_runs(http, auth_headers):
    """GET the runs collection endpoint — must not 5xx."""
    client: Client = http(SERVICE)
    r = client.get("/api/v1/runs", headers=auth_headers)
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"5xx on GET /api/v1/runs: {r.status} {r.text}"


def test_isa_agent_mt_agent_crud(http, auth_headers, cleanup):
    """POST create -> register cleanup -> GET by id. Self-cleaning CRUD."""
    client: Client = http(SERVICE)

    r = client.post(
        "/api/v1/agents", json_body=_minimal_agent_payload(), headers=auth_headers
    )
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"5xx on POST /api/v1/agents: {r.status} {r.text}"

    if r.ok:
        body = r.json() or {}
        agent_id = body.get("agent_id") or body.get("id")
        if agent_id:
            # DELETE is a soft-delete (status=archived) — safe teardown.
            cleanup(client, f"/api/v1/agents/{agent_id}")
            g = client.get(f"/api/v1/agents/{agent_id}", headers=auth_headers)
            assert g.status != 0, "service unreachable on read-back"
            assert g.status < 500, (
                f"5xx on GET /api/v1/agents/{agent_id}: {g.status} {g.text}"
            )


def test_isa_agent_mt_agent_manual_run(http, auth_headers, cleanup):
    """Create an agent, enqueue a manual run for it, read the run back.

    Exercises the agent -> run path (POST /agents/{id}/runs -> GET /runs/{id}).
    Each step asserts only `< 500`; the created agent is registered for cleanup.
    """
    client: Client = http(SERVICE)

    r = client.post(
        "/api/v1/agents", json_body=_minimal_agent_payload(), headers=auth_headers
    )
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"5xx on POST /api/v1/agents: {r.status} {r.text}"

    if not r.ok:
        # Create not possible in this env (auth/tenant/quota/FK) — parity signal
        # from the list/create endpoints already captured. Nothing to run.
        return

    body = r.json() or {}
    agent_id = body.get("agent_id") or body.get("id")
    if not agent_id:
        return

    cleanup(client, f"/api/v1/agents/{agent_id}")

    # AgentManualRunCreate body is optional (all fields default) — minimal {}.
    run_resp = client.post(
        f"/api/v1/agents/{agent_id}/runs", json_body={}, headers=auth_headers
    )
    assert run_resp.status != 0, "service unreachable on run create"
    assert run_resp.status < 500, (
        f"5xx on POST /api/v1/agents/{agent_id}/runs: {run_resp.status} {run_resp.text}"
    )

    if run_resp.ok:
        run_body = run_resp.json() or {}
        run_id = run_body.get("run_id") or run_body.get("id")
        if run_id:
            g = client.get(f"/api/v1/runs/{run_id}", headers=auth_headers)
            assert g.status != 0, "service unreachable on run read-back"
            assert g.status < 500, (
                f"5xx on GET /api/v1/runs/{run_id}: {g.status} {g.text}"
            )
