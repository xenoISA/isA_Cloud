"""Parity tests for the isA `user-campaign` service (campaign_service).

Source of truth: isA_user/microservices/campaign_service
  - main.py            : real route paths + decorators
  - routes_registry.py : base_path /api/v1/campaigns, auth_required=True
  - models.py -> tests/contracts/campaign/data_contract.py :
      CampaignCreateRequest required fields = name (str) + campaign_type
      (CampaignType enum: "scheduled" | "triggered"); everything else
      (audiences, channels, schedule, throttle, ...) is optional.
  - SN-PARITY-AUDIT.md : suggested flows (create -> get -> patch -> list
      -> delete; schedule/pause/resume; variants; metrics/preview).

Endpoints (all under /api/v1/campaigns, every handler depends on
get_auth_context so auth is required except health):
  GET    /api/v1/campaigns/health                          (public)
  GET    /api/v1/campaigns                                 list campaigns
  POST   /api/v1/campaigns                                 create campaign
  GET    /api/v1/campaigns/{campaign_id}                   read campaign
  PATCH  /api/v1/campaigns/{campaign_id}                   update campaign
  DELETE /api/v1/campaigns/{campaign_id}                   soft-delete
  POST   /api/v1/campaigns/{campaign_id}/schedule         schedule
  POST   /api/v1/campaigns/{campaign_id}/pause            pause
  POST   /api/v1/campaigns/{campaign_id}/resume           resume
  POST   /api/v1/campaigns/{campaign_id}/cancel           cancel
  POST   /api/v1/campaigns/{campaign_id}/clone            clone
  GET    /api/v1/campaigns/{campaign_id}/metrics          metrics
  POST   /api/v1/campaigns/{campaign_id}/variants         add A/B variant
  POST   /api/v1/campaigns/{campaign_id}/audiences/estimate  estimate
  POST   /api/v1/campaigns/{campaign_id}/preview          preview content

Response shape: create/get/patch return CampaignResponse =
  {"campaign": {"campaign_id": "cmp_...", ...}, "message": "..."}.

Parity assertion contract: assert ONLY `r.status < 500`. A 5xx means a
real bug (handler crash or unresolved inter-service call). 401/403/422
are acceptable parity outcomes (auth/validation nuance), not failures.
"""

from conftest import Client  # noqa: F401  (harness import per contract)

SERVICE = "user-campaign"


def _create_campaign(client, auth_headers):
    """POST a minimal valid campaign. Returns (resp, campaign_id|None)."""
    payload = {
        "name": "parity-smoke",
        "description": "parity smoke test campaign",
        "campaign_type": "scheduled",
        "timezone": "UTC",
        "tags": ["parity-smoke"],
    }
    r = client.post("/api/v1/campaigns", json_body=payload, headers=auth_headers)
    campaign_id = None
    if r.ok:
        body = r.json() or {}
        campaign = body.get("campaign") or {}
        campaign_id = (
            campaign.get("campaign_id")
            or campaign.get("id")
            or body.get("campaign_id")
            or body.get("id")
        )
    return r, campaign_id


def test_user_campaign_health(http):
    """Public health endpoint must be reachable and not 5xx."""
    client = http(SERVICE)
    r = client.get("/api/v1/campaigns/health")
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"health 5xx: {r.status} {r.text}"


def test_user_campaign_list(http, auth_headers):
    """List the main campaigns collection (with pagination) — must not 5xx."""
    client = http(SERVICE)
    r = client.get("/api/v1/campaigns?limit=20&offset=0", headers=auth_headers)
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"list 5xx: {r.status} {r.text}"


def test_user_campaign_crud(http, auth_headers, cleanup):
    """Create -> verify-by-id -> delete a campaign. Self-cleaning, prod-safe.

    Minimal valid payload per CampaignCreateRequest: name + campaign_type.
    """
    client = http(SERVICE)

    r, campaign_id = _create_campaign(client, auth_headers)
    assert r.status != 0, "service unreachable"
    assert r.status < 500, f"create 5xx: {r.status} {r.text}"

    if campaign_id:
        # Register cleanup IMMEDIATELY so the campaign is never left behind.
        cleanup(client, f"/api/v1/campaigns/{campaign_id}")

        got = client.get(f"/api/v1/campaigns/{campaign_id}", headers=auth_headers)
        assert got.status != 0, "service unreachable"
        assert got.status < 500, f"read 5xx: {got.status} {got.text}"

        # The real update verb is PATCH (main.py:@app.patch). The harness
        # Client only exposes get/post/put/delete, so we don't issue a write
        # update here; cleanup below soft-deletes via the real DELETE route.


def test_user_campaign_lifecycle(http, auth_headers, cleanup):
    """Create -> schedule -> pause -> resume -> cancel. No 5xx at any step.

    State-machine transitions may legitimately 4xx (e.g. pausing a campaign
    that isn't running); we only assert the service never crashes (5xx).
    """
    client = http(SERVICE)

    r, campaign_id = _create_campaign(client, auth_headers)
    assert r.status < 500, f"create 5xx: {r.status} {r.text}"
    if not campaign_id:
        return
    cleanup(client, f"/api/v1/campaigns/{campaign_id}")

    sched = client.post(
        f"/api/v1/campaigns/{campaign_id}/schedule",
        json_body={"scheduled_at": "2030-01-01T10:00:00Z", "timezone": "UTC"},
        headers=auth_headers,
    )
    assert sched.status < 500, f"schedule 5xx: {sched.status} {sched.text}"

    pause = client.post(
        f"/api/v1/campaigns/{campaign_id}/pause",
        json_body={},
        headers=auth_headers,
    )
    assert pause.status < 500, f"pause 5xx: {pause.status} {pause.text}"

    resume = client.post(
        f"/api/v1/campaigns/{campaign_id}/resume",
        json_body={},
        headers=auth_headers,
    )
    assert resume.status < 500, f"resume 5xx: {resume.status} {resume.text}"

    cancel = client.post(
        f"/api/v1/campaigns/{campaign_id}/cancel",
        json_body={"reason": "parity-smoke cleanup"},
        headers=auth_headers,
    )
    assert cancel.status < 500, f"cancel 5xx: {cancel.status} {cancel.text}"


def test_user_campaign_metrics_and_preview(http, auth_headers, cleanup):
    """Create -> estimate audience -> preview content -> metrics. No 5xx.

    These endpoints fan out to sibling services (account/notification) and
    are exactly where an unresolved inter-service call would surface as a
    5xx — the parity signal we hunt for.
    """
    client = http(SERVICE)

    r, campaign_id = _create_campaign(client, auth_headers)
    assert r.status < 500, f"create 5xx: {r.status} {r.text}"
    if not campaign_id:
        return
    cleanup(client, f"/api/v1/campaigns/{campaign_id}")

    estimate = client.post(
        f"/api/v1/campaigns/{campaign_id}/audiences/estimate",
        json_body={},
        headers=auth_headers,
    )
    assert estimate.status < 500, f"estimate 5xx: {estimate.status} {estimate.text}"

    preview = client.post(
        f"/api/v1/campaigns/{campaign_id}/preview",
        json_body={"sample_user_id": "parity-smoke-user"},
        headers=auth_headers,
    )
    assert preview.status < 500, f"preview 5xx: {preview.status} {preview.text}"

    metrics = client.get(
        f"/api/v1/campaigns/{campaign_id}/metrics", headers=auth_headers
    )
    assert metrics.status < 500, f"metrics 5xx: {metrics.status} {metrics.text}"
