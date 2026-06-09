"""Parity tests for the isA `user-document` service (document_service).

Source of truth: isA_user/microservices/document_service
  - routes_registry.py : real paths + capabilities
  - main.py            : route handlers (user_id is a required query param via
                         get_user_id Depends; all CRUD endpoints auth-gated)
  - models.py          : DocumentCreateRequest required fields
                         (title, doc_type, file_id)
  - SN-PARITY-AUDIT.md : suggested flows (document_lifecycle_crud,
                         permission_management, rag_and_search)

Endpoints (all under /api/v1/documents):
  GET    /api/v1/documents/health                     health (public)
  POST   /api/v1/documents                            create document
  GET    /api/v1/documents                            list user documents
  GET    /api/v1/documents/stats                      user document stats
  GET    /api/v1/documents/{doc_id}                   read document by ID
  DELETE /api/v1/documents/{doc_id}                   delete (soft by default)
  PUT    /api/v1/documents/{doc_id}/update            RAG incremental update
  PUT    /api/v1/documents/{doc_id}/permissions       update permissions
  GET    /api/v1/documents/{doc_id}/permissions       get permissions
  POST   /api/v1/documents/rag/query                  RAG query (perm-filtered)
  POST   /api/v1/documents/search                     semantic search

Parity assertion contract: assert ONLY `r.status < 500`. A 5xx means a real
bug (handler crash or unresolved inter-service call to storage_service /
digital_analytics / authorization). 401/403/422 are acceptable parity
outcomes (auth/validation nuance), not failures.

The service binds user identity from a required `user_id` query param, so we
thread it through every call alongside the auth headers.
"""

SERVICE = "user-document"
USER_ID = "parity-smoke-user"


def test_user_document_health(http):
    """Public health endpoint must be reachable and not 5xx."""
    client = http(SERVICE)
    r = client.get("/api/v1/documents/health")
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"health 5xx: {r.status} {r.text}"


def test_user_document_list(http, auth_headers):
    """List the main documents collection — must not 5xx."""
    client = http(SERVICE)
    r = client.get(f"/api/v1/documents?user_id={USER_ID}", headers=auth_headers)
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"list 5xx: {r.status} {r.text}"


def test_user_document_stats(http, auth_headers):
    """Stats endpoint aggregates per-user document data — must not 5xx."""
    client = http(SERVICE)
    r = client.get(f"/api/v1/documents/stats?user_id={USER_ID}", headers=auth_headers)
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"stats 5xx: {r.status} {r.text}"


def test_user_document_crud(http, auth_headers, cleanup):
    """Create -> verify-by-id -> delete a document. Self-cleaning, prod-safe.

    Minimal valid payload per DocumentCreateRequest: title, doc_type, file_id
    are required. file_id references storage_service; an unknown id may yield a
    4xx, which is acceptable parity (we only fail on 5xx).
    """
    client = http(SERVICE)

    payload = {
        "title": "parity-smoke",
        "description": "parity smoke test document",
        "doc_type": "txt",
        "file_id": "parity-smoke-file",
        "access_level": "private",
        "tags": ["parity-smoke"],
    }
    r = client.post(
        f"/api/v1/documents?user_id={USER_ID}", json_body=payload, headers=auth_headers
    )
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"create 5xx: {r.status} {r.text}"

    if r.ok:
        body = r.json() or {}
        doc_id = body.get("doc_id") or body.get("id")
        if doc_id:
            # Register cleanup IMMEDIATELY so the doc is never left behind.
            cleanup(client, f"/api/v1/documents/{doc_id}?user_id={USER_ID}")

            got = client.get(
                f"/api/v1/documents/{doc_id}?user_id={USER_ID}", headers=auth_headers
            )
            assert got.status != 0, "service unreachable"
            assert got.status < 500, f"read 5xx: {got.status} {got.text}"


def test_user_document_permissions(http, auth_headers, cleanup):
    """Create a doc, then read/update its permissions. No 5xx.

    The owner reads then updates permissions; unknown users/groups yield at
    worst a 4xx (acceptable parity).
    """
    client = http(SERVICE)

    r = client.post(
        f"/api/v1/documents?user_id={USER_ID}",
        json_body={
            "title": "parity-smoke",
            "doc_type": "txt",
            "file_id": "parity-smoke-file",
        },
        headers=auth_headers,
    )
    assert r.status < 500, f"create 5xx: {r.status} {r.text}"

    if not r.ok:
        return
    doc_id = (r.json() or {}).get("doc_id")
    if not doc_id:
        return
    cleanup(client, f"/api/v1/documents/{doc_id}?user_id={USER_ID}")

    get_perms = client.get(
        f"/api/v1/documents/{doc_id}/permissions?user_id={USER_ID}",
        headers=auth_headers,
    )
    assert get_perms.status < 500, f"get perms 5xx: {get_perms.status} {get_perms.text}"

    upd_perms = client.put(
        f"/api/v1/documents/{doc_id}/permissions?user_id={USER_ID}",
        json_body={"access_level": "team", "add_users": ["parity-smoke-other"]},
        headers=auth_headers,
    )
    assert upd_perms.status < 500, (
        f"update perms 5xx: {upd_perms.status} {upd_perms.text}"
    )


def test_user_document_rag_and_search(http, auth_headers):
    """RAG query + semantic search endpoints. No 5xx.

    Per the audit, these degrade gracefully when digital_analytics is
    unavailable (empty results), so a 4xx/empty body is acceptable parity.
    """
    client = http(SERVICE)

    rag = client.post(
        f"/api/v1/documents/rag/query?user_id={USER_ID}",
        json_body={"query": "What is in this document?", "top_k": 5},
        headers=auth_headers,
    )
    assert rag.status != 0, "service unreachable"
    assert rag.status < 500, f"rag query 5xx: {rag.status} {rag.text}"

    search = client.post(
        f"/api/v1/documents/search?user_id={USER_ID}",
        json_body={"query": "parity smoke", "top_k": 10},
        headers=auth_headers,
    )
    assert search.status != 0, "service unreachable"
    assert search.status < 500, f"search 5xx: {search.status} {search.text}"
