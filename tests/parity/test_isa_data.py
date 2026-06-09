"""Parity smoke tests for the isa-data service.

Env-agnostic (local / SN-IDC / GCP-GKE). Asserts only that endpoints do NOT
return a 5xx (the parity bug we hunt for) and that inter-service calls resolve.
Payload / auth nuances make exact-status assertions brittle, so we assert
`r.status < 500` (a non-5xx, non-zero response is a passing parity signal).

isa-data is NOT JWT-gated: it scopes writes via an `X-User-Id` header rather
than a Bearer token, so these tests do not use `auth_headers`. Created resources
are registered with `cleanup` so the suite is safe to run against prod.

Source of truth for paths/payloads:
  - src/main.py router mounts
  - src/api/v1/{metadata,catalog,vector_stores}.py route handlers
  - src/services/vector_store/schemas.py (VectorStoreCreateRequest)
"""

from __future__ import annotations

import uuid

from conftest import Client

SERVICE = "isa-data"

# isa-data scopes vector-store ownership by this header (no JWT). A stable
# fake id keeps the suite self-cleaning and prod-safe.
USER_HEADER = {"X-User-Id": "parity-smoke-user"}


def test_isa_data_health_and_root():
    """Service is reachable and the health/root endpoints don't 5xx."""
    c = Client(SERVICE)
    for path in ("/health", "/"):
        r = c.get(path)
        assert r.status != 0, f"{path} unreachable"
        assert r.status < 500, f"{path} -> {r.status}: {r.text[:200]}"


def test_isa_data_metadata_catalog_flow():
    """Metadata catalog endpoints (DB + Qdrant dependency) resolve without 5xx."""
    c = Client(SERVICE)

    # Semantic search — exercises Qdrant/DB inter-service path.
    r = c.post(
        "/api/v1/data/metadata/search", json_body={"query": "parity-smoke table"}
    )
    assert r.status != 0, "metadata/search unreachable"
    assert r.status < 500, f"metadata/search -> {r.status}: {r.text[:200]}"

    # Catalog listing.
    r = c.get("/api/v1/data/metadata/catalog")
    assert r.status != 0, "metadata/catalog unreachable"
    assert r.status < 500, f"metadata/catalog -> {r.status}: {r.text[:200]}"

    # Zones listing.
    r = c.get("/api/v1/data/metadata/zones")
    assert r.status != 0, "metadata/zones unreachable"
    assert r.status < 500, f"metadata/zones -> {r.status}: {r.text[:200]}"


def test_isa_data_vector_store_crud(cleanup):
    """Create -> verify -> delete a vector store (requires DB).

    POST /api/v1/vector-stores (X-User-Id header) -> if created, register
    cleanup immediately, then GET it back. All assertions are < 500.
    """
    c = Client(SERVICE)

    # List first — main collection endpoint.
    r = c.get("/api/v1/vector-stores", headers=USER_HEADER)
    assert r.status != 0, "vector-stores list unreachable"
    assert r.status < 500, f"vector-stores list -> {r.status}: {r.text[:200]}"

    # Create with a minimal valid payload (only `name` is required).
    payload = {
        "name": f"parity-smoke-{uuid.uuid4().hex[:8]}",
        "description": "parity smoke test store (safe to delete)",
    }
    r = c.post("/api/v1/vector-stores", json_body=payload, headers=USER_HEADER)
    assert r.status != 0, "vector-stores create unreachable"
    assert r.status < 500, f"vector-stores create -> {r.status}: {r.text[:200]}"

    if r.ok:
        body = r.json() or {}
        store_id = body.get("id")
        if store_id:
            # Register cleanup IMMEDIATELY so we never leak test data.
            cleanup(
                Client(SERVICE, headers=USER_HEADER),
                f"/api/v1/vector-stores/{store_id}",
            )

            # Verify the created resource is readable.
            r = c.get(f"/api/v1/vector-stores/{store_id}", headers=USER_HEADER)
            assert r.status != 0, "vector-stores get-by-id unreachable"
            assert r.status < 500, (
                f"vector-stores get-by-id -> {r.status}: {r.text[:200]}"
            )


def test_isa_data_catalog_asset_register():
    """Register a catalog asset and read it back (no 5xx).

    POST /api/v1/data/catalog/assets accepts a unified RegisterAssetRequest.
    The catalog has no DELETE for assets (only contracts are deletable), so this
    flow registers a clearly-fake test asset and reads it back; nothing leakable
    is created via a deletable resource endpoint.
    """
    c = Client(SERVICE)

    # Asset registration — required fields: asset_type, asset_name, domain, description.
    payload = {
        "asset_type": "table",
        "asset_name": "parity-smoke-asset",
        "domain": "parity",
        "description": "parity smoke test asset (safe to ignore)",
    }
    r = c.post("/api/v1/data/catalog/assets", json_body=payload)
    assert r.status != 0, "catalog/assets register unreachable"
    assert r.status < 500, f"catalog/assets register -> {r.status}: {r.text[:200]}"

    if r.ok:
        body = r.json() or {}
        asset_id = body.get("asset_id") or body.get("id")
        if asset_id:
            # asset_id is a path param ({asset_id:path}); read it back.
            r = c.get(f"/api/v1/data/catalog/assets/{asset_id}")
            assert r.status != 0, "catalog/assets get-by-id unreachable"
            assert r.status < 500, (
                f"catalog/assets get-by-id -> {r.status}: {r.text[:200]}"
            )
