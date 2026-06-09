"""Parity smoke tests for the user-storage service (isA_user storage_service).

Parity goal: confirm the MinIO-backed file-storage backend is reachable in the
target environment and that its routes resolve inter-service dependencies without
5xx-ing. We assert ONLY ``status < 500`` (a 5xx is the bug we hunt) — auth /
validation nuances (401/403/404/422) are acceptable parity outcomes.

The service is AUTH-GATED (auth_required=True per SN-PARITY-AUDIT.md): every core
file route depends on ``get_authenticated_user_id`` (Bearer JWT / API key /
internal-service header). So the authed flows pass ``auth_headers``; using that
fixture auto-skips when auth is unavailable. The caller also passes the target
``user_id`` as a query/form parameter alongside the JWT.

Endpoints/payloads derive from the real route handlers in
``storage_service/main.py`` (port 8209):

  - GET    /api/v1/storage/health                                   public health
  - GET    /api/v1/storage/files?user_id=                           list (authed)
  - GET    /api/v1/storage/files/stats?user_id=                     storage stats
  - GET    /api/v1/storage/files/quota?user_id=                     quota info
  - GET    /api/v1/storage/files/{file_id}?user_id=                 read one
  - GET    /api/v1/storage/files/{file_id}/download?user_id=        download URL (authed)
  - DELETE /api/v1/storage/files/{file_id}?user_id=&permanent=      delete (authed)
  - POST   /api/v1/storage/files/upload                             create (multipart)
  - POST   /api/v1/storage/files/{file_id}/share                    share link (multipart)

NOTE on create: the upload + share endpoints are ``multipart/form-data`` (they use
FastAPI ``File(...)`` / ``Form(...)`` parameters), which the JSON-only parity
harness Client cannot construct. There is therefore no JSON-CRUD create path to
exercise here; this file covers the list/read/stats/quota flows plus a
delete-of-nonexistent reachability probe, which is the achievable parity signal
for this service.
"""

from __future__ import annotations


SERVICE = "user-storage"

# A clearly-fake parity user id — keeps any state obviously synthetic.
PARITY_USER = "parity-smoke-user"


def test_user_storage_health(http):
    """Service is reachable and the public health route does not 5xx."""
    client = http(SERVICE)
    r = client.get("/api/v1/storage/health")
    assert r.status != 0, f"{SERVICE} unreachable: {r.text}"
    assert r.status < 500, f"health 5xx: {r.status} {r.text}"


def test_user_storage_list(http, auth_headers):
    """GET the main collection endpoint (list files) — must not 5xx."""
    client = http(SERVICE)
    r = client.get(f"/api/v1/storage/files?user_id={PARITY_USER}", headers=auth_headers)
    assert r.status != 0, f"{SERVICE} unreachable: {r.text}"
    assert r.status < 500, f"list 5xx: {r.status} {r.text}"


def test_user_storage_stats(http, auth_headers):
    """GET storage stats — aggregates over the backend, must not 5xx."""
    client = http(SERVICE)
    r = client.get(
        f"/api/v1/storage/files/stats?user_id={PARITY_USER}", headers=auth_headers
    )
    assert r.status != 0, f"{SERVICE} unreachable: {r.text}"
    assert r.status < 500, f"stats 5xx: {r.status} {r.text}"


def test_user_storage_quota(http, auth_headers):
    """GET quota info — exercises the stats->quota inter-call, must not 5xx."""
    client = http(SERVICE)
    r = client.get(
        f"/api/v1/storage/files/quota?user_id={PARITY_USER}", headers=auth_headers
    )
    assert r.status != 0, f"{SERVICE} unreachable: {r.text}"
    assert r.status < 500, f"quota 5xx: {r.status} {r.text}"


def test_user_storage_get_nonexistent_file(http, auth_headers):
    """Read a clearly-nonexistent file by id — expect a clean 404/4xx, not 5xx.

    No resource is created (upload is multipart-only and unavailable via the JSON
    harness), so this is read-only and prod-safe with nothing to clean up.
    """
    client = http(SERVICE)
    r = client.get(
        f"/api/v1/storage/files/parity-smoke-missing?user_id={PARITY_USER}",
        headers=auth_headers,
    )
    assert r.status != 0, f"{SERVICE} unreachable: {r.text}"
    assert r.status < 500, f"get-by-id 5xx: {r.status} {r.text}"


def test_user_storage_delete_nonexistent_file(http, auth_headers):
    """DELETE a nonexistent file — the delete path must resolve without 5xx.

    Probes the delete handler (and its backend/MinIO interaction) on a fake id;
    it deletes nothing real, so it is inherently self-cleaning and prod-safe.
    """
    client = http(SERVICE)
    r = client.delete(
        f"/api/v1/storage/files/parity-smoke-missing"
        f"?user_id={PARITY_USER}&permanent=true",
        headers=auth_headers,
    )
    assert r.status != 0, f"{SERVICE} unreachable: {r.text}"
    assert r.status < 500, f"delete 5xx: {r.status} {r.text}"
