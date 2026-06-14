"""Parity smoke tests for the user-artifact service (isA_user artifact_service).

Parity goal: confirm the artifact library backend is reachable in the target
environment and that its inter-service-shaped routes don't 5xx. We assert ONLY
``status < 500`` (a 5xx is the bug we hunt) — auth/validation nuances (401/403/
422/404) are acceptable parity outcomes.

The service is PUBLIC (auth_required=False per SN-PARITY-AUDIT.md): it carries
the caller identity via a ``user_id`` query/body parameter rather than a JWT, so
no ``auth_headers`` are needed. Endpoints/payloads derive from the real route
handlers in ``artifact_service/main.py`` + request models in ``models.py``:

  - POST   /api/v1/artifacts                      body {"user_id", "artifact": {title, content_type, version:{content}}}
  - GET    /api/v1/artifacts?user_id=             list
  - GET    /api/v1/artifacts/{id}?user_id=        read one
  - PATCH  /api/v1/artifacts/{id}                 body {"user_id", "update": {...}}
  - DELETE /api/v1/artifacts/{id}?user_id=        soft delete
  - POST   /api/v1/artifacts/{id}/versions        body {"user_id", "version": {content}}
"""

from __future__ import annotations


SERVICE = "user-artifact"

# A clearly-fake parity user id — keeps any rows created during the run obviously
# synthetic and easy to spot if cleanup is ever interrupted.
PARITY_USER = "parity-smoke-user"


def _minimal_artifact_body() -> dict:
    """Smallest VALID create payload per ArtifactCreateRequest / CreateArtifactBody.

    Required fields: title, content_type, and a first version with content.
    """
    return {
        "user_id": PARITY_USER,
        "artifact": {
            "title": "parity-smoke",
            "content_type": "code",
            "visibility": "private",
            "version": {
                "content": "console.log('parity-smoke');",
                "language": "javascript",
                "filename": "parity.js",
            },
        },
    }


def test_user_artifact_health(http):
    """Service is reachable and the health route does not 5xx."""
    client = http(SERVICE)
    r = client.get("/api/v1/artifacts/health")
    assert r.status != 0, f"{SERVICE} unreachable: {r.text}"
    assert r.status < 500, f"health 5xx: {r.status} {r.text}"


def test_user_artifact_list(http):
    """GET the main collection endpoint — must not 5xx."""
    client = http(SERVICE)
    r = client.get(f"/api/v1/artifacts?user_id={PARITY_USER}")
    assert r.status != 0, f"{SERVICE} unreachable: {r.text}"
    assert r.status < 500, f"list 5xx: {r.status} {r.text}"


def test_user_artifact_crud(http, cleanup):
    """Create -> verify (read by id) -> delete, self-cleaning and prod-safe.

    Asserts only ``status < 500`` at every hop. If create succeeds and returns
    an id, cleanup is registered IMMEDIATELY so no test data is left behind.
    """
    client = http(SERVICE)

    create = client.post("/api/v1/artifacts", json_body=_minimal_artifact_body())
    assert create.status != 0, f"{SERVICE} unreachable: {create.text}"
    assert create.status < 500, f"create 5xx: {create.status} {create.text}"

    if not create.ok:
        # Create rejected (e.g. validation/auth in this env) — no resource made,
        # nothing to clean up. The < 500 assertion above is the parity signal.
        return

    body = create.json() or {}
    artifact_id = body.get("id")
    if not artifact_id:
        return

    # Register teardown BEFORE any further calls so an exception can't leak the row.
    cleanup(client, f"/api/v1/artifacts/{artifact_id}?user_id={PARITY_USER}")

    read = client.get(f"/api/v1/artifacts/{artifact_id}?user_id={PARITY_USER}")
    assert read.status < 500, f"read-by-id 5xx: {read.status} {read.text}"

    delete = client.delete(f"/api/v1/artifacts/{artifact_id}?user_id={PARITY_USER}")
    assert delete.status < 500, f"delete 5xx: {delete.status} {delete.text}"


def test_user_artifact_add_version(http, cleanup):
    """Create an artifact then add a second version — versioning must not 5xx."""
    client = http(SERVICE)

    create = client.post("/api/v1/artifacts", json_body=_minimal_artifact_body())
    assert create.status != 0, f"{SERVICE} unreachable: {create.text}"
    assert create.status < 500, f"create 5xx: {create.status} {create.text}"

    if not create.ok:
        return

    artifact_id = (create.json() or {}).get("id")
    if not artifact_id:
        return

    cleanup(client, f"/api/v1/artifacts/{artifact_id}?user_id={PARITY_USER}")

    add = client.post(
        f"/api/v1/artifacts/{artifact_id}/versions",
        json_body={
            "user_id": PARITY_USER,
            "version": {
                "content": "console.log('parity-smoke v2');",
                "language": "javascript",
                "filename": "parity-v2.js",
            },
        },
    )
    assert add.status < 500, f"add-version 5xx: {add.status} {add.text}"
