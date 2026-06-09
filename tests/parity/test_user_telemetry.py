"""Parity smoke for the **user-telemetry** service (telemetry_service).

Auth-gated: every data/metric/alert endpoint requires a user JWT
(auth_required=True in routes_registry.py + Depends(get_user_context) in main.py).
The `auth_headers` fixture supplies a real bootstrapped token and auto-skips when
auth is unavailable, so the public health checks still run everywhere.

Parity signal = no 5xx + inter-service calls resolve. The telemetry service fans
out to auth_service (token verify) and its time-series store; a 5xx is the
regression we hunt. We assert ONLY `r.status < 500`; 401/403/404/422 are all
acceptable parity outcomes. We never assert specific bodies or 200s — payload and
auth nuances make those brittle.

Endpoints exercised (from microservices/telemetry_service/main.py — note the real
app mounts everything under the `/api/v1/telemetry/` prefix; routes_registry.py is
stale on the prefix):
  - GET    /health                                   (public liveness)
  - GET    /api/v1/telemetry/health                  (public service health)
  - GET    /api/v1/telemetry/service/stats           (public service info)
  - GET    /api/v1/telemetry/metrics?limit=&offset=  (list metric defs, auth)
  - GET    /api/v1/telemetry/stats                   (service stats, auth)
  - GET    /api/v1/telemetry/alerts/rules            (list alert rules, auth)
  - POST   /api/v1/telemetry/metrics                 (create metric def, auth)
        body: MetricDefinitionRequest{name, data_type (required);
              metric_type/retention_days/aggregation_interval have defaults}
  - GET    /api/v1/telemetry/metrics/{metric_name}   (read back def, auth)
  - DELETE /api/v1/telemetry/metrics/{metric_name}   (cleanup, auth)
  - POST   /api/v1/telemetry/devices/{id}/telemetry/batch (batch ingest, auth)
        body: TelemetryBatchRequest{data_points: [TelemetryDataPoint{
              timestamp, metric_name, value, unit?}]}
"""

from __future__ import annotations

import os
import time

from conftest import Client

SERVICE = "user-telemetry"


def test_user_telemetry_health():
    """Public liveness endpoint must be reachable and not 5xx."""
    c = Client(SERVICE)
    r = c.get("/health")
    assert r.status != 0, "service unreachable (connection failed)"
    assert r.status < 500, f"/health 5xx: {r.text[:160]}"


def test_user_telemetry_service_stats():
    """Public service-info endpoint (auth_required=False) — no 5xx expected."""
    c = Client(SERVICE)
    r = c.get("/api/v1/telemetry/service/stats")
    assert r.status < 500, f"/api/v1/telemetry/service/stats 5xx: {r.text[:160]}"


def test_user_telemetry_list_metrics(auth_headers):
    """List the main metric-definitions collection — must resolve without a 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/telemetry/metrics?limit=10&offset=0", headers=auth_headers)
    assert r.status < 500, f"list metrics 5xx: {r.text[:160]}"


def test_user_telemetry_stats(auth_headers):
    """Service stats endpoint — auth-gated aggregate read; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/telemetry/stats", headers=auth_headers)
    assert r.status < 500, f"telemetry stats 5xx: {r.text[:160]}"


def test_user_telemetry_list_alert_rules(auth_headers):
    """List alert rules — exercises a second auth-gated read path; no 5xx."""
    c = Client(SERVICE)
    r = c.get("/api/v1/telemetry/alerts/rules", headers=auth_headers)
    assert r.status < 500, f"list alert rules 5xx: {r.text[:160]}"


def test_user_telemetry_metric_crud(auth_headers, cleanup):
    """CRUD parity: create metric definition -> read back -> auto-delete on teardown.

    Self-cleaning so it is safe to run against prod. We register the DELETE the
    moment the metric is created (resolving the real metric name from the request,
    since metrics are addressed by name), then read it back. Only parity-level
    assertions: every call must be < 500.
    """
    c = Client(SERVICE)
    # Clearly-fake, unique test data so repeat runs don't collide on metric name.
    suffix = f"{int(time.time())}-{os.getpid()}"
    metric_name = f"parity-smoke-{suffix}"
    payload = {
        "name": metric_name,
        "description": "parity-smoke metric definition",
        "data_type": "numeric",
        "metric_type": "gauge",
        "unit": "count",
        "retention_days": 90,
        "aggregation_interval": 60,
    }

    r = c.post("/api/v1/telemetry/metrics", json_body=payload, headers=auth_headers)
    assert r.status < 500, f"create metric 5xx: {r.text[:160]}"

    # Register cleanup immediately if the create succeeded — metrics are keyed by
    # name, so resolve the real name from the response (falling back to our input).
    created_name = None
    if r.ok:
        body = r.json() if isinstance(r.json(), dict) else {}
        created_name = body.get("name") or metric_name
        cleanup(c, f"/api/v1/telemetry/metrics/{created_name}")

    # Read the resource back by name — still parity-level (no 5xx). Use the created
    # name when available, else our synthetic one so the read path is still
    # exercised against the service (a 404 is an acceptable parity outcome).
    lookup_name = created_name or metric_name
    r2 = c.get(f"/api/v1/telemetry/metrics/{lookup_name}", headers=auth_headers)
    assert r2.status < 500, f"get metric 5xx: {r2.text[:160]}"


def test_user_telemetry_batch_ingest(auth_headers):
    """Batch-ingest a single data point — exercises the write/ingest path.

    Ingestion is append-only time-series data (no addressable resource id to
    delete), so there is nothing to register with cleanup here. We use clearly-fake
    device + metric names and a single point. Parity-level only: no 5xx.
    """
    c = Client(SERVICE)
    suffix = f"{int(time.time())}-{os.getpid()}"
    device_id = f"parity-smoke-{suffix}"
    payload = {
        "data_points": [
            {
                "timestamp": "2026-06-09T12:00:00Z",
                "metric_name": "temperature",
                "value": 22.5,
                "unit": "celsius",
            }
        ]
    }
    r = c.post(
        f"/api/v1/telemetry/devices/{device_id}/telemetry/batch",
        json_body=payload,
        headers=auth_headers,
    )
    assert r.status < 500, f"batch ingest 5xx: {r.text[:160]}"
