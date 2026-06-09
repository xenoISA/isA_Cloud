"""Tests for the fleet license-issuance ledger + workflow (ADR 0009, issue #373).

Uses an in-memory sqlite SQLAlchemy engine (no live Postgres) and a real ed25519
keypair. Headline contract: a license issued through the workflow (a) writes a
ledger row AND (b) verifies VALID through isa_common.license — the same round-trip
contract the signer (#366) guarantees, here proven through the fleet workflow.

Covers:
  - issue -> ledger row + VALID signed license (round-trip through isa_common.license)
  - renewal sets superseded_by on the prior row
  - roster excludes superseded rows
  - by_customer + expiring_soon filters
  - the SQL migration is valid DDL (applied against sqlite)
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from isa_common.license import LicenseConfig, LicenseStatus
from isa_common.license_sign import generate_keypair

from fleet_console import (
    Base,
    IssuanceRequest,
    IssuanceService,
    IssuanceLedger,
    by_customer,
    expiring_soon,
    roster,
)

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "0001_issuance_ledger.sql"

LICENSE_ENV_VARS = ["ISA_LICENSE_FILE", "ISA_LICENSE_PUBKEY", "ISA_EDITION"]


@pytest.fixture(autouse=True)
def clean_license_env(monkeypatch):
    for var in LICENSE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    import isa_common.edition as edition_mod

    edition_mod._edition = None
    yield
    edition_mod._edition = None


@pytest.fixture
def keypair():
    """A real ed25519 keypair: (private_pem_bytes, public_pem_str)."""
    private_pem, public_pem = generate_keypair()
    return private_pem, public_pem.decode("utf-8")


@pytest.fixture
def session():
    """In-memory sqlite session with the ledger schema created from the ORM."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _verify(monkeypatch, tmp_path, signed: dict, pub_pem: str) -> LicenseConfig:
    """Write the signed license to disk and load it back through isa_common.license."""
    import json

    path = tmp_path / "license.json"
    path.write_text(json.dumps(signed))
    monkeypatch.setenv("ISA_LICENSE_FILE", str(path))
    monkeypatch.setenv("ISA_LICENSE_PUBKEY", pub_pem)
    monkeypatch.setenv("ISA_EDITION", signed["edition"])
    return LicenseConfig.from_env()


# --------------------------------------------------------------------------- #
# Issue -> ledger row + VALID signed license
# --------------------------------------------------------------------------- #
def test_issue_writes_row_and_signs_valid_license(monkeypatch, tmp_path, session, keypair):
    priv_pem, pub_pem = keypair
    expires = datetime.now(timezone.utc) + timedelta(days=365)

    svc = IssuanceService(session, priv_pem)
    result = svc.issue(
        IssuanceRequest(
            customer_id="SN",
            edition="on-prem-full",
            entitled_modules=["erp", "mes", "commercial_tower"],
            quota_tier="enterprise",
            expires_at=expires,
            grace_days=30,
            seats=-1,
            delivery="offline-bundle",
        )
    )

    # (b) ledger row persisted
    rows = list(session.scalars(__import__("sqlalchemy").select(IssuanceLedger)).all())
    assert len(rows) == 1
    row = rows[0]
    assert row.customer_id == "SN"
    assert row.edition == "on-prem-full"
    assert row.entitled_modules == ["erp", "mes", "commercial_tower"]
    assert row.quota_tier == "enterprise"
    assert row.delivery == "offline-bundle"
    assert row.superseded_by is None
    # #374: deployment_secret_id is now populated at issuance (was NULL pre-#374).
    assert row.deployment_secret_id is not None
    assert row.deployment_secret_id == result.credential.deployment_secret_id
    assert row.license_id == result.ledger_row.license_id

    # (a) signed artifact verifies VALID through the real verifier
    cfg = _verify(monkeypatch, tmp_path, result.license, pub_pem)
    assert cfg.status is LicenseStatus.VALID
    assert cfg.customer_id == "SN"
    assert cfg.is_entitled("commercial_tower")
    assert not cfg.is_entitled("plm")


def test_issue_default_license_id_and_no_expiry(session, keypair):
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)
    result = svc.issue(IssuanceRequest(customer_id="ACME", edition="saas"))
    # default license_id = <customer>-<date>
    assert result.ledger_row.license_id.startswith("ACME-")
    assert result.ledger_row.expires_at is None  # no expiry given


