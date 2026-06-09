#!/usr/bin/env python3
"""
isa-license-sign — the OFFLINE issuance counterpart to isa_common.license (ADR 0008).

The runtime half (`license.py`, issue #365) only ever VERIFIES: the image embeds
the ed25519 PUBLIC key (`ISA_LICENSE_PUBKEY`) and checks a mounted `license.json`
locally, with no phone-home (SN is air-gapped, FW-OUT-001). This module is the
ISSUANCE half — it runs on isA's side, never in a customer environment, and signs
a `license.json` with the ed25519 PRIVATE key.

It deliberately mirrors the verifier's canonicalisation EXACTLY so that anything
this tool emits verifies VALID through `isa_common.license`:

    signed_payload = json.dumps(body_without_signature,
                                sort_keys=True, separators=(",", ":")).encode()

Subcommands
-----------
    keygen   generate an ed25519 keypair (PEM): private for signing, public for
             ISA_LICENSE_PUBKEY (image bake / ConfigMap).
    sign     read a license spec (JSON file and/or flags), canonicalise, ed25519-sign,
             and write license.json with a base64 `signature`. After writing it runs
             a ROUND-TRIP SELF-CHECK: it loads the output back through
             isa_common.license with the matching public key + edition and asserts
             the resolved status is VALID — failing loudly otherwise.

Key custody
-----------
The PRIVATE key never ships and never enters a customer namespace. It stays offline
under the same custody as release signing (ADR 0007). The PUBLIC key is the only
half that travels (baked into the image or mounted as a non-secret ConfigMap, since
the signature already gives integrity). Rotation = generate a new keypair, re-issue
licenses with the new private key, and swap the public ConfigMap / rebuild the image.
See docs/saas-deployment/license-key-custody.md.

Usage
-----
    # one-time issuance setup
    python -m isa_common.license_sign keygen --out-dir ./keys
    #   -> keys/isa-license-ed25519.key (private, KEEP OFFLINE)
    #   -> keys/isa-license-ed25519.pub (public, -> ISA_LICENSE_PUBKEY)

    # sign from a spec file
    python -m isa_common.license_sign sign \
        --key keys/isa-license-ed25519.key \
        --spec spec.json \
        --out license.json

    # sign from flags
    python -m isa_common.license_sign sign \
        --key keys/isa-license-ed25519.key \
        --customer-id SN --edition on-prem-full \
        --entitled-modules erp,mes,commercial_tower \
        --quota-tier enterprise --seats -1 \
        --expires-at 2027-06-08T00:00:00Z --grace-days 30 \
        --out license.json
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone
from typing import List, Optional

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)

# The exact set of license fields, matching isa_common.license / ADR 0008 §1.
# `license_id` and `issued_at` are part of the signed body; the rest are the
# verifier-consumed fields.
_SIGNABLE_FIELDS = (
    "license_id",
    "customer_id",
    "edition",
    "issued_at",
    "not_before",
    "expires_at",
    "grace_days",
    "entitled_modules",
    "quota_tier",
    "seats",
)


# --------------------------------------------------------------------------- #
# Canonicalisation — MUST stay byte-identical to isa_common.license._canonical_body
# --------------------------------------------------------------------------- #
def _canonical_body(obj: dict) -> bytes:
    """Serialise the license object (sans `signature`) canonically: sorted keys,
    no whitespace, UTF-8. This is the exact payload the verifier reconstructs.
    """
    body = {k: v for k, v in obj.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# keygen
# --------------------------------------------------------------------------- #
def generate_keypair() -> "tuple[bytes, bytes]":
    """Return (private_pem, public_pem) for a fresh ed25519 keypair."""
    priv = ed25519.Ed25519PrivateKey.generate()
    private_pem = priv.private_bytes(
        Encoding.PEM,
        PrivateFormat.PKCS8,
        NoEncryption(),
    )
    public_pem = priv.public_key().public_bytes(
        Encoding.PEM,
        PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def _cmd_keygen(args: argparse.Namespace) -> int:
    private_pem, public_pem = generate_keypair()

    out_dir = args.out_dir
    name = args.name
    os.makedirs(out_dir, exist_ok=True)
    priv_path = os.path.join(out_dir, f"{name}.key")
    pub_path = os.path.join(out_dir, f"{name}.pub")

    # Private key written 0600 — it must never be world-readable.
    fd = os.open(priv_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(private_pem)
    with open(pub_path, "wb") as fh:
        fh.write(public_pem)

    print(f"private key (KEEP OFFLINE, 0600): {priv_path}", file=sys.stderr)
    print(f"public key  (-> ISA_LICENSE_PUBKEY): {pub_path}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- #
# sign
# --------------------------------------------------------------------------- #
def _load_private_key(key_pem: bytes) -> ed25519.Ed25519PrivateKey:
    key = load_pem_private_key(key_pem, password=None)
    if not isinstance(key, ed25519.Ed25519PrivateKey):
        raise ValueError("signing key is not an ed25519 private key")
    return key


def _parse_modules(value: Optional[str]) -> Optional[List[str]]:
    if value is None:
        return None
    return [m.strip() for m in value.split(",") if m.strip()]


def build_spec(args: argparse.Namespace) -> dict:
    """Assemble the license spec (the signable body, sans signature) from an
    optional --spec JSON file overlaid with any explicit flags.

    Precedence: explicit flags override file values. Sensible defaults fill in
    license_id / issued_at / not_before / grace_days / seats when absent.
    """
    spec: dict = {}
    if args.spec:
        with open(args.spec, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        if not isinstance(loaded, dict):
            raise ValueError("--spec must contain a JSON object")
        spec.update(loaded)

    # Overlay flags (only those explicitly provided / non-None).
    flag_map = {
        "license_id": args.license_id,
        "customer_id": args.customer_id,
        "edition": args.edition,
        "not_before": args.not_before,
        "expires_at": args.expires_at,
        "quota_tier": args.quota_tier,
    }
    for key, val in flag_map.items():
        if val is not None:
            spec[key] = val

    modules = _parse_modules(args.entitled_modules)
    if modules is not None:
        spec["entitled_modules"] = modules
    if args.grace_days is not None:
        spec["grace_days"] = args.grace_days
    if args.seats is not None:
        spec["seats"] = args.seats

    # Defaults for anything still missing.
    spec.setdefault("issued_at", _now_iso())
    spec.setdefault("not_before", spec["issued_at"])
    spec.setdefault("grace_days", 0)
    spec.setdefault("seats", -1)
    spec.setdefault("entitled_modules", [])
    spec.setdefault("license_id", f"{spec.get('customer_id', 'lic')}-{spec['issued_at'][:10]}")

    # Drop a signature if a spec file carried one — we re-sign.
    spec.pop("signature", None)

    _validate_spec(spec)
    return spec


def _validate_spec(spec: dict) -> None:
    missing = [f for f in ("customer_id", "edition") if not spec.get(f)]
    if missing:
        raise ValueError(
            f"spec missing required field(s): {', '.join(missing)} " "(provide via --spec or flags)"
        )
    if not isinstance(spec.get("entitled_modules", []), list):
        raise ValueError("entitled_modules must be a JSON array")
    # Surface any unexpected keys early — typos in a spec file would otherwise
    # be silently signed into the body.
    unknown = set(spec) - set(_SIGNABLE_FIELDS)
    if unknown:
        raise ValueError(f"unknown spec field(s): {', '.join(sorted(unknown))}")


def sign_license(spec: dict, priv: ed25519.Ed25519PrivateKey) -> dict:
    """Return the signed license dict: the spec plus a base64 ed25519 `signature`
    over the canonical body.
    """
    body = {k: v for k, v in spec.items() if k != "signature"}
    signature = priv.sign(_canonical_body(body))
    signed = dict(body)
    signed["signature"] = base64.b64encode(signature).decode("ascii")
    return signed


def _round_trip_check(out_path: str, public_pem: bytes, edition: str) -> None:
    """Load the freshly written license.json back through isa_common.license with
    the matching public key + edition and assert the resolved status is VALID.

    Raises SystemExit (loud failure) if it does not verify — the whole point of
    the CLI is that its output is trusted by the verifier.
    """
    # Import lazily so keygen/sign work even if the wider isa_common import graph
    # (DB drivers etc.) is unavailable; verification only needs license + edition.
    from isa_common.license import LicenseConfig, LicenseStatus

    prev = {k: os.environ.get(k) for k in ("ISA_LICENSE_FILE", "ISA_LICENSE_PUBKEY", "ISA_EDITION")}
    try:
        os.environ["ISA_LICENSE_FILE"] = out_path
        os.environ["ISA_LICENSE_PUBKEY"] = public_pem.decode("utf-8")
        os.environ["ISA_EDITION"] = edition
        # Reset the edition singleton so this edition is honoured by the match.
        import isa_common.edition as edition_mod

        edition_mod._edition = None
        cfg = LicenseConfig.from_env()
        edition_mod._edition = None
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    if cfg.status is not LicenseStatus.VALID:
        raise SystemExit(
            f"ROUND-TRIP SELF-CHECK FAILED: signed license verified as "
            f"{cfg.status.value!r}, expected 'valid'. Refusing to vouch for "
            f"{out_path}. Check expires_at/not_before (must straddle now) and "
            f"that --edition matches the license edition."
        )
    print(
        f"round-trip self-check: VALID "
        f"(customer={cfg.customer_id!r}, edition={cfg.edition!r}, "
        f"modules={len(cfg.entitled_modules)})",
        file=sys.stderr,
    )


def _cmd_sign(args: argparse.Namespace) -> int:
    with open(args.key, "rb") as fh:
        priv = _load_private_key(fh.read())

    spec = build_spec(args)
    signed = sign_license(spec, priv)

    rendered = json.dumps(signed, indent=2, sort_keys=True) + "\n"
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(rendered)
    print(f"wrote signed license: {args.out}", file=sys.stderr)

    # Round-trip self-check unless explicitly skipped.
    if not args.no_self_check:
        public_pem = priv.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        _round_trip_check(args.out, public_pem, signed["edition"])

    return 0


# --------------------------------------------------------------------------- #
# argparse wiring
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="isa-license-sign",
        description="Offline ed25519 signing tool for isA license.json (ADR 0008).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    kg = sub.add_parser("keygen", help="generate an ed25519 keypair (PEM)")
    kg.add_argument("--out-dir", default="keys", help="output directory (default: keys)")
    kg.add_argument(
        "--name",
        default="isa-license-ed25519",
        help="basename for .key/.pub (default: isa-license-ed25519)",
    )
    kg.set_defaults(func=_cmd_keygen)

    sg = sub.add_parser("sign", help="sign a license spec into license.json")
    sg.add_argument("--key", required=True, help="path to ed25519 private key (PEM)")
    sg.add_argument("--spec", help="path to a license spec JSON file (optional)")
    sg.add_argument("--out", default="license.json", help="output path (default: license.json)")
    sg.add_argument("--license-id", help="license_id (default: <customer>-<date>)")
    sg.add_argument("--customer-id", help="customer_id (required via spec or flag)")
    sg.add_argument("--edition", help="edition; must match ISA_EDITION at runtime")
    sg.add_argument(
        "--entitled-modules",
        help="comma-separated module keys (e.g. erp,mes,commercial_tower)",
    )
    sg.add_argument("--quota-tier", help="quota tier (e.g. enterprise)")
    sg.add_argument("--seats", type=int, help="seat count; -1 = unlimited (default -1)")
    sg.add_argument("--not-before", help="ISO-8601 start (default: issued_at)")
    sg.add_argument("--expires-at", help="ISO-8601 expiry (omit for no expiry)")
    sg.add_argument("--grace-days", type=int, help="soft grace window in days (default 0)")
    sg.add_argument(
        "--no-self-check",
        action="store_true",
        help="skip the round-trip VALID verification (not recommended)",
    )
    sg.set_defaults(func=_cmd_sign)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as exc:  # surface a clean error, not a traceback dump
        print(f"isa-license-sign: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
