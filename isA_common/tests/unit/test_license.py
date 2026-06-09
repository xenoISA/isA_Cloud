"""L1 unit tests — offline ed25519 license contract (ADR 0008).

Pure logic, env-driven. An ed25519 keypair is generated INSIDE the test and used
to sign fixtures on the fly — no keys are hardcoded. Covers: valid, expired,
grace, tampered-signature, edition-mismatch, and unlicensed (no file).
"""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

from isa_common.license import (
    LicenseConfig,
    LicenseStatus,
    _canonical_body,
    get_license,
)

LICENSE_ENV_VARS = ["ISA_LICENSE_FILE", "ISA_LICENSE_PUBKEY", "ISA_EDITION"]


@pytest.fixture(autouse=True)
def clean_license_env(monkeypatch):
    for var in LICENSE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    # get_edition() is a process-wide singleton; reset it so each test's
    # ISA_EDITION is honoured by the license edition-match check.
    import isa_common.edition as edition_mod

    edition_mod._edition = None
    yield
    edition_mod._edition = None


@pytest.fixture
def keypair():
    priv = ed25519.Ed25519PrivateKey.generate()
    pub_pem = (
        priv.public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        .decode("utf-8")
    )
    return priv, pub_pem


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sign(obj: dict, priv: ed25519.Ed25519PrivateKey) -> dict:
    """Return a copy of `obj` with a valid base64 ed25519 signature attached."""
    signed = dict(obj)
    signed.pop("signature", None)
    sig = priv.sign(_canonical_body(signed))
    signed["signature"] = base64.b64encode(sig).decode("ascii")
    return signed


def _base_license(edition="on-prem-full", **overrides) -> dict:
    now = datetime.now(timezone.utc)
    obj = {
        "license_id": "sn-prod-2026",
        "customer_id": "SN",
        "edition": edition,
        "issued_at": _iso(now - timedelta(days=1)),
        "not_before": _iso(now - timedelta(days=1)),
        "expires_at": _iso(now + timedelta(days=365)),
        "grace_days": 30,
        "entitled_modules": ["erp", "mes", "commercial_tower"],
        "quota_tier": "enterprise",
        "seats": -1,
    }
    obj.update(overrides)
    return obj


def _write_license(tmp_path, obj) -> str:
    path = tmp_path / "license.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    return str(path)


def _setup(monkeypatch, tmp_path, obj, priv, pub_pem, edition="on-prem-full"):
    path = _write_license(tmp_path, _sign(obj, priv))
    monkeypatch.setenv("ISA_LICENSE_FILE", path)
    monkeypatch.setenv("ISA_LICENSE_PUBKEY", pub_pem)
    monkeypatch.setenv("ISA_EDITION", edition)


