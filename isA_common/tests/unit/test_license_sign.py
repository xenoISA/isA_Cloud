"""L1 unit tests — offline ed25519 license SIGNING CLI (ADR 0008 §1, issue #366).

The signing tool (isa_common.license_sign) is the issuance counterpart to the
verifier (isa_common.license, #365). The contract is: anything the CLI signs must
load back as VALID through the verifier. These tests exercise that round trip end
to end — generate a keypair, sign a license (from flags and from a spec file), and
assert isa_common.license resolves it to VALID with the right entitlements — plus
the negative cases (tamper, wrong edition).
"""

import base64
import json

import pytest
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_private_key,
)

from isa_common.license import LicenseConfig, LicenseStatus
from isa_common.license_sign import (
    _canonical_body,
    build_spec,
    generate_keypair,
    sign_license,
)
from isa_common.license_sign import main as sign_main

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
def keypair_files(tmp_path):
    """Write a real ed25519 keypair to disk and return (priv_path, pub_pem_str)."""
    private_pem, public_pem = generate_keypair()
    priv_path = tmp_path / "isa-license-ed25519.key"
    priv_path.write_bytes(private_pem)
    return str(priv_path), public_pem.decode("utf-8")


def _verify_valid(monkeypatch, license_path, pub_pem, edition):
    monkeypatch.setenv("ISA_LICENSE_FILE", str(license_path))
    monkeypatch.setenv("ISA_LICENSE_PUBKEY", pub_pem)
    monkeypatch.setenv("ISA_EDITION", edition)
    return LicenseConfig.from_env()


def test_keygen_writes_ed25519_pair(tmp_path):
    out_dir = tmp_path / "keys"
    rc = sign_main(["keygen", "--out-dir", str(out_dir), "--name", "k"])
    assert rc == 0
    priv_path = out_dir / "k.key"
    pub_path = out_dir / "k.pub"
    assert priv_path.exists() and pub_path.exists()
    # Private key is a real, loadable ed25519 private key, written 0600.
    assert (priv_path.stat().st_mode & 0o777) == 0o600
    key = load_pem_private_key(priv_path.read_bytes(), password=None)
    pub = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    assert pub == pub_path.read_bytes()


def test_cli_sign_round_trips_to_valid(monkeypatch, tmp_path, keypair_files):
    """The headline contract: a CLI-signed license verifies as VALID."""
    priv_path, pub_pem = keypair_files
    out = tmp_path / "license.json"
    rc = sign_main(
        [
            "sign",
            "--key",
            priv_path,
            "--customer-id",
            "SN",
            "--edition",
            "on-prem-full",
            "--entitled-modules",
            "erp,mes,commercial_tower",
            "--quota-tier",
            "enterprise",
            "--seats",
            "-1",
            "--expires-at",
            "2099-01-01T00:00:00Z",
            "--grace-days",
            "30",
            "--out",
            str(out),
        ]
    )
    assert rc == 0  # rc==0 implies the built-in round-trip self-check passed too

    cfg = _verify_valid(monkeypatch, out, pub_pem, "on-prem-full")
    assert cfg.status is LicenseStatus.VALID
    assert cfg.customer_id == "SN"
    assert cfg.edition == "on-prem-full"
    assert cfg.quota_tier == "enterprise"
    assert cfg.seats == -1
    assert cfg.entitled_modules == frozenset({"erp", "mes", "commercial_tower"})
    assert cfg.is_entitled("commercial_tower") is True


def test_cli_sign_from_spec_file_round_trips(monkeypatch, tmp_path, keypair_files):
    priv_path, pub_pem = keypair_files
    spec = {
        "customer_id": "ACME",
        "edition": "saas",
        "entitled_modules": ["erp", "finance"],
        "quota_tier": "enterprise",
        "expires_at": "2099-01-01T00:00:00Z",
        "grace_days": 14,
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    out = tmp_path / "acme.json"

    rc = sign_main(["sign", "--key", priv_path, "--spec", str(spec_path), "--out", str(out)])
    assert rc == 0

    cfg = _verify_valid(monkeypatch, out, pub_pem, "saas")
    assert cfg.status is LicenseStatus.VALID
    assert cfg.customer_id == "ACME"
    assert cfg.entitled_modules == frozenset({"erp", "finance"})


def test_flags_override_spec_file(tmp_path, keypair_files):
    priv_path, _ = keypair_files
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps({"customer_id": "ACME", "edition": "saas"}), encoding="utf-8")

    class _Args:
        spec = str(spec_path)
        license_id = None
        customer_id = "OVERRIDE"
        edition = "on-prem-full"
        not_before = None
        expires_at = None
        quota_tier = None
        entitled_modules = "erp"
        grace_days = None
        seats = None

    built = build_spec(_Args())
    assert built["customer_id"] == "OVERRIDE"
    assert built["edition"] == "on-prem-full"
    assert built["entitled_modules"] == ["erp"]


def test_signature_matches_verifier_canonical_body(keypair_files, tmp_path):
    """The CLI signs the SAME canonical bytes the verifier reconstructs."""
    priv_path, pub_pem = keypair_files
    priv = load_pem_private_key(open(priv_path, "rb").read(), password=None)

    class _Args:
        spec = None
        license_id = "x-1"
        customer_id = "SN"
        edition = "on-prem-full"
        not_before = None
        expires_at = "2099-01-01T00:00:00Z"
        quota_tier = "enterprise"
        entitled_modules = "erp,mes"
        grace_days = 0
        seats = -1

    spec = build_spec(_Args())
    signed = sign_license(spec, priv)

    pub = priv.public_key()
    sig = base64.b64decode(signed["signature"])
    # Must not raise — same canonical bytes on both sides.
    pub.verify(sig, _canonical_body(signed))


def test_tampered_after_signing_is_invalid(monkeypatch, tmp_path, keypair_files):
    priv_path, pub_pem = keypair_files
    out = tmp_path / "license.json"
    sign_main(
        [
            "sign",
            "--key",
            priv_path,
            "--customer-id",
            "SN",
            "--edition",
            "on-prem-full",
            "--entitled-modules",
            "erp",
            "--expires-at",
            "2099-01-01T00:00:00Z",
            "--out",
            str(out),
        ]
    )
    obj = json.loads(out.read_text())
    obj["entitled_modules"] = ["erp", "finance"]  # tamper, signature unchanged
    out.write_text(json.dumps(obj), encoding="utf-8")

    cfg = _verify_valid(monkeypatch, out, pub_pem, "on-prem-full")
    assert cfg.status is LicenseStatus.INVALID


def test_sign_missing_required_field_errors(tmp_path, keypair_files):
    priv_path, _ = keypair_files
    out = tmp_path / "license.json"
    # No customer_id anywhere → build_spec validation fails → main returns 1.
    rc = sign_main(["sign", "--key", priv_path, "--edition", "saas", "--out", str(out)])
    assert rc == 1
    assert not out.exists()


def test_expired_license_fails_self_check(tmp_path, keypair_files):
    """A signed-but-expired license must fail the round-trip self-check loudly."""
    priv_path, _ = keypair_files
    out = tmp_path / "license.json"
    with pytest.raises(SystemExit):
        sign_main(
            [
                "sign",
                "--key",
                priv_path,
                "--customer-id",
                "SN",
                "--edition",
                "on-prem-full",
                "--expires-at",
                "2000-01-01T00:00:00Z",
                "--grace-days",
                "0",
                "--out",
                str(out),
            ]
        )
