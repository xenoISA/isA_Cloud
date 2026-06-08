"""Issuance workflow — sign a license AND write the ledger row, atomically (ADR 0009 §1–2).

Issuing a license is ONE workflow with two inseparable effects (ADR 0009 §1: "the
two cannot diverge"):

    (a) sign the artifact via ``isa_common.license_sign`` -> the signed license.json
    (b) write the issuance-ledger row

We MUST NOT hand out a license whose ledger row failed to persist, nor persist a
row for a license we never produced.

Ordering / atomicity choice
---------------------------
1. Sign FIRST, in memory (pure CPU, no side effects, can't half-fail). If signing
   raises, nothing was written and no artifact escapes.
2. Then write the ledger row inside a single DB transaction. The signed artifact is
   only RETURNED to the caller after that transaction commits. If the commit fails,
   the transaction rolls back and we raise — the caller never receives a license.

Signing happens before the DB write because it is the cheaper thing to undo
(throwing away an in-memory dict) and because the ledger row records *what was
signed* (license_id, issued_at) — which only exists after signing. The artifact is
withheld until commit, so from the caller's perspective the two are atomic: you get
both or neither.

This wraps the signer's library API (``sign_license``) rather than the CLI, and
reuses the verifier's canonicalisation by construction (``sign_license`` signs the
same canonical body ``isa_common.license`` reconstructs), so every artifact this
emits verifies VALID — confirmed by a round-trip test.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Union

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from isa_common.license_sign import sign_license

from .models import IssuanceLedger

# Imported lazily-as-needed; Session typing only.
try:  # pragma: no cover - typing convenience
    from sqlalchemy.orm import Session
except Exception:  # pragma: no cover
    Session = object  # type: ignore


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    """Render a tz-aware datetime as the signer's Z-suffixed ISO-8601."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(value) -> Optional[datetime]:
    """Coerce an ISO-8601 string (optionally Z-suffixed) or datetime to UTC-aware."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class IssuanceRequest:
    """A request to issue (or renew) a license.

    Mirrors the license fields ADR 0008 §1 signs, plus ledger-only ``delivery``.
    Datetimes may be passed as datetime or ISO-8601 string.
    """

    customer_id: str
    edition: str
    entitled_modules: List[str] = field(default_factory=list)
    quota_tier: Optional[str] = None
    # datetime | ISO-8601 str | None. expires_at None = no expiry;
    # not_before None = default to issued_at.
    expires_at: Optional[Union[datetime, str]] = None
    not_before: Optional[Union[datetime, str]] = None
    grace_days: int = 0
    seats: int = -1
    license_id: Optional[str] = None  # default derived: <customer>-<date>
    delivery: Optional[str] = None  # ADR 0007, e.g. "offline-bundle"


@dataclass
class IssuanceResult:
    """The output of an issuance: the signed artifact + the persisted ledger row."""

    license: dict  # the signed license.json body (with base64 `signature`)
    ledger_row: IssuanceLedger


def _load_private_key(key_pem: bytes) -> ed25519.Ed25519PrivateKey:
    key = load_pem_private_key(key_pem, password=None)
    if not isinstance(key, ed25519.Ed25519PrivateKey):
        raise ValueError("signing key is not an ed25519 private key")
    return key


def _build_spec(req: IssuanceRequest, issued_at: datetime) -> dict:
    """Assemble the signable license body from a request, applying the same
    defaults/validation the signer's CLI applies (license_sign.build_spec)."""
    if not req.customer_id or not req.edition:
        raise ValueError("issuance request requires customer_id and edition")
    if not isinstance(req.entitled_modules, list):
        raise ValueError("entitled_modules must be a list")

    issued_iso = _iso(issued_at)
    not_before = _parse_ts(req.not_before) or issued_at
    expires = _parse_ts(req.expires_at)
    license_id = req.license_id or f"{req.customer_id}-{issued_iso[:10]}"

    spec: dict = {
        "license_id": license_id,
        "customer_id": req.customer_id,
        "edition": req.edition,
        "issued_at": issued_iso,
        "not_before": _iso(not_before),
        "grace_days": int(req.grace_days),
        "entitled_modules": list(req.entitled_modules),
        "quota_tier": req.quota_tier,
        "seats": int(req.seats),
    }
    if expires is not None:
        spec["expires_at"] = _iso(expires)
    # quota_tier is optional in the signed body; drop if None to keep it clean.
    if spec["quota_tier"] is None:
        spec.pop("quota_tier")
    return spec


