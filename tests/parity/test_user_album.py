"""Parity tests for the isA `user-album` service (album_service).

Source of truth: isA_user/microservices/album_service
  - routes_registry.py : real paths + auth flags
  - models.py          : AlbumCreateRequest required fields (name)
  - SN-PARITY-AUDIT.md : suggested flows (user_id passed as query param)

Endpoints (all under /api/v1/albums, auth_required=True except health):
  GET    /api/v1/albums/health
  GET    /api/v1/albums                          list albums
  POST   /api/v1/albums                          create album
  GET    /api/v1/albums/{album_id}               read album
  PUT    /api/v1/albums/{album_id}               update album
  DELETE /api/v1/albums/{album_id}               delete album
  GET    /api/v1/albums/{album_id}/photos        list album photos
  POST   /api/v1/albums/{album_id}/photos        add photos
  DELETE /api/v1/albums/{album_id}/photos        remove photos
  POST   /api/v1/albums/{album_id}/sync          sync to frame
  GET    /api/v1/albums/{album_id}/sync/{frame_id}  sync status

Parity assertion contract: assert ONLY `r.status < 500`. A 5xx means a
real bug (handler crash or unresolved inter-service call). 401/403/422
are acceptable parity outcomes (auth/validation nuance), not failures.

The service binds user identity from a `user_id` query param (per the
audit doc), so we thread it through every call alongside auth headers.
"""

SERVICE = "user-album"
USER_ID = "parity-smoke-user"


def test_user_album_health(http):
    """Public health endpoint must be reachable and not 5xx."""
    client = http(SERVICE)
    r = client.get("/api/v1/albums/health")
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"health 5xx: {r.status} {r.text}"


def test_user_album_list(http, auth_headers):
    """List the main albums collection — must not 5xx."""
    client = http(SERVICE)
    r = client.get(f"/api/v1/albums?user_id={USER_ID}", headers=auth_headers)
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"list 5xx: {r.status} {r.text}"


def test_user_album_crud(http, auth_headers, cleanup):
    """Create -> verify-by-id -> delete an album. Self-cleaning, prod-safe.

    Minimal valid payload per AlbumCreateRequest: only `name` is required.
    """
    client = http(SERVICE)

    payload = {
        "name": "parity-smoke",
        "description": "parity smoke test album",
        "auto_sync": False,
        "is_family_shared": False,
    }
    r = client.post(
        f"/api/v1/albums?user_id={USER_ID}", json_body=payload, headers=auth_headers
    )
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"create 5xx: {r.status} {r.text}"

    if r.ok:
        body = r.json() or {}
        album_id = body.get("album_id") or body.get("id")
        if album_id:
            # Register cleanup IMMEDIATELY so the album is never left behind.
            cleanup(client, f"/api/v1/albums/{album_id}?user_id={USER_ID}")

            got = client.get(
                f"/api/v1/albums/{album_id}?user_id={USER_ID}", headers=auth_headers
            )
            assert got.status != 0, "service unreachable"
            assert got.status < 500, f"read 5xx: {got.status} {got.text}"


def test_user_album_photos(http, auth_headers, cleanup):
    """Create an album, then exercise the photos collection endpoint.

    Photo add references external file IDs (storage_service); we only
    assert no 5xx — a 4xx for unknown photo ids is acceptable parity.
    """
    client = http(SERVICE)

    r = client.post(
        f"/api/v1/albums?user_id={USER_ID}",
        json_body={"name": "parity-smoke", "auto_sync": False},
        headers=auth_headers,
    )
    assert r.status < 500, f"create 5xx: {r.status} {r.text}"

    if not r.ok:
        return
    album_id = (r.json() or {}).get("album_id")
    if not album_id:
        return
    cleanup(client, f"/api/v1/albums/{album_id}?user_id={USER_ID}")

    lst = client.get(
        f"/api/v1/albums/{album_id}/photos?user_id={USER_ID}", headers=auth_headers
    )
    assert lst.status < 500, f"list photos 5xx: {lst.status} {lst.text}"

    add = client.post(
        f"/api/v1/albums/{album_id}/photos?user_id={USER_ID}",
        json_body={"photo_ids": ["parity-smoke-photo-1"]},
        headers=auth_headers,
    )
    assert add.status < 500, f"add photos 5xx: {add.status} {add.text}"


def test_user_album_sync(http, auth_headers, cleanup):
    """Create an album, request a frame sync, query sync status. No 5xx."""
    client = http(SERVICE)

    r = client.post(
        f"/api/v1/albums?user_id={USER_ID}",
        json_body={"name": "parity-smoke", "auto_sync": False},
        headers=auth_headers,
    )
    assert r.status < 500, f"create 5xx: {r.status} {r.text}"

    if not r.ok:
        return
    album_id = (r.json() or {}).get("album_id")
    if not album_id:
        return
    cleanup(client, f"/api/v1/albums/{album_id}?user_id={USER_ID}")

    frame_id = "parity-smoke-frame"
    sync = client.post(
        f"/api/v1/albums/{album_id}/sync?user_id={USER_ID}",
        json_body={"frame_id": frame_id},
        headers=auth_headers,
    )
    assert sync.status < 500, f"sync 5xx: {sync.status} {sync.text}"

    status = client.get(
        f"/api/v1/albums/{album_id}/sync/{frame_id}?user_id={USER_ID}",
        headers=auth_headers,
    )
    assert status.status < 500, f"sync status 5xx: {status.status} {status.text}"
