"""
V-5: Apicurio Registry schema register + v2 BACKWARD-compat evolution.

Mirrors the V-5 phase-C gate in verify-bigdata-kind.sh, but as a pytest
case so it can run as part of CI. Steps:

  1. Register an AVRO artifact under group `verify-pytest`, ID `hello`.
  2. Set BACKWARD compatibility on the artifact.
  3. POST a v2 schema that adds an optional `label` field — should pass
     compat check.
  4. Fetch the latest schema version and assert it includes `label`.
  5. Cleanup: DELETE the artifact.

The Apicurio Registry authoritative API is `/apis/registry/v2/...`.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

GROUP = "verify-pytest"
ARTIFACT = "hello"

V1_SCHEMA = {
    "type": "record",
    "name": "Hello",
    "fields": [{"name": "id", "type": "string"}],
}

V2_SCHEMA_BACKWARD_COMPAT = {
    "type": "record",
    "name": "Hello",
    "fields": [
        {"name": "id", "type": "string"},
        {"name": "label", "type": ["null", "string"], "default": None},
    ],
}


def _http(
    method: str,
    url: str,
    body: dict | None = None,
    headers: dict | None = None,
) -> tuple[int, str]:
    headers = headers or {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _delete_artifact(base: str) -> None:
    """Best-effort cleanup — never fail the test for cleanup errors."""
    try:
        _http("DELETE", f"{base}/groups/{GROUP}/artifacts/{ARTIFACT}")
    except Exception:
        pass


def test_v5_apicurio_schema_register_and_evolve(apicurio_forward) -> None:
    """End-to-end: register v1 → set BACKWARD → POST v2 → read back v2."""
    base = f"http://127.0.0.1:{apicurio_forward.local_port}/apis/registry/v2"

    # Cleanup any leftover from a prior run.
    _delete_artifact(base)

    try:
        # 1. Register v1.
        status, body = _http(
            "POST",
            f"{base}/groups/{GROUP}/artifacts",
            body=V1_SCHEMA,
            headers={
                "Content-Type": "application/json; artifactType=AVRO",
                "X-Registry-ArtifactId": ARTIFACT,
            },
        )
        assert status in (200, 201), f"register v1 failed: {status} {body}"

        # 2. Set BACKWARD compatibility.
        status, body = _http(
            "PUT",
            f"{base}/groups/{GROUP}/artifacts/{ARTIFACT}/rules/COMPATIBILITY",
            body={"type": "COMPATIBILITY", "config": "BACKWARD"},
        )
        assert status in (200, 204), f"set rule failed: {status} {body}"

        # 3. POST v2 (BACKWARD-compatible: only adds an optional field).
        status, body = _http(
            "POST",
            f"{base}/groups/{GROUP}/artifacts/{ARTIFACT}/versions",
            body=V2_SCHEMA_BACKWARD_COMPAT,
            headers={"Content-Type": "application/json"},
        )
        assert status in (200, 201), f"register v2 failed: {status} {body}"

        # 4. Fetch latest, assert label field present.
        status, body = _http("GET", f"{base}/groups/{GROUP}/artifacts/{ARTIFACT}")
        assert status == 200, f"fetch latest failed: {status} {body}"
        assert "label" in body, f"v2 fetched but did not include 'label' field; body:\n{body}"
    finally:
        _delete_artifact(base)


def test_v5_apicurio_system_info_reachable(apicurio_forward) -> None:
    """A no-side-effect health probe — separate test so its failure
    doesn't mask the schema-evolution test's intent."""
    status, body = _http(
        "GET",
        f"http://127.0.0.1:{apicurio_forward.local_port}/apis/registry/v2/system/info",
    )
    assert status == 200, f"system/info returned {status}: {body}"

    parsed = json.loads(body)
    assert "version" in parsed, f"system/info missing 'version': {body}"