class IssuanceService:
    """Issues licenses against a SQLAlchemy session + an ed25519 private key.

    The private key is passed in (PEM bytes) and held only for the lifetime of the
    call chain — custody stays offline (ADR 0009 §2); the console calls the signer,
    it does not run a hot key service.
    """

    def __init__(self, session: "Session", signing_key_pem: bytes):
        self._session = session
        self._priv = _load_private_key(signing_key_pem)

    def issue(self, req: IssuanceRequest) -> IssuanceResult:
        """Sign + ledger-write a NEW license atomically. Returns the signed artifact.

        The signed artifact is only returned after the ledger row commits.
        """
        issued_at = _now()
        spec = _build_spec(req, issued_at)

        # (a) sign in memory — pure, side-effect-free.
        signed = sign_license(spec, self._priv)

        # (b) write the ledger row in one transaction; artifact withheld until commit.
        row = IssuanceLedger(
            license_id=spec["license_id"],
            customer_id=spec["customer_id"],
            edition=spec["edition"],
            entitled_modules=list(spec["entitled_modules"]),
            quota_tier=spec.get("quota_tier"),
            issued_at=issued_at,
            not_before=_parse_ts(spec["not_before"]),
            expires_at=_parse_ts(spec.get("expires_at")),
            superseded_by=None,
            delivery=req.delivery,
            deployment_secret_id=None,  # populated by #374
        )
        self._session.add(row)
        self._session.flush()  # surface PK/constraint errors before we vouch for it
        self._session.commit()
        return IssuanceResult(license=signed, ledger_row=row)

    def renew(self, prior_license_id: str, req: IssuanceRequest) -> IssuanceResult:
        """Issue a renewal and set ``superseded_by`` on the prior row, atomically.

        The new license is signed, the new ledger row is written, and the prior
        row's ``superseded_by`` is pointed at the new license_id — all in one
        transaction. Renewal of an already-superseded row is rejected (avoids
        branching a lineage).
        """
        prior = self._session.get(IssuanceLedger, prior_license_id)
        if prior is None:
            raise ValueError(f"unknown prior license_id: {prior_license_id!r}")
        if prior.superseded_by is not None:
            raise ValueError(
                f"license {prior_license_id!r} is already superseded by "
                f"{prior.superseded_by!r}; renew its successor instead"
            )

        issued_at = _now()
        # Carry customer_id/edition forward from the prior row unless overridden.
        if not req.customer_id:
            req.customer_id = prior.customer_id
        if not req.edition:
            req.edition = prior.edition
        spec = _build_spec(req, issued_at)
        if spec["license_id"] == prior_license_id:
            raise ValueError(
                "renewal license_id must differ from the prior license_id "
                f"({prior_license_id!r}); pass a distinct license_id"
            )

        signed = sign_license(spec, self._priv)

        new_row = IssuanceLedger(
            license_id=spec["license_id"],
            customer_id=spec["customer_id"],
            edition=spec["edition"],
            entitled_modules=list(spec["entitled_modules"]),
            quota_tier=spec.get("quota_tier"),
            issued_at=issued_at,
            not_before=_parse_ts(spec["not_before"]),
            expires_at=_parse_ts(spec.get("expires_at")),
            superseded_by=None,
            delivery=req.delivery,
            deployment_secret_id=None,
        )
        self._session.add(new_row)
        self._session.flush()  # new row must exist before prior can FK-reference it
        prior.superseded_by = new_row.license_id
        self._session.commit()
        return IssuanceResult(license=signed, ledger_row=new_row)


# --------------------------------------------------------------------------- #
# Convenience functions
# --------------------------------------------------------------------------- #
def issue_license(
    session: "Session", signing_key_pem: bytes, req: IssuanceRequest
) -> IssuanceResult:
    """Functional shorthand for ``IssuanceService(session, key).issue(req)``."""
    return IssuanceService(session, signing_key_pem).issue(req)


def renew_license(
    session: "Session",
    signing_key_pem: bytes,
    prior_license_id: str,
    req: IssuanceRequest,
) -> IssuanceResult:
    """Functional shorthand for ``IssuanceService(...).renew(prior_license_id, req)``."""
    return IssuanceService(session, signing_key_pem).renew(prior_license_id, req)


__all__ = [
    "IssuanceRequest",
    "IssuanceResult",
    "IssuanceService",
    "issue_license",
    "renew_license",
]


# Keep base64 import referenced (signer returns base64 signature; useful for callers
# that want raw bytes). Not strictly required, but documents the artifact shape.
def signature_bytes(signed_license: dict) -> bytes:  # pragma: no cover - helper
    """Decode the base64 ``signature`` field of a signed license to raw bytes."""
    return base64.b64decode(signed_license["signature"])
