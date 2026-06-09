"""Tests for the per-deployment telemetry credential (ADR 0009 §3, issue #374).

In-memory sqlite + a real ed25519 keypair (same harness as #373's test_issuance).

Covers:
  - issuing mints a credential AND populates IssuanceLedger.deployment_secret_id
  - the secret is retrievable for verification (get_secret / secret_for_license)
  - verify_telemetry_hmac accepts a correctly-signed payload and rejects a
    tampered payload, a tampered signature, a wrong secret, and an unknown id
  - the HMAC scheme is HMAC-SHA256 / lowercase-hex over the raw payload bytes
  - renewal rotates the credential (new id + new secret on the new lineage row)
  - explicit rotate_credential mints a new secret without touching the license
  - the deployment_secret SQL migration is valid DDL
"""

import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from isa_common.license_sign import generate_keypair

from fleet_console import (
    Base,
    DeploymentSecret,
    IssuanceLedger,
    IssuanceRequest,
    IssuanceService,
    get_secret,
    mint_credential,
    rotate_credential,
    secret_for_license,
    sign_telemetry,
    verify_telemetry_hmac,
)

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "0002_deployment_secret.sql"
)


@pytest.fixture
def keypair():
    private_pem, public_pem = generate_keypair()
    return private_pem, public_pem.decode("utf-8")


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


# --------------------------------------------------------------------------- #
# Issuance mints + persists the credential, populates the ledger pointer
# --------------------------------------------------------------------------- #
def test_issue_mints_credential_and_populates_ledger(session, keypair):
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)
    result = svc.issue(IssuanceRequest(customer_id="SN", edition="on-prem-full"))

    cred = result.credential
    # id is the short, stable, dep-<customer>-<rand> shape and non-secret.
    assert cred.deployment_secret_id.startswith("dep-sn-")
    assert cred.secret  # random HMAC key returned for the secret bundle
    assert len(cred.secret) >= 32

    # ledger row carries the pointer (was NULL pre-#374).
    row = session.get(IssuanceLedger, result.ledger_row.license_id)
    assert row.deployment_secret_id == cred.deployment_secret_id

    # secret persisted to the isolated table, retrievable for verification.
    stored = get_secret(session, cred.deployment_secret_id)
    assert stored == cred.secret
    assert secret_for_license(session, row.license_id) == cred.secret

    # the secret lives in its OWN table, not on the ledger row.
    secret_rows = list(session.scalars(select(DeploymentSecret)).all())
    assert len(secret_rows) == 1
    assert secret_rows[0].customer_id == "SN"


def test_each_issuance_gets_a_distinct_credential(session, keypair):
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)
    a = svc.issue(IssuanceRequest(license_id="a-1", customer_id="A", edition="saas"))
    b = svc.issue(IssuanceRequest(license_id="a-2", customer_id="A", edition="saas"))
    assert a.credential.deployment_secret_id != b.credential.deployment_secret_id
    assert a.credential.secret != b.credential.secret


# --------------------------------------------------------------------------- #
# verify_telemetry_hmac: accept correct, reject tampered / wrong / unknown
# --------------------------------------------------------------------------- #
def test_verify_accepts_correctly_signed_payload(session, keypair):
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)
    cred = svc.issue(IssuanceRequest(customer_id="SN", edition="on-prem-full")).credential

    payload = b'{"license_id":"sn-2026","last_seen":"2026-06-08T00:00:00Z"}'
    sig = sign_telemetry(cred.secret, payload)
    assert verify_telemetry_hmac(session, cred.deployment_secret_id, payload, sig) is True


def test_verify_rejects_tampered_payload(session, keypair):
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)
    cred = svc.issue(IssuanceRequest(customer_id="SN", edition="on-prem-full")).credential

    payload = b'{"over_license":false}'
    sig = sign_telemetry(cred.secret, payload)
    tampered = b'{"over_license":true}'
    assert verify_telemetry_hmac(session, cred.deployment_secret_id, tampered, sig) is False


def test_verify_rejects_tampered_signature(session, keypair):
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)
    cred = svc.issue(IssuanceRequest(customer_id="SN", edition="on-prem-full")).credential

    payload = b"usage-bundle-bytes"
    sig = sign_telemetry(cred.secret, payload)
    bad = ("0" if sig[0] != "0" else "1") + sig[1:]  # flip first hex nibble
    assert verify_telemetry_hmac(session, cred.deployment_secret_id, payload, bad) is False
    # empty / None signatures are rejected too
    assert verify_telemetry_hmac(session, cred.deployment_secret_id, payload, "") is False


