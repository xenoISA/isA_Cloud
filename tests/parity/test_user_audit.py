"""Parity flows for the **user-audit** service (isA_user/microservices/audit_service).

Parity-level, not business-level: we only assert that endpoints are reachable and
return no 5xx. A 5xx is the real bug class this suite hunts (DSN/cred, hardcoded
localhost, response-model-on-empty, broken inter-service calls). 401/403 (auth-gated)
and 422 (validation) are acceptable outcomes and still pass.

Service surface (from routes_registry.py + main.py):
  - GET  /health, /api/v1/audit/health, /api/v1/audit/info        (public)
  - GET  /api/v1/audit/compliance/standards                       (public)
  - GET  /api/v1/audit/stats                                      (auth)
  - GET/POST /api/v1/audit/events                                 (auth)
  - POST /api/v1/audit/events/query                               (auth)
  - POST /api/v1/audit/events/batch  (raw List[AuditEventCreateRequest])  (auth)
  - GET  /api/v1/audit/users/{user_id}/activities|summary         (auth)
  - POST /api/v1/audit/security/alerts                            (auth)
  - GET  /api/v1/audit/security/events                            (auth)
  - POST /api/v1/audit/compliance/reports                         (auth)
  - GET/POST /api/v1/audit/admin/actions                          (auth)

NOTE: audit events / admin actions are append-only — the service exposes no DELETE
for them (only POST /maintenance/cleanup, which we never call). Creates are therefore
inherently prod-safe: they write clearly-fake "parity-smoke" rows that are never
deleted by id. The `cleanup` fixture is still wired in per the harness contract for
any future deletable resource.
"""

from __future__ import annotations

from conftest import Client

SERVICE = "user-audit"

# A minimal VALID AuditEventCreateRequest. event_type/category/severity are enums;
# action is the only other required field. Fake, greppable test data.
_EVENT = {
    "event_type": "user_login",
    "category": "authentication",
    "severity": "low",
    "action": "parity-smoke login",
    "description": "parity-smoke synthetic audit event",
    "user_id": "parity-smoke-user",
    "success": True,
    "tags": ["parity-smoke"],
}


# ---------------------------------------------------------------------------
# 1. Public read/list parity — no auth needed.
# ---------------------------------------------------------------------------
def test_user_audit_public_reads():
    """Public health/info/standards endpoints must be reachable and not 5xx."""
    c = Client(SERVICE)
    for path in (
        "/health",
        "/api/v1/audit/health",
        "/api/v1/audit/info",
        "/api/v1/audit/compliance/standards",
    ):
        r = c.get(path)
        assert r.status != 0, f"{path}: unreachable ({r.text[:120]})"
        assert r.status < 500, f"{path}: 5xx ({r.status}) {r.text[:160]}"


# ---------------------------------------------------------------------------
# 2. Auth-gated collection reads — events list + stats + query.
# ---------------------------------------------------------------------------
def test_user_audit_authed_reads(auth_headers):
    """Main collection endpoints (events list, stats, query) must not 5xx."""
    c = Client(SERVICE)

    r = c.get("/api/v1/audit/events?user_id=parity-smoke-user", headers=auth_headers)
    assert r.status != 0, f"events list unreachable ({r.text[:120]})"
    assert r.status < 500, f"events list 5xx ({r.status}) {r.text[:160]}"

    r = c.get("/api/v1/audit/stats", headers=auth_headers)
    assert r.status < 500, f"stats 5xx ({r.status}) {r.text[:160]}"

    r = c.post(
        "/api/v1/audit/events/query",
        {"user_id": "parity-smoke-user", "limit": 10},
        headers=auth_headers,
    )
    assert r.status < 500, f"events/query 5xx ({r.status}) {r.text[:160]}"


