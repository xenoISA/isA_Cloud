"""Parity smoke for the **user-ota** service (ota_service).

OTA = over-the-air firmware/device-update service. Most endpoints are
auth-gated (auth_required=True in routes_registry.py + get_user_context dep in
main.py); only the health and service-stats endpoints are public. The
`auth_headers` fixture supplies a real bootstrapped token and auto-skips when
auth is unavailable, so the public health checks still run everywhere.

Parity signal = no 5xx + inter-service calls resolve. The OTA service fans out
to auth_service (token verify), device_service, storage_service and
notification_service — a 5xx is the regression we hunt. We assert ONLY
`r.status < 500`; 400/401/403/404/422 are all acceptable parity outcomes. We
never assert specific bodies or 200s — payload/auth nuances make those brittle.

NOTE on CRUD: the only JSON create endpoint is POST /api/v1/ota/campaigns
(UpdateCampaignRequest). Firmware create is a multipart file upload, not JSON,
so it is not exercised here. A campaign requires an existing firmware_id, so the
create commonly resolves to 400/404 (firmware not found) — still a valid parity
outcome (< 500). We register cleanup immediately if a campaign_id comes back so
the test is self-cleaning and safe against prod.

Endpoints exercised (paths from microservices/ota_service/main.py — the live
FastAPI app mounts everything under /api/v1/ota/, not the bare /api/v1/ in the
Consul routes_registry):
  - GET  /health                                   (public liveness)
  - GET  /api/v1/ota/health                          (public service health)
  - GET  /api/v1/ota/service/stats                   (public service stats)
  - GET  /api/v1/ota/firmware?limit=&offset=         (list firmware, auth)
  - GET  /api/v1/ota/campaigns?limit=&offset=        (list campaigns, auth)
  - GET  /api/v1/ota/stats                           (update statistics, auth)
  - POST /api/v1/ota/campaigns                       (create campaign, auth)
        body: UpdateCampaignRequest{name, firmware_id} (required)
  - GET  /api/v1/ota/campaigns/{campaign_id}         (read back, auth)
  - DELETE registered via cleanup if a campaign id is returned
"""

from __future__ import annotations

import os
import time

from conftest import Client

SERVICE = "user-ota"


def test_user_ota_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_ota_service_stats():
    """Public service-stats endpoint (no auth dep) — no 5xx expected."""
    c = Client(SERVICE)
    r = c.get("/api/v1/ota/service/stats")
    assert r.status < 500, f"/api/v1/ota/service/stats 5xx: {r.text[:160]}"


def test_user_ota_firmware_list(auth_headers):
    """List the firmware collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/ota/firmware?limit=10&offset=0", headers=auth_headers)
    assert r.status < 500, f"list firmware 5xx: {r.text[:160]}"


def test_user_ota_campaigns_list(auth_headers):
    """List the campaigns collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/ota/campaigns?limit=10&offset=0", headers=auth_headers)
    assert r.status < 500, f"list campaigns 5xx: {r.text[:160]}"


def test_user_ota_stats(auth_headers):
    """Update-statistics aggregate read — auth-gated; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/ota/stats", headers=auth_headers)
    assert r.status < 500, f"update stats 5xx: {r.text[:160]}"


def test_user_ota_campaign_create_read_delete(auth_headers, cleanup):
    """CRUD parity: create campaign -> read back -> auto-clean on teardown.

    A campaign needs an existing firmware_id; with clearly-fake test data the
    service most likely returns 400/404 (firmware not found) — an acceptable
    parity outcome. If a campaign IS created we resolve its real campaign_id from
    the response and register the DELETE immediately, then read it back. Only
    parity-level assertions: every call must be < 500.
    """
    c = Client(SERVICE)
    suffix = f"{int(time.time())}-{os.getpid()}"
    payload = {
        "name": "parity-smoke",
        "description": "parity-smoke campaign",
        "firmware_id": f"parity-smoke-{suffix}",
        "target_devices": [],
        "deployment_strategy": "staged",
        "priority": "normal",
    }

    r = c.post("/api/v1/ota/campaigns", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"create campaign 5xx: {r.text[:160]}"

    # Register cleanup immediately if the create succeeded — resolve the real id.
    campaign_id = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        campaign_id = body.get("campaign_id")
        if campaign_id:
            cleanup(c, f"/api/v1/ota/campaigns/{campaign_id}")

    # Read the resource back by id — still parity-level (no 5xx). Fall back to a
    # synthetic id when the create did not return one, so the read path is still
    # exercised against the service (a 404 is an acceptable parity outcome).
    lookup_id = campaign_id or f"parity-smoke-{suffix}"
    r2 = c.get(f"/api/v1/ota/campaigns/{lookup_id}", headers=auth_headers)
    assert r2.status < 500, f"get campaign 5xx: {r2.text[:160]}"
