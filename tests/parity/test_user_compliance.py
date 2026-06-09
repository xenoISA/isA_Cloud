"""Parity smoke for the **user-compliance** service (compliance_service).

Endpoints come from microservices/compliance_service/main.py +
routes_registry.py. At the route-handler level the service declares
``auth_required=False`` (see SN-PARITY-AUDIT.md and routes_registry.py) —
auth is enforced at the APISIX gateway, not in the handler dependencies
(every functional route uses ``Depends(get_compliance_service/repository)``,
none use an auth dependency). We still pass ``auth_headers`` so the gateway
path resolves; the ``auth_headers`` fixture auto-skips when auth is
unavailable.

Parity signal = no 5xx + inter-service calls resolve. We deliberately assert
ONLY ``r.status < 500`` (401/403/404/422 are all acceptable parity outcomes),
never specific bodies or 200s — payload/auth nuances make those brittle.

NOTE ON CLEANUP: this service exposes **no DELETE** for compliance checks or
GDPR data requests (confirmed in routes_registry.py — only GDPR user-data has a
DELETE, which we do NOT exercise here to avoid destructive side effects). The
write flows below therefore POST clearly-fake test data (user_id="parity-smoke-*")
and register ``cleanup`` defensively whenever a delete-by-id path could plausibly
exist; if the resource is not deletable the registered teardown DELETE simply
returns 404/405 and is harmless. No undeletable destructive resources are created.

Endpoints exercised:
  - GET  /health                                         (public liveness)
  - GET  /status                                         (service status)
  - GET  /api/v1/compliance/policies                     (list collection)
  - GET  /api/v1/compliance/stats                        (stats read)
  - GET  /api/v1/compliance/reviews/pending              (pending reviews read)
  - GET  /api/v1/compliance/data-requests                (GDPR request list)
  - POST /api/v1/compliance/check                        (compliance check write)
        body: ComplianceCheckRequest{user_id, content_type, content, check_types}
  - GET  /api/v1/compliance/checks/{check_id}            (read back the check)
  - GET  /api/v1/compliance/checks/user/{user_id}        (read user checks)
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-compliance"


def test_user_compliance_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_compliance_status():
    """Service status endpoint — reports DB/NATS/provider health; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/status")
    assert r.status < 500, f"/status 5xx: {r.text[:160]}"


def test_user_compliance_list_policies(auth_headers):
    """List the compliance policies collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/compliance/policies", headers=auth_headers)
    assert r.status < 500, f"list policies 5xx: {r.text[:160]}"


def test_user_compliance_stats(auth_headers):
    """Statistics read path — aggregates across today/7d/30d; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/compliance/stats", headers=auth_headers)
    assert r.status < 500, f"stats 5xx: {r.text[:160]}"


def test_user_compliance_pending_reviews(auth_headers):
    """Pending human-review queue read — auth-gated read path; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/compliance/reviews/pending?limit=10", headers=auth_headers)
    assert r.status < 500, f"pending reviews 5xx: {r.text[:160]}"


def test_user_compliance_list_data_requests(auth_headers):
    """GDPR data-request queue list — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get(
        "/api/v1/compliance/data-requests?limit=50&offset=0", headers=auth_headers
    )
    assert r.status < 500, f"list data-requests 5xx: {r.text[:160]}"


def test_user_compliance_check_then_read(auth_headers, cleanup):
    """Write parity: POST a compliance check -> read it back by id + by user.

    POSTs clearly-fake test content via ComplianceCheckRequest (required fields:
    user_id, content_type; content is the text payload). The service persists a
    check record but exposes no DELETE for checks — we register a defensive
    cleanup against the conventional delete-by-id path so any future delete
    support is exercised, and it is harmless (404/405) today. Parity-level only:
    every call must be < 500.
    """
    c = Client(SERVICE)
    user_id = "parity-smoke-user"
    payload = {
        "user_id": user_id,
        "content_type": "text",
        "content": "parity-smoke test content",
        "check_types": ["content_moderation", "pii_detection"],
    }

    r = c.post("/api/v1/compliance/check", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"compliance check 5xx: {r.text[:160]}"

    check_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        check_id = body.get("check_id")
        if check_id:
            # Defensive cleanup: harmless 404/405 if no delete exists for checks.
            cleanup(c, f"/api/v1/compliance/checks/{check_id}")

    # Read back by id (use the returned id when present, else a fake id —
    # either way only a parity-level (<500) assertion).
    lookup_id = check_id or "parity-smoke-check"
    r2 = c.get(f"/api/v1/compliance/checks/{lookup_id}", headers=auth_headers)
    assert r2.status < 500, f"get check by id 5xx: {r2.text[:160]}"

    # Read back the user's checks collection.
    r3 = c.get(
        f"/api/v1/compliance/checks/user/{user_id}?limit=10", headers=auth_headers
    )
    assert r3.status < 500, f"get user checks 5xx: {r3.text[:160]}"
