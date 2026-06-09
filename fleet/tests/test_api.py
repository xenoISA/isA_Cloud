"""Tests for the fleet console operator API (ADR 0009 §2/§4, issue #377).

Uses FastAPI ``TestClient`` over an in-memory sqlite session (StaticPool, the same
pattern as ``test_intake.py``) and a real ed25519 keypair (as ``test_issuance.py``).

Covers the issue's required cases:
  - roster -> current rows + derived status (current/expiring/expired/perpetual)
  - expiring -> the renewal-alert window
  - issue -> signs + writes a ledger row (returns the signed license)
  - renew -> supersedes the prior row; roster reflects the successor
  - revoke -> ledger flag; row drops out of the active roster
  - showback -> honest telemetry state (realtime / last-upload / none)
  - the metadata-only guarantee: every roster/showback field is ledger/telemetry
    metadata, and the issue body rejects smuggled business data (extra="forbid")
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from isa_common.license import LicenseConfig, LicenseStatus
from isa_common.license_sign import generate_keypair

from fleet_console import (
    Base,
    DeploymentSecret,
    IssuanceLedger,
    TelemetryRecord,
    create_fleet_api,
)

LICENSE_ENV_VARS = ["ISA_LICENSE_FILE", "ISA_LICENSE_PUBKEY", "ISA_EDITION"]

# Operator bearer token used by the test app (B2, #377). The client fixture sets the
# matching Authorization header so existing behavioral tests exercise the real path.
OPERATOR_TOKEN = "test-operator-token"


@pytest.fixture(autouse=True)
def clean_license_env(monkeypatch):
    for var in LICENSE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    # Ensure no ambient FLEET_API_TOKEN leaks into the env-default auth path.
    monkeypatch.delenv("FLEET_API_TOKEN", raising=False)
    import isa_common.edition as edition_mod

    edition_mod._edition = None
    yield
    edition_mod._edition = None


@pytest.fixture
def keypair():
    private_pem, public_pem = generate_keypair()
    return private_pem, public_pem.decode("utf-8")


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
def session_factory(engine):
    return sessionmaker(bind=engine, class_=Session)


@pytest.fixture
def client(session_factory, keypair):
    priv_pem, _ = keypair
    # Pin the dev key on the app (real ops supplies it per request, ADR 0009 §2).
    # Configure the operator token (B2) and send it by default on every request.
    app = create_fleet_api(
        session_factory, signing_key_pem=priv_pem, operator_token=OPERATOR_TOKEN
    )
    return TestClient(app, headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"})


def _seed_license(session_factory, **overrides):
    now = datetime.now(timezone.utc)
    fields = dict(
        license_id="sn-2026",
        customer_id="SN",
        edition="on-prem-full",
        entitled_modules=["erp", "mes", "commercial_tower"],
        quota_tier="enterprise",
        issued_at=now,
        not_before=now,
        expires_at=now + timedelta(days=365),
        superseded_by=None,
        delivery="offline-bundle",
        deployment_secret_id="dep-sn-1",
    )
    fields.update(overrides)
    with session_factory() as s:
        s.add(IssuanceLedger(**fields))
        s.commit()
    return fields


# --------------------------------------------------------------------------- #
# Roster + derived status
# --------------------------------------------------------------------------- #
def test_roster_returns_current_rows_with_status(client, session_factory):
    now = datetime.now(timezone.utc)
    _seed_license(session_factory, license_id="cur-1", customer_id="A",
                  expires_at=now + timedelta(days=200), deployment_secret_id="d1")
    _seed_license(session_factory, license_id="exp-1", customer_id="B",
                  expires_at=now + timedelta(days=10), deployment_secret_id="d2")
    _seed_license(session_factory, license_id="gone-1", customer_id="C",
                  expires_at=now - timedelta(days=5), deployment_secret_id="d3")
    _seed_license(session_factory, license_id="perp-1", customer_id="D",
                  expires_at=None, deployment_secret_id="d4")

    resp = client.get("/fleet/roster")
    assert resp.status_code == 200, resp.text
    rows = {r["license_id"]: r for r in resp.json()}
    assert rows["cur-1"]["status"] == "current"
    assert rows["exp-1"]["status"] == "expiring"
    assert rows["gone-1"]["status"] == "expired"
    assert rows["perp-1"]["status"] == "perpetual"
    # never-reported -> honest silence enrichment
    assert rows["cur-1"]["last_seen"] is None
    assert rows["cur-1"]["silent"] is True


def test_customer_view_entitlements(client, session_factory):
    _seed_license(session_factory)
    resp = client.get("/fleet/customers/SN")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["customer_id"] == "SN"
    assert body["entitled_modules"] == ["erp", "mes", "commercial_tower"]
    assert len(body["licenses"]) == 1

    assert client.get("/fleet/customers/NOPE").status_code == 404


def test_expiring_window(client, session_factory):
    now = datetime.now(timezone.utc)
    _seed_license(session_factory, license_id="soon", customer_id="A",
                  expires_at=now + timedelta(days=5), deployment_secret_id="d1")
    _seed_license(session_factory, license_id="far", customer_id="B",
                  expires_at=now + timedelta(days=200), deployment_secret_id="d2")
    resp = client.get("/fleet/expiring", params={"within_days": 30})
    assert resp.status_code == 200, resp.text
    ids = [r["license_id"] for r in resp.json()]
    assert ids == ["soon"]


# --------------------------------------------------------------------------- #
# Issue / renew / revoke
# --------------------------------------------------------------------------- #
def test_issue_signs_and_writes_ledger(monkeypatch, tmp_path, client, session_factory, keypair):
    _, pub_pem = keypair
    expires = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    resp = client.post("/fleet/issue", json={
        "license_id": "acme-1",
        "customer_id": "ACME",
        "edition": "saas",
        "entitled_modules": ["erp"],
        "quota_tier": "pro",
        "expires_at": expires,
        "delivery": "saas-direct",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ledger_row"]["license_id"] == "acme-1"
    assert body["ledger_row"]["status"] == "current"
    assert body["deployment_secret_id"]  # non-secret pointer surfaced

    # ledger row persisted
    with session_factory() as s:
        row = s.get(IssuanceLedger, "acme-1")
    assert row is not None and row.customer_id == "ACME"

    # the returned signed license verifies VALID through the real verifier
    signed = body["license"]
    path = tmp_path / "license.json"
    path.write_text(json.dumps(signed))
    monkeypatch.setenv("ISA_LICENSE_FILE", str(path))
    monkeypatch.setenv("ISA_LICENSE_PUBKEY", pub_pem)
    monkeypatch.setenv("ISA_EDITION", signed["edition"])
    cfg = LicenseConfig.from_env()
    assert cfg.status is LicenseStatus.VALID
    assert cfg.customer_id == "ACME"
    assert cfg.is_entitled("erp")


def test_issue_per_request_key(session_factory, keypair):
    # No pinned key on the app: the operator supplies it per request (ADR 0009 §2).
    # Still operator-auth gated (B2): configure + send the token.
    priv_pem, _ = keypair
    app = create_fleet_api(session_factory, operator_token=OPERATOR_TOKEN)  # no key
    cl = TestClient(app, headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"})

    # Without a key -> 400
    r0 = cl.post("/fleet/issue", json={"customer_id": "X", "edition": "saas"})
    assert r0.status_code == 400

    # With a per-request PEM key -> 201
    r1 = cl.post("/fleet/issue", json={
        "customer_id": "X", "edition": "saas",
        "signing_key_pem": priv_pem.decode("utf-8"),
    })
    assert r1.status_code == 201, r1.text


def test_renew_supersedes_prior(client, session_factory):
    _seed_license(session_factory, license_id="sn-2026")
    expires = (datetime.now(timezone.utc) + timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ")
    resp = client.post("/fleet/renew", json={
        "prior_license_id": "sn-2026",
        "license_id": "sn-2027",
        "customer_id": "SN",
        "edition": "on-prem-full",
        "expires_at": expires,
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["ledger_row"]["license_id"] == "sn-2027"

    # roster now shows only the successor
    roster_ids = [r["license_id"] for r in client.get("/fleet/roster").json()]
    assert roster_ids == ["sn-2027"]
    with session_factory() as s:
        assert s.get(IssuanceLedger, "sn-2026").superseded_by == "sn-2027"


def test_revoke_flags_and_drops_from_roster(client, session_factory):
    _seed_license(session_factory, license_id="sn-2026")
    resp = client.post("/fleet/revoke", json={
        "license_id": "sn-2026", "reason": "contract terminated",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "revoked"
    assert body["revoked_reason"] == "contract terminated"
    assert body["revoked_at"] is not None

    # revoked row excluded from the active roster
    assert client.get("/fleet/roster").json() == []
    # still retained (audit) — visible via include_superseded
    full = client.get("/fleet/roster", params={"include_superseded": True}).json()
    assert [r["license_id"] for r in full] == ["sn-2026"]

    # double-revoke rejected
    assert client.post("/fleet/revoke", json={"license_id": "sn-2026"}).status_code == 400


# --------------------------------------------------------------------------- #
# Showback rollup — honest telemetry state (ADR 0009 §4)
# --------------------------------------------------------------------------- #
def _add_telemetry(session_factory, license_id, secret_id, **overrides):
    fields = dict(
        license_id=license_id,
        deployment_secret_id=secret_id,
        last_seen=datetime.now(timezone.utc),
        received_at=datetime.now(timezone.utc),
        source="realtime",
        active_edition="on-prem-full",
        active_modules=["erp", "mes"],
        module_usage={"erp": 1200, "mes": 340},
        showback_totals={"requests": 50000, "seats": 12},
        over_license=False,
    )
    fields.update(overrides)
    with session_factory() as s:
        s.add(TelemetryRecord(**fields))
        s.commit()


def test_showback_honest_states(client, session_factory):
    # A: reports realtime; B: never reports (silent / air-gapped)
    _seed_license(session_factory, license_id="a-1", customer_id="A", deployment_secret_id="da")
    _seed_license(session_factory, license_id="b-1", customer_id="B", deployment_secret_id="db")
    _add_telemetry(session_factory, "a-1", "da", source="realtime")

    resp = client.get("/fleet/showback")
    assert resp.status_code == 200, resp.text
    rows = {r["license_id"]: r for r in resp.json()}

    assert rows["a-1"]["telemetry_state"] == "realtime"
    assert rows["a-1"]["module_usage"] == {"erp": 1200, "mes": 340}
    assert rows["a-1"]["showback_totals"] == {"requests": 50000, "seats": 12}
    assert rows["a-1"]["over_license"] is False

    # honest silence — never fabricated
    assert rows["b-1"]["telemetry_state"] == "none"
    assert rows["b-1"]["last_seen"] is None
    assert "no telemetry" in rows["b-1"]["note"]
    assert rows["b-1"]["module_usage"] == {}


def test_showback_last_upload_for_offline(client, session_factory):
    _seed_license(session_factory, license_id="o-1", customer_id="O", deployment_secret_id="do")
    _add_telemetry(session_factory, "o-1", "do", source="offline-upload")
    rows = {r["license_id"]: r for r in client.get("/fleet/showback").json()}
    assert rows["o-1"]["telemetry_state"] == "last-upload"
    assert rows["o-1"]["source"] == "offline-upload"


def test_showback_staleness_is_honest(client, session_factory):
    _seed_license(session_factory, license_id="s-1", customer_id="S", deployment_secret_id="ds")
    old = datetime.now(timezone.utc) - timedelta(days=45)
    _add_telemetry(session_factory, "s-1", "ds", last_seen=old, source="realtime")
    rows = {r["license_id"]: r for r in
            client.get("/fleet/showback", params={"silent_after_days": 30}).json()}
    # past the staleness threshold -> honestly "none", with a "no telemetry since X" note
    assert rows["s-1"]["telemetry_state"] == "none"
    assert "no telemetry since" in rows["s-1"]["note"]


# --------------------------------------------------------------------------- #
# Metadata-only guarantee (ADR 0009 §5)
# --------------------------------------------------------------------------- #
def test_issue_body_rejects_smuggled_business_data(client):
    # extra="forbid" — any field outside the metadata schema is rejected (422).
    resp = client.post("/fleet/issue", json={
        "customer_id": "X", "edition": "saas",
        "customer_email": "alice@example.com",  # smuggled PII
        "orders": [{"sku": "A", "qty": 3}],      # smuggled business data
    })
    assert resp.status_code == 422, resp.text


def test_responses_contain_only_metadata_fields(client, session_factory):
    _seed_license(session_factory, license_id="sn-2026")
    _add_telemetry(session_factory, "sn-2026", "dep-sn-1")

    allowed_roster = {
        "license_id", "customer_id", "edition", "entitled_modules", "quota_tier",
        "issued_at", "not_before", "expires_at", "delivery", "deployment_secret_id",
        "status", "revoked_at", "revoked_reason", "last_seen", "silent",
    }
    for r in client.get("/fleet/roster").json():
        assert set(r.keys()) <= allowed_roster

    allowed_showback = {
        "customer_id", "license_id", "edition", "telemetry_state", "last_seen",
        "source", "active_edition", "active_modules", "module_usage",
        "showback_totals", "over_license", "note",
    }
    for r in client.get("/fleet/showback").json():
        assert set(r.keys()) <= allowed_showback


# --------------------------------------------------------------------------- #
# Operator auth — fail-closed bearer token on the whole router (B2, #377)
# --------------------------------------------------------------------------- #
def test_missing_or_invalid_token_rejected(session_factory, keypair):
    """Configured token but missing/wrong request token -> 401 (read AND write)."""
    priv_pem, _ = keypair
    app = create_fleet_api(
        session_factory, signing_key_pem=priv_pem, operator_token=OPERATOR_TOKEN
    )
    cl = TestClient(app)  # no Authorization header

    # Missing token -> 401 on a read route...
    assert cl.get("/fleet/roster").status_code == 401
    # ...and on a write/mint route (the issuance oracle stays closed).
    assert cl.post("/fleet/issue", json={"customer_id": "X", "edition": "saas"}).status_code == 401

    # Wrong token -> 401.
    bad = {"Authorization": "Bearer not-the-token"}
    assert cl.get("/fleet/roster", headers=bad).status_code == 401

    # Correct token via Authorization: Bearer -> allowed (200).
    ok = {"Authorization": f"Bearer {OPERATOR_TOKEN}"}
    assert cl.get("/fleet/roster", headers=ok).status_code == 200

    # X-Fleet-Token header is also accepted.
    assert cl.get("/fleet/roster", headers={"X-Fleet-Token": OPERATOR_TOKEN}).status_code == 200

    # healthz stays open (liveness, unauthenticated).
    assert cl.get("/healthz").status_code == 200


def test_unconfigured_token_fails_closed_503(session_factory):
    """No operator token configured -> every /fleet route refuses with 503."""
    # Explicit None (not the env-default sentinel) => unconfigured. No signing key
    # pinned so the router still builds; auth itself must fail closed.
    app = create_fleet_api(session_factory, operator_token=None)
    cl = TestClient(app)

    # Even WITH a (meaningless) bearer header, an unconfigured app serves nothing.
    hdr = {"Authorization": "Bearer anything"}
    r = cl.get("/fleet/roster", headers=hdr)
    assert r.status_code == 503, r.text
    assert "not configured" in r.json()["detail"]
    # write route equally closed
    assert cl.post("/fleet/issue", json={"customer_id": "X", "edition": "saas"},
                   headers=hdr).status_code == 503


def test_pinned_key_without_token_refuses(session_factory, keypair):
    """A pinned signing key with no operator token is refused at construction.

    A hot signing key behind no auth is the worst case (unauthenticated minting),
    so create_fleet_api must refuse to build rather than expose it.
    """
    priv_pem, _ = keypair
    with pytest.raises(RuntimeError):
        create_fleet_api(session_factory, signing_key_pem=priv_pem, operator_token=None)


def test_token_defaults_from_env(session_factory, monkeypatch):
    """Unpassed operator_token defaults to FLEET_API_TOKEN (env), still gated."""
    monkeypatch.setenv("FLEET_API_TOKEN", "env-token")
    app = create_fleet_api(session_factory)  # no operator_token kwarg -> env default
    cl = TestClient(app)
    assert cl.get("/fleet/roster").status_code == 401  # gated, needs the env token
    assert cl.get("/fleet/roster",
                  headers={"Authorization": "Bearer env-token"}).status_code == 200
