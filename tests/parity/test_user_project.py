"""Parity tests for the isA user-project service (project_service).

Parity-level assertions only: a 5xx is the bug we hunt. Auth/validation
responses (401/403/404/422) are acceptable -> we only assert status < 500,
which proves the service is reachable and its inter-service calls resolve.

Service is auth-gated (auth_required=True), so we pass auth_headers on each
call. Real endpoints derived from:
  isA_user/microservices/project_service/main.py + models.py
CreateProjectRequest requires only `name` (max 255); `description` optional.
ProjectResponse returns an `id` field used for verify + cleanup.
"""

SERVICE = "user-project"


def test_user_project_list(http, auth_headers):
    """GET the main collection endpoint. Must not 5xx."""
    client = http(SERVICE)
    r = client.get("/api/v1/projects?limit=10&offset=0", headers=auth_headers)
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"5xx on list projects: {r.status} {r.text}"


def test_user_project_create_verify_delete(http, auth_headers, cleanup):
    """POST a minimal valid project -> verify by id -> auto-cleanup (DELETE)."""
    client = http(SERVICE)

    payload = {
        "name": "parity-smoke",
        "description": "parity test auto-cleanup",
    }
    r = client.post("/api/v1/projects", json_body=payload, headers=auth_headers)
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"5xx on create project: {r.status} {r.text}"

    if r.ok:
        body = r.json() or {}
        project_id = body.get("id")
        if project_id:
            # Register cleanup IMMEDIATELY so test data never leaks.
            cleanup(client, f"/api/v1/projects/{project_id}")

            g = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
            assert g.status != 0, "service unreachable"
            assert g.status < 500, f"5xx on get project: {g.status} {g.text}"
