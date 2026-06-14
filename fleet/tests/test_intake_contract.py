"""Producer -> intake CONTRACT test (B1, #375 / #376).

The existing per-side tests each verify their OWN serialization, so they passed
even while the air-gapped upload was 100% broken (BLOCKER B1): the producer
signs the CANONICAL payload bytes and ships a ``{payload, deployment_secret_id,
signature}`` envelope, but intake used to MAC the whole raw file and read the
signature from a header.

This test closes that gap from the intake side. It REPLICATES the deployment-side
producer's EXACT envelope format (``microservices/telemetry_service/usage_bundle.py``,
read but NOT imported — different repo) and POSTs it to BOTH intake endpoints:

  - signed bytes  = ``json.dumps(payload, sort_keys=True, separators=(",",":")).encode()``
  - signature     = ``sign_telemetry(secret, signed_bytes)``  (HMAC-SHA256, hex)
  - envelope file = ``json.dump({payload, deployment_secret_id, signature},
                       indent=2, sort_keys=True)``  (the producer's on-disk shape)

Asserts the contract holds end-to-end:
  - both /telemetry and /telemetry/upload accept it -> 201 + a persisted row;
  - tampering the payload after signing               -> 401 (MAC mismatch);
  - an extra field smuggled into the payload          -> 422 (metadata-only guard).
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from fleet_console import (
    Base,
    DeploymentSecret,
    IssuanceLedger,
    TelemetryRecord,
    create_intake_app,
    sign_telemetry,
)

DEPLOYMENT_SECRET_ID = "dep-sn-7f3a"
SECRET = "super-secret-hmac-key"
LICENSE_ID = "sn-prod-2026"


# --------------------------------------------------------------------------- #
# Replicate the #376 producer's exact wire format (NOT imported cross-repo).
# Mirrors usage_bundle.py: canonical_payload_bytes() + json.dump(..., indent=2,
# sort_keys=True). These two helpers ARE the producer contract, restated here.
# --------------------------------------------------------------------------- #
def _producer_canonical_bytes(payload: dict) -> bytes:
    """== usage_bundle.canonical_payload_bytes(): sorted keys, no whitespace."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _producer_envelope_file(payload: dict, *, secret: str, secret_id: str) -> bytes:
    """== usage_bundle.export_bundle()'s on-disk file: signed canonical bytes wrapped
    in ``{payload, deployment_secret_id, signature}`` via json.dump(indent=2, sort_keys=True).
    """
    signature = sign_telemetry(secret, _producer_canonical_bytes(payload))
    bundle = {
        "payload": payload,
        "deployment_secret_id": secret_id,
        "signature": signature,
    }
    # json.dump(..., indent=2, sort_keys=True) — exactly the producer's file write.
    return (json.dumps(bundle, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _producer_payload(**overrides) -> dict:
    """A payload shaped EXACTLY like the producer's UsageBundlePayload.model_dump():
    last_seen is an ISO string, module_usage is dict[str,int], etc. (all JSON-native).
    """
    base = {
        "license_id": LICENSE_ID,
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "active_edition": "on-prem-full",
        "active_modules": ["erp", "mes"],
        "module_usage": {"erp": 1200, "mes": 340},
        "showback_totals": {"requests": 50000.0, "seats": 12.0},
        "over_license": False,
    }
    base.update(overrides)
    return base


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def seeded(engine):
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
                deployment_secret_id=DEPLOYMENT_SECRET_ID,
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
def client(seeded):
    return TestClient(create_intake_app(sessionmaker(bind=seeded, class_=Session)))


# --------------------------------------------------------------------------- #
# Confirm our replica matches the documented producer formula (self-check).
# --------------------------------------------------------------------------- #
def test_canonical_bytes_formula_matches_producer():
    payload = {"b": 2, "a": 1, "nested": {"y": 1, "x": 2}}
    assert (
        _producer_canonical_bytes(payload)
        == b'{"a":1,"b":2,"nested":{"x":2,"y":1}}'
    )


# --------------------------------------------------------------------------- #
# The real contract: producer file -> BOTH intake endpoints -> 201 + persisted.
# --------------------------------------------------------------------------- #
def test_producer_envelope_accepted_by_post(client, seeded):
    raw = _producer_envelope_file(
        _producer_payload(), secret=SECRET, secret_id=DEPLOYMENT_SECRET_ID
    )
    resp = client.post("/telemetry", content=raw)
    assert resp.status_code == 201, resp.text
    assert resp.json()["source"] == "realtime"
    with Session(seeded) as s:
        rec = s.scalars(select(TelemetryRecord)).one()
    assert rec.license_id == LICENSE_ID
    assert rec.deployment_secret_id == DEPLOYMENT_SECRET_ID
    assert rec.module_usage == {"erp": 1200, "mes": 340}


def test_producer_envelope_accepted_by_upload(client, seeded):
    # The air-gapped tier: hand-carry the file alone, no headers.
    raw = _producer_envelope_file(
        _producer_payload(), secret=SECRET, secret_id=DEPLOYMENT_SECRET_ID
    )
    resp = client.post(
        "/telemetry/upload",
        files={"file": ("usage_bundle.json", raw, "application/json")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["source"] == "offline-upload"
    with Session(seeded) as s:
        rec = s.scalars(select(TelemetryRecord)).one()
    assert rec.license_id == LICENSE_ID
    assert rec.source == "offline-upload"


def test_tampered_payload_after_signing_rejected_401(client, seeded):
    # Sign the real payload, then mutate the envelope's payload -> MAC mismatch -> 401.
    payload = _producer_payload()
    signature = sign_telemetry(SECRET, _producer_canonical_bytes(payload))
    payload["over_license"] = True  # tamper AFTER signing
    raw = (
        json.dumps(
            {
                "payload": payload,
                "deployment_secret_id": DEPLOYMENT_SECRET_ID,
                "signature": signature,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")

    assert client.post("/telemetry", content=raw).status_code == 401
    assert (
        client.post(
            "/telemetry/upload",
            files={"file": ("usage_bundle.json", raw, "application/json")},
        ).status_code
        == 401
    )
    with Session(seeded) as s:
        assert s.scalars(select(TelemetryRecord)).all() == []


def test_extra_field_in_payload_rejected_422(client, seeded):
    # HMAC is VALID over the extra-bearing payload; intake still rejects on the
    # strict metadata-only schema (extra="forbid") AFTER auth -> 422.
    payload = _producer_payload()
    payload["customer_pii"] = "alice@example.com"
    raw = _producer_envelope_file(payload, secret=SECRET, secret_id=DEPLOYMENT_SECRET_ID)

    assert client.post("/telemetry", content=raw).status_code == 422
    assert (
        client.post(
            "/telemetry/upload",
            files={"file": ("usage_bundle.json", raw, "application/json")},
        ).status_code
        == 422
    )
    with Session(seeded) as s:
        assert s.scalars(select(TelemetryRecord)).all() == []
