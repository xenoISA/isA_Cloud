#!/usr/bin/env python3
"""
License configuration — the offline "who may run this, which modules, until when"
contract (ADR 0008).

Under the profile/edition model every edition runs the SAME image set, so the only
thing distinguishing a licensed install from an unlicensed copy is configuration. A
signed license file is what makes that configuration tamper-evident. SN runs
air-gapped (no public egress, FW-OUT-001), so there is NO online activation and NO
phone-home: the license is an offline, locally-verifiable signed artifact — a
`license.json` signed with isA's ed25519 private key; the image embeds only the
PUBLIC key and verifies the signature + expiry locally.

This module is the RUNTIME half, mirroring edition.py / brand.py: a `LicenseStatus`
enum, a frozen `LicenseConfig` dataclass, a `from_env()` classmethod, and a
process-wide `get_license()` singleton, exported from isa_common/__init__.py next to
get_edition / get_brand.

Defaults are conservative and decoupled from enforcement: with no ISA_LICENSE_FILE
set, status is UNLICENSED — which on a dev/lite install is fine (enforcement is
opt-in, see ADR 0008 §3). from_env() NEVER raises; any failure (missing file, bad
signature, edition mismatch, malformed JSON) resolves to an INVALID/UNLICENSED
status, never an exception.

Usage:
    from isa_common import get_license

    lic = get_license()
    if not lic.is_entitled("commercial_tower"):
        raise SystemExit("module not entitled by license")
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from .edition import get_edition

logger = logging.getLogger(__name__)

# Env var names (set per-profile in Helm values/ConfigMap, see ADR 0008 §6).
ISA_LICENSE_FILE = "ISA_LICENSE_FILE"
ISA_LICENSE_PUBKEY = "ISA_LICENSE_PUBKEY"


class LicenseStatus(str, Enum):
    """Resolved license state for the running process (ADR 0008 §2)."""

    VALID = "valid"  # signed, in-window
    GRACE = "grace"  # expired but within grace_days → warn, allow
    EXPIRED = "expired"  # past expiry + grace
    INVALID = "invalid"  # bad signature / edition mismatch / malformed
    UNLICENSED = "unlicensed"  # no license file present


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into a tz-aware UTC datetime.

    Accepts a trailing 'Z' (which datetime.fromisoformat rejects before 3.11).
    Naive timestamps are assumed to be UTC. Returns None on absent/unparseable
    input so callers can treat it as "no bound".
    """
    if not value:
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _canonical_body(obj: dict) -> bytes:
    """Reproduce the signed payload: the license object with `signature` removed,
    serialized canonically (sorted keys, no whitespace). UTF-8 bytes.
    """
    body = {k: v for k, v in obj.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


# Statuses that are NOT time-derived: once resolved they cannot be re-trusted at
# runtime (there is no signature to re-verify on a cheap datetime compare).
_TERMINAL_STATUSES = (LicenseStatus.INVALID, LicenseStatus.UNLICENSED)


def _derive_time_status(
    expires_at: Optional[datetime],
    grace_days: int,
    now: datetime,
) -> LicenseStatus:
    """Derive the VALID/GRACE/EXPIRED *time* status from the signature-verified
    static fields (`expires_at`, `grace_days`) vs `now`.

    This is the ONLY part of a license's status that changes over wall-clock time;
    every other field is fixed by the signature. It is a pure datetime comparison —
    NO signature verification — so it is safe to call per-request.

    Perpetual licenses (`expires_at is None`) are always VALID.
    """
    if expires_at is None:
        return LicenseStatus.VALID
    if now <= expires_at:
        return LicenseStatus.VALID
    grace_end = expires_at + timedelta(days=max(grace_days, 0))
    if now <= grace_end:
        return LicenseStatus.GRACE
    return LicenseStatus.EXPIRED


@dataclass(frozen=True)
class LicenseConfig:
    """Offline-verified license state + entitlements. NEVER editable at runtime."""

    status: LicenseStatus
    customer_id: str
    edition: str
    expires_at: Optional[datetime]
    grace_days: int
    entitled_modules: frozenset
    quota_tier: Optional[str]
    seats: int

    def is_entitled(self, module_key: str) -> bool:
        """True if `module_key` is in the license's entitled_modules set."""
        return module_key in self.entitled_modules

    def current_status(self, now: Optional[datetime] = None) -> LicenseStatus:
        """Re-derive the VALID/GRACE/EXPIRED *time* status as of `now`.

        The signature-verified static fields (`expires_at`, `grace_days`, ...) are
        frozen at boot by `from_env()`; only the time-derived status drifts as the
        clock advances. A long-running pod must re-evaluate that drift per request
        instead of freezing the boot status — otherwise an expiry that happens while
        the pod stays up is never observed (H1, ADR 0008 §3).

        This is a cheap datetime comparison: the signature was already trusted ONCE
        at boot, so there is NOTHING to re-verify here. Terminal statuses
        (INVALID/UNLICENSED) are returned unchanged — there is no signed window to
        re-derive. Perpetual licenses (`expires_at is None`) are always VALID.

        Args:
            now: Override for the current time (UTC). Defaults to
                `datetime.now(timezone.utc)`. Injectable for tests.

        Returns:
            The license status as of `now`.
        """
        if self.status in _TERMINAL_STATUSES:
            return self.status
        if now is None:
            now = datetime.now(timezone.utc)
        return _derive_time_status(self.expires_at, self.grace_days, now)

    @classmethod
    def unlicensed(cls) -> "LicenseConfig":
        """The conservative no-license default (no ISA_LICENSE_FILE set)."""
        return cls(
            status=LicenseStatus.UNLICENSED,
            customer_id="",
            edition="",
            expires_at=None,
            grace_days=0,
            entitled_modules=frozenset(),
            quota_tier=None,
            seats=0,
        )

    @classmethod
    def invalid(
        cls,
        *,
        customer_id: str = "",
        edition: str = "",
        expires_at: Optional[datetime] = None,
        grace_days: int = 0,
        entitled_modules: frozenset = frozenset(),
        quota_tier: Optional[str] = None,
        seats: int = 0,
    ) -> "LicenseConfig":
        """An INVALID config — entitlements are dropped so nothing is granted."""
        return cls(
            status=LicenseStatus.INVALID,
            customer_id=customer_id,
            edition=edition,
            expires_at=expires_at,
            grace_days=grace_days,
            entitled_modules=entitled_modules,
            quota_tier=quota_tier,
            seats=seats,
        )

    @classmethod
    def from_env(cls) -> "LicenseConfig":
        """Load + verify the license from env (ADR 0008 §1–2).

        ISA_LICENSE_FILE   path to a signed license.json (unset/missing → UNLICENSED)
        ISA_LICENSE_PUBKEY ed25519 public key (PEM) used to verify the signature

        Flow: parse JSON → ed25519-verify the canonical body against `signature` →
        require license `edition` to equal get_edition().edition.value → check
        not_before / expires_at (+ grace_days) against current UTC → derive status.
        Any failure resolves to UNLICENSED or INVALID; this method NEVER raises.
        """
        path = os.getenv(ISA_LICENSE_FILE)
        if not path or not os.path.isfile(path):
            # No license file present is a normal, non-error state (dev/lite).
            return cls.unlicensed()

        # --- read + parse ---------------------------------------------------
        try:
            with open(path, "r", encoding="utf-8") as fh:
                obj = json.load(fh)
            if not isinstance(obj, dict):
                raise ValueError("license root is not a JSON object")
        except (OSError, ValueError) as exc:
            logger.warning("license: unreadable/malformed file %s: %s", path, exc)
            return cls.invalid()

        # Extract fields up-front so an INVALID result can still surface metadata.
        customer_id = str(obj.get("customer_id", ""))
        edition = str(obj.get("edition", ""))
        expires_at = _parse_ts(obj.get("expires_at"))
        not_before = _parse_ts(obj.get("not_before"))
        try:
            grace_days = int(obj.get("grace_days", 0))
        except (TypeError, ValueError):
            grace_days = 0
        try:
            seats = int(obj.get("seats", 0))
        except (TypeError, ValueError):
            seats = 0
        quota_tier = obj.get("quota_tier")
        quota_tier = str(quota_tier) if quota_tier is not None else None
        raw_modules = obj.get("entitled_modules") or []
        entitled_modules = frozenset(str(m) for m in raw_modules)

        def _invalid() -> "LicenseConfig":
            return cls.invalid(
                customer_id=customer_id,
                edition=edition,
                expires_at=expires_at,
                grace_days=grace_days,
                quota_tier=quota_tier,
                seats=seats,
            )

        # --- verify ed25519 signature over the canonical body ---------------
        signature_b64 = obj.get("signature")
        pubkey_pem = os.getenv(ISA_LICENSE_PUBKEY)
        if not signature_b64 or not pubkey_pem:
            logger.warning("license: missing signature or ISA_LICENSE_PUBKEY")
            return _invalid()

        try:
            import base64

            from cryptography.hazmat.primitives.asymmetric import ed25519
            from cryptography.hazmat.primitives.serialization import (
                load_pem_public_key,
            )

            public_key = load_pem_public_key(pubkey_pem.encode("utf-8"))
            if not isinstance(public_key, ed25519.Ed25519PublicKey):
                logger.warning("license: ISA_LICENSE_PUBKEY is not an ed25519 key")
                return _invalid()
            signature = base64.b64decode(signature_b64)
            public_key.verify(signature, _canonical_body(obj))
        except Exception as exc:  # InvalidSignature, bad PEM, bad base64, etc.
            logger.warning("license: signature verification failed: %s", exc)
            return _invalid()

        # --- edition must match the running edition -------------------------
        running_edition = get_edition().edition.value
        if edition != running_edition:
            logger.warning(
                "license: edition mismatch (license=%r, running=%r)",
                edition,
                running_edition,
            )
            return _invalid()

        # --- derive time-based status (signature already trusted) -----------
        now = datetime.now(timezone.utc)

        if not_before is not None and now < not_before:
            # Not yet valid — treat as not-in-window / invalid.
            logger.warning("license: not yet valid (not_before=%s)", not_before)
            return _invalid()

        status = _derive_time_status(expires_at, grace_days, now)
        if status is LicenseStatus.GRACE:
            logger.warning(
                "license: in GRACE window (expired %s, grace_days=%d)",
                expires_at,
                grace_days,
            )
        elif status is LicenseStatus.EXPIRED:
            logger.warning("license: EXPIRED (expired %s)", expires_at)

        return cls(
            status=status,
            customer_id=customer_id,
            edition=edition,
            expires_at=expires_at,
            grace_days=grace_days,
            entitled_modules=entitled_modules,
            quota_tier=quota_tier,
            seats=seats,
        )


# Module-level singleton — read env once at import, reuse everywhere.
_license: Optional[LicenseConfig] = None


def get_license() -> LicenseConfig:
    """Return the process-wide LicenseConfig (loaded + verified on first call)."""
    global _license
    if _license is None:
        _license = LicenseConfig.from_env()
    return _license
