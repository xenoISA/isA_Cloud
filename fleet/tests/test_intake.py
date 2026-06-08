"""Tests for the telemetry intake endpoint (ADR 0009 §3, issue #375).

Uses FastAPI ``TestClient`` over an in-memory sqlite session and a real
HMAC-SHA256 signature (the #374 contract, exercised through the canonical
DB-backed ``verify_telemetry_hmac(session, ...)`` against a seeded
``deployment_secret`` row — same pattern as ``test_telemetry_credential.py``).

Covers the issue's required cases:
  - valid HMAC + valid metadata payload  -> 201, persists a telemetry_record
  - bad / missing HMAC                    -> 401, nothing persisted
  - unknown / extra field (smuggled data) -> 422, rejected (metadata-only guard)
  - file-upload path persists IDENTICALLY (offline air-gapped tier)
  - last_seen / honest-silence query reports "no telemetry since X"
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from fleet_console import (
    Base,
    DeploymentSecret,
    IssuanceLedger,
    TelemetryRecord,
    create_intake_app,
    last_seen_per_deployment,
    sign_telemetry,
)

DEPLOYMENT_SECRET_ID = "dep-sn-7f3a"
SECRET = "super-secret-hmac-key"
LICENSE_ID = "sn-prod-2026"


@pytest.fixture
def engine():
    """Shared in-memory sqlite engine (StaticPool so every connection sees one DB)."""
    from sqlalchemy.pool import StaticPool

    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def seeded_ledger(engine):
    """Seed one current ledger row + its per-deployment secret (#374 store).

    The secret is persisted into the isolated ``deployment_secret`` table that the
    canonical ``verify_telemetry_hmac(session, ...)`` looks up — no env stub.
    """
    with Session(engine) as s:
        s.add(
            IssuanceLedger(
                license_id=LICENSE_ID,
                customer_id="SN",
                edition="on-prem-full",
                entitled_modules=["erp", "mes"],
                quota_tier="enterprise",
                issued_at=datetime.now(timezone.utc),
                not_before=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=365),
                superseded_by=None,
                delivery="offline-bundle",
                deployment_secret_id=DEPLOYMENT_SECRET_ID,  # pin the credential
            )
        )
        s.add(
            DeploymentSecret(
                deployment_secret_id=DEPLOYMENT_SECRET_ID,
                secret=SECRET,
                customer_id="SN",
                license_id=LICENSE_ID,
            )
        )
        s.commit()
    return engine


@pytest.fixture
def client(seeded_ledger):
    session_factory = sessionmaker(bind=seeded_ledger, class_=Session)
    app = create_intake_app(session_factory)
    return TestClient(app)


def _payload(**overrides) -> dict:
    base = {
        "license_id": LICENSE_ID,
        "last_seen": "2026-06-08T12:00:00Z",
        "active_edition": "on-prem-full",
        "active_modules": ["erp", "mes"],
        "module_usage": {"erp": 1200, "mes": 340},
        "showback_totals": {"requests": 50000, "seats": 12},
        "over_license": False,
    }
    base.update(overrides)
    return base


def _signed_headers(raw: bytes, *, secret: str = SECRET, secret_id: str = DEPLOYMENT_SECRET_ID):
    return {
        "X-Deployment-Secret-Id": secret_id,
        "X-Telemetry-Signature": sign_telemetry(secret, raw),
    }


# --------------------------------------------------------------------------- #
# valid HMAC + valid metadata -> 201 + persists
# --------------------------------------------------------------------------- #
def test_post_valid_hmac_and_metadata_persists(client, seeded_ledger):
    raw = json.dumps(_payload()).encode()
    resp = client.post("/telemetry", content=raw, headers=_signed_headers(raw))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["license_id"] == LICENSE_ID
    assert body["source"] == "realtime"

    with Session(seeded_ledger) as s:
        rows = list(s.scalars(select(TelemetryRecord)).all())
    assert len(rows) == 1
    rec = rows[0]
    assert rec.license_id == LICENSE_ID
    assert rec.deployment_secret_id == DEPLOYMENT_SECRET_ID
    assert rec.active_modules == ["erp", "mes"]
    assert rec.module_usage == {"erp": 1200, "mes": 340}
    assert rec.showback_totals == {"requests": 50000, "seats": 12}
    assert rec.over_license is False
    assert rec.source == "realtime"


def test_over_license_flag_persisted(client, seeded_ledger):
    raw = json.dumps(_payload(over_license=True)).encode()
    resp = client.post("/telemetry", content=raw, headers=_signed_headers(raw))
    assert resp.status_code == 201, resp.text
    with Session(seeded_ledger) as s:
        rec = s.scalars(select(TelemetryRecord)).one()
    assert rec.over_license is True


# --------------------------------------------------------------------------- #
# bad / missing HMAC -> 401, nothing persisted
# --------------------------------------------------------------------------- #
def test_bad_hmac_rejected_401(client, seeded_ledger):
    raw = json.dumps(_payload()).encode()
    headers = {
        "X-Deployment-Secret-Id": DEPLOYMENT_SECRET_ID,
        "X-Telemetry-Signature": "deadbeef",  # wrong signature
    }
    resp = client.post("/telemetry", content=raw, headers=headers)
    assert resp.status_code == 401
    with Session(seeded_ledger) as s:
        assert s.scalars(select(TelemetryRecord)).all() == []


def test_missing_hmac_rejected_401(client, seeded_ledger):
    raw = json.dumps(_payload()).encode()
    resp = client.post("/telemetry", content=raw)  # no auth headers
    assert resp.status_code == 401
    with Session(seeded_ledger) as s:
        assert s.scalars(select(TelemetryRecord)).all() == []


def test_unknown_secret_id_rejected_401(client, seeded_ledger):
    raw = json.dumps(_payload()).encode()
    headers = _signed_headers(raw, secret_id="dep-unknown")
    resp = client.post("/telemetry", content=raw, headers=headers)
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# unknown / extra field -> 422 (metadata-only guard, ADR 0009 §5)
# --------------------------------------------------------------------------- #
def test_extra_field_rejected_422(client, seeded_ledger):
    # HMAC is VALID — the rejection is purely the strict schema (extra="forbid").
    payload = _payload()
    payload["customer_email"] = "alice@example.com"  # smuggled PII
    raw = json.dumps(payload).encode()
    resp = client.post("/telemetry", content=raw, headers=_signed_headers(raw))
    assert resp.status_code == 422, resp.text
    with Session(seeded_ledger) as s:
        assert s.scalars(select(TelemetryRecord)).all() == []


def test_missing_required_field_rejected_422(client):
    payload = _payload()
    del payload["license_id"]
    raw = json.dumps(payload).encode()
    resp = client.post("/telemetry", content=raw, headers=_signed_headers(raw))
    assert resp.status_code == 422


def test_unknown_license_id_404(client):
    raw = json.dumps(_payload(license_id="does-not-exist")).encode()
    resp = client.post("/telemetry", content=raw, headers=_signed_headers(raw))
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# file-upload path persists IDENTICALLY (offline air-gapped tier)
# --------------------------------------------------------------------------- #
def test_file_upload_path_persists_identically(client, seeded_ledger):
    raw = json.dumps(_payload()).encode()
    headers = _signed_headers(raw)  # SAME HMAC over the SAME raw bytes
    resp = client.post(
        "/telemetry/upload",
        files={"file": ("usage_bundle.json", raw, "application/json")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["source"] == "offline-upload"

    with Session(seeded_ledger) as s:
        rec = s.scalars(select(TelemetryRecord)).one()
    assert rec.license_id == LICENSE_ID
    assert rec.module_usage == {"erp": 1200, "mes": 340}
    assert rec.source == "offline-upload"


def test_file_upload_bad_hmac_rejected_401(client, seeded_ledger):
    raw = json.dumps(_payload()).encode()
    resp = client.post(
        "/telemetry/upload",
        files={"file": ("usage_bundle.json", raw, "application/json")},
        headers={
            "X-Deployment-Secret-Id": DEPLOYMENT_SECRET_ID,
            "X-Telemetry-Signature": "deadbeef",
        },
    )
    assert resp.status_code == 401
    with Session(seeded_ledger) as s:
        assert s.scalars(select(TelemetryRecord)).all() == []


def test_file_upload_extra_field_rejected_422(client):
    payload = _payload()
    payload["secret_business_data"] = {"orders": 42}
    raw = json.dumps(payload).encode()
    resp = client.post(
        "/telemetry/upload",
        files={"file": ("usage_bundle.json", raw, "application/json")},
        headers=_signed_headers(raw),
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# last_seen / honest-silence query (ADR 0009 §4)
# --------------------------------------------------------------------------- #
def test_silence_query_reports_no_telemetry(client, seeded_ledger):
    # A second current license that NEVER reports — must show as silent/None.
    with Session(seeded_ledger) as s:
        s.add(
            IssuanceLedger(
                license_id="acme-2026",
                customer_id="ACME",
                edition="saas",
                entitled_modules=[],
                issued_at=datetime.now(timezone.utc),
                not_before=datetime.now(timezone.utc),
                superseded_by=None,
                deployment_secret_id="dep-acme",
            )
        )
        s.commit()

    # SN reports; ACME stays silent.
    raw = json.dumps(_payload()).encode()
    assert client.post("/telemetry", content=raw, headers=_signed_headers(raw)).status_code == 201

    with Session(seeded_ledger) as s:
        statuses = {d.license_id: d for d in last_seen_per_deployment(s)}

    assert statuses[LICENSE_ID].last_seen is not None
    assert statuses[LICENSE_ID].silent is False
    # Never reported -> honest "no telemetry"
    assert statuses["acme-2026"].last_seen is None
    assert statuses["acme-2026"].silent is True


def test_silence_query_staleness_threshold(client, seeded_ledger):
    # Report with an OLD last_seen, then assert it is flagged silent past threshold.
    old = (datetime.now(timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw = json.dumps(_payload(last_seen=old)).encode()
    assert client.post("/telemetry", content=raw, headers=_signed_headers(raw)).status_code == 201

    with Session(seeded_ledger) as s:
        statuses = {d.license_id: d for d in last_seen_per_deployment(s, silent_after_days=30)}
    assert statuses[LICENSE_ID].last_seen is not None
    assert statuses[LICENSE_ID].silent is True  # 45d old > 30d threshold