# ---------------------------------------------------------------------------
# 3. Create -> verify CRUD flow on audit events (append-only; self-cleaning).
# ---------------------------------------------------------------------------
def test_user_audit_event_create_and_verify(auth_headers, cleanup):
    """POST a minimal valid audit event, then read it back. Parity asserts only.

    Audit events have no DELETE endpoint (append-only ledger), so created rows are
    fake "parity-smoke" data that are intentionally never removed. cleanup is still
    available and would be used if a deletable id were ever returned.
    """
    c = Client(SERVICE)

    r = c.post("/api/v1/audit/events", _EVENT, headers=auth_headers)
    assert r.status != 0, f"event create unreachable ({r.text[:120]})"
    assert r.status < 500, f"event create 5xx ({r.status}) {r.text[:160]}"

    # If the create succeeded and returned an id, register cleanup IMMEDIATELY
    # (no-op DELETE if the route is absent — the harness swallows failures) and
    # read the resource back. We do not assert on body shape (parity, not business).
    if r.ok:
        body = r.json() or {}
        event_id = body.get("id")
        if event_id:
            cleanup(c, f"/api/v1/audit/events/{event_id}")
            rg = c.get(
                f"/api/v1/audit/events?user_id={_EVENT['user_id']}",
                headers=auth_headers,
            )
            assert rg.status < 500, f"event read-back 5xx ({rg.status}) {rg.text[:160]}"


# ---------------------------------------------------------------------------
# 4. Batch create flow — raw list payload (List[AuditEventCreateRequest]).
# ---------------------------------------------------------------------------
def test_user_audit_event_batch(auth_headers):
    """POST a 2-event batch; the endpoint must accept it without 5xx."""
    c = Client(SERVICE)
    batch = [
        dict(_EVENT, action="parity-smoke batch 1"),
        dict(_EVENT, action="parity-smoke batch 2"),
    ]
    r = c.post("/api/v1/audit/events/batch", batch, headers=auth_headers)
    assert r.status != 0, f"events/batch unreachable ({r.text[:120]})"
    assert r.status < 500, f"events/batch 5xx ({r.status}) {r.text[:160]}"


# ---------------------------------------------------------------------------
# 5. Admin audit trail — record action then list (inter-service / DB write path).
# ---------------------------------------------------------------------------
def test_user_audit_admin_action_create_and_list(auth_headers):
    """Record an admin action, then list admin actions. Parity asserts only."""
    c = Client(SERVICE)
    payload = {
        "admin_user_id": "parity-smoke-admin",
        "admin_email": "parity-smoke@example.com",
        "action": "parity_smoke_action",
        "resource_type": "parity_smoke_resource",
        "resource_id": "parity-smoke-1",
        "changes": {"before": None, "after": "parity-smoke"},
    }
    r = c.post("/api/v1/audit/admin/actions", payload, headers=auth_headers)
    assert r.status != 0, f"admin/actions create unreachable ({r.text[:120]})"
    assert r.status < 500, f"admin/actions create 5xx ({r.status}) {r.text[:160]}"

    rl = c.get(
        "/api/v1/audit/admin/actions?admin_user_id=parity-smoke-admin",
        headers=auth_headers,
    )
    assert rl.status < 500, f"admin/actions list 5xx ({rl.status}) {rl.text[:160]}"


# ---------------------------------------------------------------------------
# 6. Security alert + compliance report — secondary write/read paths.
# ---------------------------------------------------------------------------
def test_user_audit_security_and_compliance(auth_headers):
    """Security alert create, security events read, and compliance report gen."""
    c = Client(SERVICE)

    alert = {
        "threat_type": "parity_smoke_threat",
        "severity": "low",
        "source_ip": "203.0.113.10",
        "target_resource": "parity-smoke-resource",
        "description": "parity-smoke synthetic security alert",
    }
    r = c.post("/api/v1/audit/security/alerts", alert, headers=auth_headers)
    assert r.status != 0, f"security/alerts unreachable ({r.text[:120]})"
    assert r.status < 500, f"security/alerts 5xx ({r.status}) {r.text[:160]}"

    rg = c.get("/api/v1/audit/security/events?days=7", headers=auth_headers)
    assert rg.status < 500, f"security/events 5xx ({rg.status}) {rg.text[:160]}"

    report = {
        "report_type": "parity_smoke",
        "compliance_standard": "GDPR",
        "period_start": "2026-01-01T00:00:00Z",
        "period_end": "2026-01-31T23:59:59Z",
        "include_details": True,
    }
    rc = c.post("/api/v1/audit/compliance/reports", report, headers=auth_headers)
    assert rc.status < 500, f"compliance/reports 5xx ({rc.status}) {rc.text[:160]}"