class TestUnlicensed:
    def test_no_file_env_is_unlicensed(self):
        c = LicenseConfig.from_env()
        assert c.status is LicenseStatus.UNLICENSED
        assert c.customer_id == ""
        assert c.entitled_modules == frozenset()
        assert c.is_entitled("erp") is False

    def test_missing_file_path_is_unlicensed(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ISA_LICENSE_FILE", str(tmp_path / "nope.json"))
        assert LicenseConfig.from_env().status is LicenseStatus.UNLICENSED

    def test_from_env_never_raises_on_garbage_file(self, monkeypatch, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json{{{", encoding="utf-8")
        monkeypatch.setenv("ISA_LICENSE_FILE", str(path))
        monkeypatch.setenv("ISA_EDITION", "on-prem-full")
        assert LicenseConfig.from_env().status is LicenseStatus.INVALID


class TestValid:
    def test_valid_license(self, monkeypatch, tmp_path, keypair):
        priv, pub_pem = keypair
        _setup(monkeypatch, tmp_path, _base_license(), priv, pub_pem)
        c = LicenseConfig.from_env()
        assert c.status is LicenseStatus.VALID
        assert c.customer_id == "SN"
        assert c.edition == "on-prem-full"
        assert c.quota_tier == "enterprise"
        assert c.seats == -1
        assert c.is_entitled("commercial_tower") is True
        assert c.is_entitled("not_a_module") is False
        assert c.entitled_modules == frozenset({"erp", "mes", "commercial_tower"})


class TestExpiry:
    def test_expired_within_grace_is_grace(self, monkeypatch, tmp_path, keypair):
        priv, pub_pem = keypair
        now = datetime.now(timezone.utc)
        obj = _base_license(
            expires_at=_iso(now - timedelta(days=5)),
            grace_days=30,
        )
        _setup(monkeypatch, tmp_path, obj, priv, pub_pem)
        assert LicenseConfig.from_env().status is LicenseStatus.GRACE

    def test_expired_past_grace_is_expired(self, monkeypatch, tmp_path, keypair):
        priv, pub_pem = keypair
        now = datetime.now(timezone.utc)
        obj = _base_license(
            expires_at=_iso(now - timedelta(days=40)),
            grace_days=30,
        )
        _setup(monkeypatch, tmp_path, obj, priv, pub_pem)
        assert LicenseConfig.from_env().status is LicenseStatus.EXPIRED

    def test_expired_zero_grace_is_expired(self, monkeypatch, tmp_path, keypair):
        priv, pub_pem = keypair
        now = datetime.now(timezone.utc)
        obj = _base_license(
            expires_at=_iso(now - timedelta(hours=1)),
            grace_days=0,
        )
        _setup(monkeypatch, tmp_path, obj, priv, pub_pem)
        assert LicenseConfig.from_env().status is LicenseStatus.EXPIRED

    def test_not_yet_valid_is_invalid(self, monkeypatch, tmp_path, keypair):
        priv, pub_pem = keypair
        now = datetime.now(timezone.utc)
        obj = _base_license(not_before=_iso(now + timedelta(days=2)))
        _setup(monkeypatch, tmp_path, obj, priv, pub_pem)
        assert LicenseConfig.from_env().status is LicenseStatus.INVALID


class TestSignature:
    def test_tampered_body_after_signing_is_invalid(self, monkeypatch, tmp_path, keypair):
        priv, pub_pem = keypair
        signed = _sign(_base_license(), priv)
        # Tamper AFTER signing — flip an entitlement the signature does not cover.
        signed["entitled_modules"] = ["erp", "mes", "commercial_tower", "finance"]
        path = _write_license(tmp_path, signed)
        monkeypatch.setenv("ISA_LICENSE_FILE", path)
        monkeypatch.setenv("ISA_LICENSE_PUBKEY", pub_pem)
        monkeypatch.setenv("ISA_EDITION", "on-prem-full")
        assert LicenseConfig.from_env().status is LicenseStatus.INVALID

    def test_garbage_signature_is_invalid(self, monkeypatch, tmp_path, keypair):
        priv, pub_pem = keypair
        obj = _base_license()
        obj["signature"] = base64.b64encode(b"not-a-real-signature").decode("ascii")
        path = _write_license(tmp_path, obj)
        monkeypatch.setenv("ISA_LICENSE_FILE", path)
        monkeypatch.setenv("ISA_LICENSE_PUBKEY", pub_pem)
        monkeypatch.setenv("ISA_EDITION", "on-prem-full")
        assert LicenseConfig.from_env().status is LicenseStatus.INVALID

    def test_wrong_key_is_invalid(self, monkeypatch, tmp_path, keypair):
        priv, _ = keypair
        other_pub = (
            ed25519.Ed25519PrivateKey.generate()
            .public_key()
            .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
            .decode("utf-8")
        )
        _setup(monkeypatch, tmp_path, _base_license(), priv, other_pub)
        assert LicenseConfig.from_env().status is LicenseStatus.INVALID

    def test_missing_pubkey_is_invalid(self, monkeypatch, tmp_path, keypair):
        priv, _ = keypair
        path = _write_license(tmp_path, _sign(_base_license(), priv))
        monkeypatch.setenv("ISA_LICENSE_FILE", path)
        monkeypatch.setenv("ISA_EDITION", "on-prem-full")
        # ISA_LICENSE_PUBKEY intentionally unset.
        assert LicenseConfig.from_env().status is LicenseStatus.INVALID


class TestEditionMismatch:
    def test_edition_mismatch_is_invalid(self, monkeypatch, tmp_path, keypair):
        priv, pub_pem = keypair
        # License says on-prem-full, but the process runs as saas.
        _setup(
            monkeypatch,
            tmp_path,
            _base_license(edition="on-prem-full"),
            priv,
            pub_pem,
            edition="saas",
        )
        assert LicenseConfig.from_env().status is LicenseStatus.INVALID


def test_invalid_drops_entitlements(monkeypatch, tmp_path, keypair):
    priv, pub_pem = keypair
    _setup(
        monkeypatch,
        tmp_path,
        _base_license(edition="on-prem-full"),
        priv,
        pub_pem,
        edition="saas",
    )
    c = LicenseConfig.from_env()
    assert c.status is LicenseStatus.INVALID
    assert c.is_entitled("erp") is False  # nothing granted on INVALID


class TestCurrentStatus:
    """current_status() re-derives the time-based status at runtime (H1).

    The signature-verified static fields are frozen at boot; only VALID/GRACE/EXPIRED
    drifts with the wall clock. current_status() must recompute it (cheap datetime
    compare, no signature re-verify) so long-running pods see expiry.
    """

    def _cfg(self, *, status, expires_at, grace_days):
        return LicenseConfig(
            status=status,
            customer_id="SN",
            edition="on-prem-full",
            expires_at=expires_at,
            grace_days=grace_days,
            entitled_modules=frozenset({"erp"}),
            quota_tier="enterprise",
            seats=-1,
        )

    def test_rederives_expired_when_now_past_grace(self):
        # Boot status was VALID, but now() is well past expiry+grace.
        boot = datetime(2026, 1, 1, tzinfo=timezone.utc)
        expires = boot + timedelta(days=30)
        cfg = self._cfg(status=LicenseStatus.VALID, expires_at=expires, grace_days=10)
        # Within window → still VALID.
        assert cfg.current_status(now=expires - timedelta(days=1)) is LicenseStatus.VALID
        # In grace window → GRACE.
        assert cfg.current_status(now=expires + timedelta(days=5)) is LicenseStatus.GRACE
        # Past grace → EXPIRED, even though boot status was VALID.
        assert cfg.current_status(now=expires + timedelta(days=20)) is LicenseStatus.EXPIRED

    def test_grace_boundary_inclusive(self):
        expires = datetime(2026, 1, 1, tzinfo=timezone.utc)
        cfg = self._cfg(status=LicenseStatus.VALID, expires_at=expires, grace_days=10)
        grace_end = expires + timedelta(days=10)
        assert cfg.current_status(now=grace_end) is LicenseStatus.GRACE
        assert cfg.current_status(now=grace_end + timedelta(seconds=1)) is LicenseStatus.EXPIRED

    def test_expiry_boundary_inclusive_is_valid(self):
        expires = datetime(2026, 1, 1, tzinfo=timezone.utc)
        cfg = self._cfg(status=LicenseStatus.VALID, expires_at=expires, grace_days=0)
        assert cfg.current_status(now=expires) is LicenseStatus.VALID
        assert cfg.current_status(now=expires + timedelta(seconds=1)) is LicenseStatus.EXPIRED

    def test_perpetual_is_always_valid(self):
        cfg = self._cfg(status=LicenseStatus.VALID, expires_at=None, grace_days=0)
        far_future = datetime(3000, 1, 1, tzinfo=timezone.utc)
        assert cfg.current_status(now=far_future) is LicenseStatus.VALID

    @pytest.mark.parametrize("terminal", [LicenseStatus.INVALID, LicenseStatus.UNLICENSED])
    def test_terminal_status_unchanged(self, terminal):
        # Terminal statuses have no signed window to re-derive — stay as-is even if
        # the (meaningless) expires_at would otherwise imply a different status.
        cfg = self._cfg(
            status=terminal,
            expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            grace_days=0,
        )
        far_future = datetime(3000, 1, 1, tzinfo=timezone.utc)
        assert cfg.current_status(now=far_future) is terminal

    def test_default_now_is_utc_now(self):
        # No now= → uses datetime.now(timezone.utc). A license that expired long ago
        # resolves to EXPIRED without an injected clock.
        expires = datetime(2000, 1, 1, tzinfo=timezone.utc)
        cfg = self._cfg(status=LicenseStatus.VALID, expires_at=expires, grace_days=0)
        assert cfg.current_status() is LicenseStatus.EXPIRED


def test_from_env_uses_same_derivation_as_current_status(monkeypatch, tmp_path, keypair):
    """Boot status from from_env() agrees with current_status() at boot time."""
    priv, pub_pem = keypair
    now = datetime.now(timezone.utc)
    obj = _base_license(expires_at=_iso(now - timedelta(days=5)), grace_days=30)
    _setup(monkeypatch, tmp_path, obj, priv, pub_pem)
    c = LicenseConfig.from_env()
    assert c.status is LicenseStatus.GRACE
    assert c.current_status() is LicenseStatus.GRACE


def test_frozen_dataclass_is_immutable():
    c = LicenseConfig.from_env()
    with pytest.raises(Exception):
        c.status = LicenseStatus.VALID  # type: ignore[misc]


def test_get_license_is_singleton(monkeypatch, tmp_path, keypair):
    priv, pub_pem = keypair
    _setup(monkeypatch, tmp_path, _base_license(), priv, pub_pem)
    import isa_common.license as lic_mod

    lic_mod._license = None  # reset for a clean read (no public reset by design)
    first = get_license()
    second = get_license()
    assert first is second
    lic_mod._license = None  # leave module state clean for other tests
