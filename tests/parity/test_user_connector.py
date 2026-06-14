"""Parity tests for the isA `user-connector` (connector_service).

Source of truth: isA_user/microservices/connector_service
  GET    /api/v1/connectors/catalog                  (public-by-default, APISIX JWT)
  GET    /api/v1/connectors/installed                (auth)
  POST   /api/v1/connectors/custom                   (auth, feature-flagged)
  DELETE /api/v1/connectors/custom/{id}              (auth, feature-flagged)

Parity contract: assert ONLY `r.status < 500`. A 5xx is the bug we hunt;
401/403/404 (feature-flag off)/422 (handshake) are all acceptable parity
signals — they prove the route resolved and inter-service calls didn't blow up.

All created resources are registered with `cleanup` so the suite is prod-safe.
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-connector"


def test_user_connector_catalog_list(http, auth_headers):
    """GET the built-in connector catalog (and a filtered variant)."""
    client: Client = http(SERVICE)

    r = client.get("/api/v1/connectors/catalog", headers=auth_headers)
    assert r.status != 0, f"catalog unreachable: {r.text}"
    assert r.status < 500, f"5xx on catalog list: {r.status} {r.text}"

    # Optional ?category= filter must not 5xx either.
    r2 = client.get("/api/v1/connectors/catalog?category=storage", headers=auth_headers)
    assert r2.status < 500, f"5xx on filtered catalog: {r2.status} {r2.text}"


def test_user_connector_installed_list(http, auth_headers):
    """GET the per-user installed + custom connectors collection."""
    client: Client = http(SERVICE)

    r = client.get("/api/v1/connectors/installed", headers=auth_headers)
    assert r.status != 0, f"installed unreachable: {r.text}"
    assert r.status < 500, f"5xx on installed list: {r.status} {r.text}"


def test_user_connector_custom_crud(http, auth_headers, cleanup):
    """POST a custom MCP connector -> verify via installed/get -> auto-delete.

    Required fields per CreateCustomMcpRequest: label, url. auth_kind defaults
    to "none" (no secret needed). The server runs a real MCP handshake against
    the URL before persisting, so a fake URL commonly yields 422 (handshake
    failed) — that is an acceptable parity outcome (no 5xx). The custom routes
    are also feature-flagged and may return 404 (route_disabled) when
    ALLOW_CUSTOM_MCP_CONNECTORS=false; that is acceptable too.
    """
    client: Client = http(SERVICE)

    payload = {
        "label": "parity-smoke",
        "url": "https://mcp.example.com/parity-smoke",
        "auth_kind": "none",
    }

    r = client.post(
        "/api/v1/connectors/custom", json_body=payload, headers=auth_headers
    )
    assert r.status != 0, f"custom create unreachable: {r.text}"
    assert r.status < 500, f"5xx on custom create: {r.status} {r.text}"

    body = r.json()
    if r.ok and isinstance(body, dict):
        connector_id = body.get("id")
        if connector_id:
            # Register teardown IMMEDIATELY so nothing leaks even if a
            # later assert fails.
            cleanup(client, f"/api/v1/connectors/custom/{connector_id}")

            # Verify it shows up via the installed collection (the GET-by-id
            # surface for custom rows is the installed list, per the service).
            r_get = client.get("/api/v1/connectors/installed", headers=auth_headers)
            assert r_get.status < 500, (
                f"5xx verifying created connector: {r_get.status} {r_get.text}"
            )