# --------------------------------------------------------------------------- #
# Renewal sets superseded_by; roster excludes superseded
# --------------------------------------------------------------------------- #
def test_renewal_sets_superseded_by_and_roster_excludes_prior(session, keypair):
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)

    first = svc.issue(
        IssuanceRequest(
            license_id="sn-2026",
            customer_id="SN",
            edition="on-prem-full",
            expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        )
    )
    second = svc.renew(
        "sn-2026",
        IssuanceRequest(
            license_id="sn-2027",
            customer_id="SN",
            edition="on-prem-full",
            expires_at=datetime.now(timezone.utc) + timedelta(days=375),
        ),
    )

    prior = session.get(IssuanceLedger, "sn-2026")
    assert prior.superseded_by == "sn-2027"
    assert session.get(IssuanceLedger, "sn-2027").superseded_by is None

    # roster shows only the current row
    current = roster(session)
    assert [r.license_id for r in current] == ["sn-2027"]
    # full history includes both
    assert {r.license_id for r in roster(session, include_superseded=True)} == {
        "sn-2026",
        "sn-2027",
    }
    assert second.ledger_row.license_id == "sn-2027"
    assert first.ledger_row.license_id == "sn-2026"


def test_renew_rejects_already_superseded(session, keypair):
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)
    svc.issue(IssuanceRequest(license_id="a", customer_id="C", edition="saas"))
    svc.renew("a", IssuanceRequest(license_id="b", customer_id="C", edition="saas"))
    with pytest.raises(ValueError, match="already superseded"):
        svc.renew("a", IssuanceRequest(license_id="c", customer_id="C", edition="saas"))


def test_renew_rejects_duplicate_license_id(session, keypair):
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)
    svc.issue(IssuanceRequest(license_id="a", customer_id="C", edition="saas"))
    with pytest.raises(ValueError, match="must differ"):
        svc.renew("a", IssuanceRequest(license_id="a", customer_id="C", edition="saas"))


# --------------------------------------------------------------------------- #
# Query API: by_customer + expiring_soon
# --------------------------------------------------------------------------- #
def test_by_customer_filters_and_expiring_soon(session, keypair):
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)
    now = datetime.now(timezone.utc)

    svc.issue(
        IssuanceRequest(
            license_id="sn-1", customer_id="SN", edition="on-prem-full",
            expires_at=now + timedelta(days=5),
        )
    )
    svc.issue(
        IssuanceRequest(
            license_id="acme-1", customer_id="ACME", edition="saas",
            expires_at=now + timedelta(days=100),
        )
    )
    svc.issue(
        IssuanceRequest(
            license_id="perp-1", customer_id="PERP", edition="saas",
            # no expiry
        )
    )

    sn = by_customer(session, "SN")
    assert [r.license_id for r in sn] == ["sn-1"]
    assert by_customer(session, "NOPE") == []

    soon = expiring_soon(session, within_days=30, now=now)
    assert [r.license_id for r in soon] == ["sn-1"]  # acme too far, perp has no expiry

    wide = expiring_soon(session, within_days=200, now=now)
    assert [r.license_id for r in wide] == ["sn-1", "acme-1"]  # ordered by expiry


def test_expiring_soon_excludes_superseded(session, keypair):
    priv_pem, _ = keypair
    svc = IssuanceService(session, priv_pem)
    now = datetime.now(timezone.utc)
    svc.issue(
        IssuanceRequest(license_id="x1", customer_id="X", edition="saas",
                        expires_at=now + timedelta(days=5))
    )
    svc.renew(
        "x1",
        IssuanceRequest(license_id="x2", customer_id="X", edition="saas",
                        expires_at=now + timedelta(days=400)),
    )
    soon = expiring_soon(session, within_days=30, now=now)
    assert soon == []  # x1 superseded, x2 far out


# --------------------------------------------------------------------------- #
# The SQL migration is valid DDL
# --------------------------------------------------------------------------- #
def test_sql_migration_is_valid_ddl():
    """Apply the Postgres migration against sqlite to confirm the DDL parses + runs.

    sqlite accepts arbitrary type names (JSONB/TIMESTAMPTZ) under its flexible
    typing, so only the Postgres-specific `::jsonb` cast in the DEFAULT needs
    neutralising for this validation pass — the .sql file stays Postgres-correct.
    """
    raw = MIGRATION.read_text()
    assert "CREATE TABLE" in raw and "issuance_ledger" in raw

    # Strip line comments, then drop the postgres-only ::jsonb cast for sqlite.
    no_comments = "\n".join(
        re.sub(r"--.*$", "", ln) for ln in raw.splitlines()
    )
    sqlite_sql = no_comments.replace("::jsonb", "")

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for stmt in (s.strip() for s in sqlite_sql.split(";")):
            if stmt:
                conn.execute(text(stmt))
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(issuance_ledger)"))}
    expected = {
        "license_id", "customer_id", "edition", "entitled_modules", "quota_tier",
        "issued_at", "not_before", "expires_at", "superseded_by", "delivery",
        "deployment_secret_id",
    }
    assert expected <= cols
