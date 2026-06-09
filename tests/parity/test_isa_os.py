"""Parity tests for the isa-os web service (isA_OS/web_services).

isa-os is a stateless web-automation service: search / crawl / automation are
POST *actions* that return results (they don't persist a queryable resource), and
the browser endpoints manage ephemeral in-memory sessions (open -> ... -> close).
There is no classic DB-backed CRUD-with-id collection, so the closest analogue to
create->verify->delete is browser/open -> ... -> browser/close (note: close is a
POST, not a DELETE, so it can't use the DELETE-only `cleanup` fixture — the open
flow is made self-cleaning with an explicit close in a finally block).

Parity signal (per SN-PARITY-AUDIT): no 5xx + inter-service calls resolve. Auth is
required, so authed tests carry `auth_headers` (auto-skips if auth is unavailable).
We assert ONLY `r.status < 500` (a 5xx is the bug we hunt; 401/403/422/404/502/503
on a downstream that's unreachable in a given env are acceptable parity outcomes,
but a 500 from this service's own code is not — note 5xx >= 500 would fail, which
is intentional only for true server errors; downstream-dependency statuses the
service deliberately raises as 502/503/504 are gated behind auth and not exercised
with real downstream wiring here).
"""

from __future__ import annotations

from conftest import Client

SERVICE = "isa-os"

# Realistic, fake-but-valid payloads derived from src/api/models.py request models.
_SEARCH_PAYLOAD = {
    "query": "parity-smoke test query",
    "count": 5,
    "provider": "self_hosted",
}
_CRAWL_PAYLOAD = {"url": "http://example.com", "provider": "self_hosted"}
_AUTOMATION_PAYLOAD = {
    "url": "http://example.com",
    "task": "parity-smoke click button",
    "provider": "self_hosted",
}


def test_isa_os_health_reachable():
    """GET /health must be reachable and never 5xx (public, no auth)."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, f"isa-os: unreachable ({r.text[:160]})"
    assert r.status < 500, f"isa-os: /health 5xx ({r.status}) {r.text[:160]}"


def test_isa_os_list_providers(auth_headers):
    """List/read flow: GET the providers collection. No 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/web/providers", headers=auth_headers)
    assert r.status != 0, f"isa-os: providers unreachable ({r.text[:160]})"
    assert r.status < 500, f"isa-os: GET providers 5xx ({r.status}) {r.text[:160]}"


def test_isa_os_provider_health_read(auth_headers):
    """Read a single provider's health by composite id. No 5xx (404 is fine)."""
    c = Client(SERVICE)
    r = c.get(
        "/api/v1/web/providers/search/self_hosted/health",
        headers=auth_headers,
    )
    assert r.status != 0, f"isa-os: provider health unreachable ({r.text[:160]})"
    assert r.status < 500, f"isa-os: provider health 5xx ({r.status}) {r.text[:160]}"


def test_isa_os_search_action(auth_headers):
    """Search action endpoint accepts a valid SearchRequest payload without 5xx."""
    c = Client(SERVICE)
    r = c.post("/api/v1/web/search", _SEARCH_PAYLOAD, headers=auth_headers)
    assert r.status != 0, f"isa-os: search unreachable ({r.text[:160]})"
    assert r.status < 500, f"isa-os: POST search 5xx ({r.status}) {r.text[:160]}"


def test_isa_os_crawl_action(auth_headers):
    """Crawl action endpoint accepts a valid CrawlRequest payload without 5xx."""
    c = Client(SERVICE)
    r = c.post("/api/v1/web/crawl", _CRAWL_PAYLOAD, headers=auth_headers)
    assert r.status != 0, f"isa-os: crawl unreachable ({r.text[:160]})"
    assert r.status < 500, f"isa-os: POST crawl 5xx ({r.status}) {r.text[:160]}"


def test_isa_os_automation_action(auth_headers):
    """Automation action endpoint accepts a valid AutomationRequest payload without 5xx."""
    c = Client(SERVICE)
    r = c.post(
        "/api/v1/web/automation/execute",
        _AUTOMATION_PAYLOAD,
        headers=auth_headers,
    )
    assert r.status != 0, f"isa-os: automation unreachable ({r.text[:160]})"
    assert r.status < 500, f"isa-os: POST automation 5xx ({r.status}) {r.text[:160]}"


def test_isa_os_browser_open_close_lifecycle(auth_headers):
    """Pseudo-CRUD: open a browser session (create) -> verify reachable -> close (delete).

    browser/close is a POST (not DELETE), so the DELETE-only `cleanup` fixture
    can't tear this down — instead the session is closed explicitly in a finally
    block, keeping the flow self-cleaning and safe to run against prod.
    """
    c = Client(SERVICE)
    open_payload = {"url": "http://example.com", "runtime": "local"}
    r = c.post("/api/v1/web/browser/open", open_payload, headers=auth_headers)
    assert r.status != 0, f"isa-os: browser/open unreachable ({r.text[:160]})"
    assert r.status < 500, f"isa-os: POST browser/open 5xx ({r.status}) {r.text[:160]}"

    session_id = None
    body = r.json()
    if r.ok and isinstance(body, dict):
        session_id = body.get("session_id")

    try:
        if session_id:
            # Verify: observe the just-opened session (read by id). No 5xx.
            v = c.post(
                "/api/v1/web/browser/observe",
                {"session_id": session_id},
                headers=auth_headers,
            )
            assert v.status < 500, (
                f"isa-os: browser/observe 5xx ({v.status}) {v.text[:160]}"
            )
    finally:
        if session_id:
            # Delete: explicitly close the session so no state is left behind.
            c.post(
                "/api/v1/web/browser/close",
                {"session_id": session_id},
                headers=auth_headers,
            )