def test_verify_rejects_wrong_secret(session, keypair):
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)
    cred = svc.issue(IssuanceRequest(customer_id="SN", edition="on-prem-full")).credential

    payload = b"metadata"
    wrong = mint_credential("SN").secret  # a different random secret
    sig = sign_telemetry(wrong, payload)
    assert verify_telemetry_hmac(session, cred.deployment_secret_id, payload, sig) is False


def test_verify_rejects_unknown_secret_id(session):
    assert verify_telemetry_hmac(session, "dep-nope-deadbeef", b"x", "abc") is False


def test_hmac_scheme_is_sha256_hex_over_raw_bytes(session, keypair):
    """Pin the exact scheme #375/#376 must implement: HMAC-SHA256, hex, raw bytes."""
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)
    cred = svc.issue(IssuanceRequest(customer_id="SN", edition="on-prem-full")).credential

    payload = b"\x00\x01rawbytes\xff"
    expected = hmac.new(cred.secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert sign_telemetry(cred.secret, payload) == expected
    assert re.fullmatch(r"[0-9a-f]{64}", expected)  # 256-bit lowercase hex
    assert verify_telemetry_hmac(session, cred.deployment_secret_id, payload, expected)


# --------------------------------------------------------------------------- #
# Rotation: renewal rotates the credential; explicit rotate_credential
# --------------------------------------------------------------------------- #
def test_renewal_rotates_credential(session, keypair):
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)
    first = svc.issue(
        IssuanceRequest(license_id="sn-2026", customer_id="SN", edition="on-prem-full")
    )
    second = svc.renew(
        "sn-2026",
        IssuanceRequest(license_id="sn-2027", customer_id="SN", edition="on-prem-full"),
    )

    # new lineage row has a fresh id + secret
    assert second.credential.deployment_secret_id != first.credential.deployment_secret_id
    assert second.credential.secret != first.credential.secret
    assert session.get(IssuanceLedger, "sn-2027").deployment_secret_id == (
        second.credential.deployment_secret_id
    )

    # telemetry signed with the NEW secret verifies under the new id; old secret does not
    payload = b"renewed-usage"
    sig_new = sign_telemetry(second.credential.secret, payload)
    assert verify_telemetry_hmac(
        session, second.credential.deployment_secret_id, payload, sig_new
    )
    sig_old = sign_telemetry(first.credential.secret, payload)
    assert not verify_telemetry_hmac(
        session, second.credential.deployment_secret_id, payload, sig_old
    )


def test_explicit_rotate_credential_replaces_secret_for_leak(session, keypair):
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)
    issued = svc.issue(
        IssuanceRequest(license_id="acme-1", customer_id="ACME", edition="saas")
    )
    old_id = issued.credential.deployment_secret_id

    # simulate a leak: rotate the secret, delete the old, repoint the ledger row.
    new_cred = rotate_credential(
        session,
        customer_id="ACME",
        license_id="acme-1",
        old_deployment_secret_id=old_id,
    )
    led = session.get(IssuanceLedger, "acme-1")
    led.deployment_secret_id = new_cred.deployment_secret_id
    session.commit()

    # old secret is gone; new one verifies. The LICENSE is untouched (rotation
    # never needs the ed25519 key — blast radius is telemetry only).
    assert get_secret(session, old_id) is None
    payload = b"post-rotation"
    sig = sign_telemetry(new_cred.secret, payload)
    assert verify_telemetry_hmac(
        session, new_cred.deployment_secret_id, payload, sig
    )
    assert secret_for_license(session, "acme-1") == new_cred.secret


# --------------------------------------------------------------------------- #
# The deployment_secret SQL migration is valid DDL
# --------------------------------------------------------------------------- #
def test_secret_sql_migration_is_valid_ddl():
    raw = MIGRATION.read_text()
    assert "CREATE TABLE" in raw and "deployment_secret" in raw

    no_comments = "\n".join(re.sub(r"--.*$", "", ln) for ln in raw.splitlines())
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for stmt in (s.strip() for s in no_comments.split(";")):
            if stmt:
                conn.execute(text(stmt))
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(deployment_secret)"))}
    assert {"deployment_secret_id", "secret", "customer_id", "license_id"} <= cols
