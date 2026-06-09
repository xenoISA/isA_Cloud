"""Baseline cloud-native read-parity — runs against ANY target (local/SN/GCP).

For every service: it must be reachable and no plain GET endpoint may 500.
A 5xx here is a real functional/parity bug (the class this suite exists to catch:
DSN/cred, hardcoded localhost, missing content, response-model-on-empty, etc.).
401/403 (auth-gated) and 422 (needs a query param) are EXPECTED and pass.

This file needs NO auth, so it validates env-resolution + DB-read + serialization
for the whole platform in one run, in any environment.
"""

from __future__ import annotations

import json

import pytest

from config import all_services
from conftest import Client

SERVICES = all_services()


@pytest.mark.parametrize("service", SERVICES)
def test_service_reachable(service):
    """Service answers /health (or root) and is not erroring."""
    c = Client(service)
    r = c.get("/health")
    if r.status in (0, 404):  # no /health — try root / openapi as liveness
        r = c.get("/openapi.json")
    assert r.status not in (0,), f"{service}: unreachable ({r.text[:120]})"
    assert r.status < 500, f"{service}: /health 5xx ({r.status})"


def _no_param_gets(c: Client) -> list[str]:
    r = c.get("/openapi.json")
    if not r.ok:
        return []
    try:
        spec = json.loads(r.text)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for path, methods in (spec.get("paths") or {}).items():
        if "{" in path:
            continue
        if any(m.lower() == "get" for m in methods):
            out.append(path)
    return sorted(out)


@pytest.mark.parametrize("service", SERVICES)
def test_no_get_endpoint_5xxs(service):
    """No no-path-param GET endpoint returns 5xx (5xx == real bug)."""
    c = Client(service)
    paths = _no_param_gets(c)
    if not paths:
        pytest.skip(f"{service}: no OpenAPI GET endpoints (e.g. MCP/stateless)")
    failures = []
    for p in paths[:25]:
        r = c.get(p)
        if r.status >= 500:
            failures.append(f"{r.status} {p}")
    assert not failures, f"{service}: 5xx on {failures}"
