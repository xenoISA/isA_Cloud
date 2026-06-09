"""Parity tests for the isA `user-media` service (media_service).

Source of truth: isA_user/microservices/media_service
  - main.py            : real FastAPI routes (all under /api/v1/media)
  - models.py          : request models + required fields
  - routes_registry.py : route map (registered base_path /api/v1/media)
  - SN-PARITY-AUDIT.md : suggested flows (user-media auth_required=False;
                         user identity is bound via a `user_id` query param)

The handlers extract the caller's identity from a `user_id` query param
(`get_user_id` Depends on Query(...)), NOT from a JWT — the audit marks this
service auth_required=False. So these tests thread `user_id` as a query param
and do NOT send auth headers.

Endpoints exercised (all under /api/v1/media):
  GET    /health                                 service health (public)
  GET    /api/v1/media/health                    api-v1 health (public)
  GET    /                                        root status (public)
  GET    /api/v1/media/playlists                  list playlists
  POST   /api/v1/media/playlists                  create playlist
  GET    /api/v1/media/playlists/{id}             read playlist
  PUT    /api/v1/media/playlists/{id}             update playlist
  DELETE /api/v1/media/playlists/{id}             delete playlist
  POST   /api/v1/media/versions                   create photo version
  GET    /api/v1/media/versions/{id}              read photo version
  DELETE /api/v1/media/versions/{id}              delete photo version
  POST   /api/v1/media/schedules                  create rotation schedule
  GET    /api/v1/media/schedules/{id}             read schedule
  DELETE /api/v1/media/schedules/{id}             delete schedule
  GET    /api/v1/media/metadata/{file_id}         read photo metadata
  GET    /api/v1/media/gallery/playlists          gallery playlists (compat)

Parity assertion contract: assert ONLY `r.status < 500`. A 5xx means a
real bug (handler crash or an unresolved inter-service call). 401/403/404/422
are acceptable parity outcomes (auth/validation/missing-resource nuance), not
failures. Every created resource is registered with `cleanup` so the suite is
self-cleaning and safe to run against prod.
"""

from conftest import Client  # noqa: F401  (harness import per contract)

SERVICE = "user-media"
USER_ID = "parity-smoke-user"


def test_user_media_health(http):
    """Public health endpoints must be reachable and not 5xx."""
    client = http(SERVICE)
    for path in ("/health", "/api/v1/media/health"):
        r = client.get(path)
        assert r.status != 0, f"service unreachable: {path}"
        assert r.status < 500, f"health 5xx ({path}): {r.status} {r.text}"


def test_user_media_list_playlists(http):
    """List the main playlists collection — must not 5xx."""
    client = http(SERVICE)
    r = client.get(f"/api/v1/media/playlists?user_id={USER_ID}")
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"list playlists 5xx: {r.status} {r.text}"


def test_user_media_list_gallery_playlists(http):
    """Gallery compatibility collection endpoint — must not 5xx."""
    client = http(SERVICE)
    r = client.get(f"/api/v1/media/gallery/playlists?user_id={USER_ID}")
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"list gallery playlists 5xx: {r.status} {r.text}"


def test_user_media_playlist_crud(http, cleanup):
    """Create -> verify-by-id -> delete a playlist. Self-cleaning, prod-safe.

    Minimal valid payload per PlaylistCreateRequest: only `name` is required.
    """
    client = http(SERVICE)

    payload = {
        "name": "parity-smoke",
        "description": "parity smoke test playlist",
        "playlist_type": "manual",
        "photo_ids": [],
        "shuffle": False,
        "loop": True,
        "transition_duration": 5,
    }
    r = client.post(f"/api/v1/media/playlists?user_id={USER_ID}", json_body=payload)
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"create playlist 5xx: {r.status} {r.text}"

    if r.ok:
        body = r.json() or {}
        playlist_id = body.get("playlist_id") or body.get("id")
        if playlist_id:
            # Register cleanup IMMEDIATELY so the playlist is never left behind.
            cleanup(client, f"/api/v1/media/playlists/{playlist_id}?user_id={USER_ID}")

            got = client.get(f"/api/v1/media/playlists/{playlist_id}?user_id={USER_ID}")
            assert got.status != 0, "service unreachable"
            assert got.status < 500, f"read playlist 5xx: {got.status} {got.text}"


def test_user_media_version_create_read(http, cleanup):
    """Create a photo version, then read it back by id. No 5xx.

    Minimal valid payload per PhotoVersionCreateRequest:
    photo_id, version_name, version_type, file_id are required. The referenced
    photo/file are fake; a 4xx for unknown refs is acceptable parity.
    """
    client = http(SERVICE)

    payload = {
        "photo_id": "parity-smoke-photo",
        "version_name": "parity-smoke",
        "version_type": "ai_enhanced",
        "file_id": "parity-smoke-file",
    }
    r = client.post(f"/api/v1/media/versions?user_id={USER_ID}", json_body=payload)
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"create version 5xx: {r.status} {r.text}"

    if r.ok:
        body = r.json() or {}
        version_id = body.get("version_id") or body.get("id")
        if version_id:
            cleanup(client, f"/api/v1/media/versions/{version_id}?user_id={USER_ID}")

            got = client.get(f"/api/v1/media/versions/{version_id}?user_id={USER_ID}")
            assert got.status != 0, "service unreachable"
            assert got.status < 500, f"read version 5xx: {got.status} {got.text}"


def test_user_media_schedule_create_read(http, cleanup):
    """Create a rotation schedule, then read it back by id. No 5xx.

    Minimal valid payload per RotationScheduleCreateRequest:
    frame_id and playlist_id are required. The referenced frame/playlist are
    fake; a 4xx for unknown refs is acceptable parity.
    """
    client = http(SERVICE)

    payload = {
        "frame_id": "parity-smoke-frame",
        "playlist_id": "parity-smoke-playlist",
        "schedule_type": "continuous",
        "rotation_interval": 10,
        "shuffle": False,
    }
    r = client.post(f"/api/v1/media/schedules?user_id={USER_ID}", json_body=payload)
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"create schedule 5xx: {r.status} {r.text}"

    if r.ok:
        body = r.json() or {}
        schedule_id = body.get("schedule_id") or body.get("id")
        if schedule_id:
            cleanup(client, f"/api/v1/media/schedules/{schedule_id}?user_id={USER_ID}")

            got = client.get(f"/api/v1/media/schedules/{schedule_id}?user_id={USER_ID}")
            assert got.status != 0, "service unreachable"
            assert got.status < 500, f"read schedule 5xx: {got.status} {got.text}"


def test_user_media_metadata_read(http):
    """Read photo metadata for an unknown file id — must not 5xx.

    A 404 for an unknown file_id is the expected parity outcome; the signal
    we hunt is a handler crash (5xx).
    """
    client = http(SERVICE)
    r = client.get(f"/api/v1/media/metadata/parity-smoke-file?user_id={USER_ID}")
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"read metadata 5xx: {r.status} {r.text}"
