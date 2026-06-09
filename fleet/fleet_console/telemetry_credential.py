"""Per-deployment telemetry credential — mint at issuance, verify at intake (ADR 0009 §3).

ADR 0009 §3 says: "At issuance, each deployment also gets a **per-deployment
credential** (an HMAC secret / API key, ``deployment_secret_id`` in the ledger)
baked into its secret bundle. Telemetry is authenticated with it and tied back to
the ledger row." This module is the *one place* that defines that credential — how
it is minted, where the secret lives, and how a telemetry HMAC is verified — so the
intake endpoint (#375) and the deployment-side signer (#376) agree by construction.

What is minted (`mint_credential`)
----------------------------------
- ``deployment_secret_id`` — a short, stable, NON-secret identifier, shaped
  ``dep-<customer>-<rand>``. This is what goes onto the ledger row
  (``IssuanceLedger.deployment_secret_id``) and travels in the clear inside the
  telemetry payload so intake knows *which* secret to look up.
- ``secret`` — a cryptographically random HMAC key (``secrets.token_urlsafe(32)``,
  ~256 bits of entropy). This is the sensitive half; it is delivered to the
  deployment (in its secret bundle) and stored vendor-side so intake can verify.

Where the secret material lives (security rationale)
----------------------------------------------------
HMAC is **symmetric**: the verifier (intake, #375) needs the *same* secret the
signer (the deployment, #376) used — there is no public/private split as there is
for the ed25519 *license* key. So the vendor side must retain the secret itself,
not merely a one-way hash of it (a hash cannot recompute an HMAC).

We therefore store the secret, but **isolate** it:

- ``deployment_secret_id`` → the **ledger** (``issuance_ledger`` row). Non-secret;
  it is just a pointer.
- the secret value → a **separate** ``deployment_secret`` table, keyed by
  ``deployment_secret_id``. This table is explicitly SENSITIVE: it is the telemetry
  verification keyset and should get the same at-rest protection as other
  vendor-side secrets (DB-level encryption / restricted grants). Keeping it in its
  own table — not a column on the ledger — means the broad, frequently-read fleet
  roster query never pulls secret bytes into memory, and the secret table can be
  locked down / column-encrypted independently of the metadata ledger.

Blast radius (ADR 0009 Consequences): a leaked deployment secret only lets an
attacker **forge that one customer's telemetry**, never a license — licenses are
signed with the offline ed25519 *private* key, which never enters this system at
all (see docs/saas-deployment/license-key-custody.md). Telemetry is metadata-only
(ADR 0009 §3/§5), so the worst case is poisoned usage counters for a single
customer, detectable and revocable by rotating that one secret.

The HMAC scheme (defined HERE; #375 uses it verbatim)
-----------------------------------------------------
- Algorithm: **HMAC-SHA256**.
- Key: the per-deployment ``secret`` (UTF-8 bytes of the ``token_urlsafe`` string).
- Message: the **raw telemetry payload bytes**, signed exactly as transmitted
  (the deployment serialises its usage bundle to bytes, signs those bytes, and
  sends both bytes + signature; intake re-HMACs the bytes it received). No
  canonicalisation is imposed here — the signer and verifier agree on the exact
  byte string, which is the safest contract for an opaque metadata blob.
- Encoding: the signature is **lowercase hex** (``hmac.hexdigest()``).
- Comparison: constant-time (``hmac.compare_digest``).

``verify_telemetry_hmac(deployment_secret_id, payload_bytes, signature) -> bool``
looks up the secret by id and returns True iff ``signature`` is a valid
HMAC-SHA256 of ``payload_bytes`` under that secret. Unknown id → False (no leak of
whether the id exists beyond the boolean). ``sign_telemetry`` is the inverse, used
by tests (and documents what the deployment-side signer #376 must do).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, IssuanceLedger

try:  # pragma: no cover - typing convenience
    from sqlalchemy.orm import Session
except Exception:  # pragma: no cover
    Session = object  # type: ignore


# --------------------------------------------------------------------------- #
# Sensitive store — the telemetry HMAC keyset (isolated from the ledger)
# --------------------------------------------------------------------------- #
class DeploymentSecret(Base):
    """The per-deployment telemetry HMAC secret, keyed by ``deployment_secret_id``.

    SENSITIVE: this is the verification keyset for telemetry intake. HMAC is
    symmetric, so the secret value itself must be retained (a hash cannot recompute
    an HMAC). Kept in its own table — never a column on the broad, frequently-read
    ``issuance_ledger`` roster — so it can be granted/encrypted independently and so
    roster queries never load secret bytes. Treat at-rest like any vendor secret.
    """

    __tablename__ = "deployment_secret"

    # Stable, non-secret pointer; matches IssuanceLedger.deployment_secret_id.
    deployment_secret_id: Mapped[str] = mapped_column(String, primary_key=True)
    # The HMAC key (token_urlsafe string). Sensitive — see class docstring.
    secret: Mapped[str] = mapped_column(String, nullable=False)
    # Which ledger lineage / customer this secret authenticates (for revocation
    # and audit). Non-FK on purpose: a rotated license_id should not orphan a
    # still-valid secret mid-rotation; the link is informational.
    customer_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    license_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug aid; never print `secret`
        return (
            f"DeploymentSecret(deployment_secret_id={self.deployment_secret_id!r}, "
            f"customer_id={self.customer_id!r}, license_id={self.license_id!r})"
        )


@dataclass
class TelemetryCredential:
    """The minted credential. ``secret`` is sensitive — return it to the caller for
    bundling into the deployment's secret bundle, then drop it; do not log it."""

    deployment_secret_id: str  # non-secret; written to the ledger row
    secret: str  # sensitive HMAC key; goes into the deployment secret bundle


# --------------------------------------------------------------------------- #
# Mint
# --------------------------------------------------------------------------- #
def _new_secret_id(customer_id: str) -> str:
    """Short, stable, collision-resistant id: ``dep-<customer>-<rand>``.

    ``customer_id`` is slugified to keep the id readable in the ledger/UI; the
    random suffix (token_hex(4) = 8 hex chars) makes it unique across a customer's
    renewals so rotation produces a fresh, distinguishable id.
    """
    slug = "".join(c.lower() if c.isalnum() else "-" for c in customer_id).strip("-")
    slug = slug or "cust"
    return f"dep-{slug}-{secrets.token_hex(4)}"


def mint_credential(customer_id: str) -> TelemetryCredential:
    """Mint a fresh per-deployment telemetry credential (pure, no DB side-effects).

    Returns the non-secret id + the random HMAC secret. Persisting it is the
    caller's job (``persist_credential``) so the mint+ledger write stay in ONE
    transaction (ADR 0009 §1 "both or neither").
    """
    return TelemetryCredential(
        deployment_secret_id=_new_secret_id(customer_id),
        secret=secrets.token_urlsafe(32),  # ~256 bits
    )


def persist_credential(
    session: "Session",
    cred: TelemetryCredential,
    *,
    customer_id: str,
    license_id: Optional[str],
) -> DeploymentSecret:
    """Add the secret row to the session (NO commit — the caller's transaction owns it).

    Mirrors how ``IssuanceService`` flushes within its own transaction so the
    credential and the ledger row commit together or not at all.
    """
    row = DeploymentSecret(
        deployment_secret_id=cred.deployment_secret_id,
        secret=cred.secret,
        customer_id=customer_id,
        license_id=license_id,
    )
    session.add(row)
    return row


def get_secret(session: "Session", deployment_secret_id: str) -> Optional[str]:
    """Look up the raw secret by id (for intake verification). None if unknown."""
    row = session.get(DeploymentSecret, deployment_secret_id)
    return row.secret if row is not None else None


# --------------------------------------------------------------------------- #
# HMAC scheme — the ONE definition shared by signer (#376) and verifier (#375)
# --------------------------------------------------------------------------- #
def sign_telemetry(secret: str, payload_bytes: bytes) -> str:
    """HMAC-SHA256(payload_bytes) under ``secret``, lowercase hex.

    This is exactly what the deployment-side signer (#376) must produce. Defined
    here so there is one canonical scheme; ``verify_telemetry_hmac`` is its inverse.
    """
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def verify_telemetry_hmac(
    session: "Session",
    deployment_secret_id: str,
    payload_bytes: bytes,
    signature: str,
) -> bool:
    """Validate a telemetry HMAC against the stored per-deployment secret.

    Returns True iff ``signature`` is a valid HMAC-SHA256 (lowercase hex) of
    ``payload_bytes`` under the secret registered for ``deployment_secret_id``.
    Unknown id → False. Constant-time comparison (``hmac.compare_digest``) so a
    valid prefix leaks no timing signal. This is the function #375 calls.
    """
    secret = get_secret(session, deployment_secret_id)
    if secret is None:
        return False
    expected = sign_telemetry(secret, payload_bytes)
    return hmac.compare_digest(expected, signature or "")


# --------------------------------------------------------------------------- #
# Rotation — re-mint a secret without touching the license (ADR 0009 Consequences)
# --------------------------------------------------------------------------- #
def rotate_credential(
    session: "Session",
    *,
    customer_id: str,
    license_id: Optional[str] = None,
    old_deployment_secret_id: Optional[str] = None,
) -> TelemetryCredential:
    """Mint + persist a NEW telemetry secret and (optionally) delete the old one.

    Use when a deployment secret leaks: rotating it invalidates the old secret's
    forged telemetry while leaving the LICENSE untouched (licenses need the offline
    ed25519 private key, which this system never holds). The caller owns the
    transaction; pass the resulting ``deployment_secret_id`` to an
    ``UPDATE issuance_ledger SET deployment_secret_id = ...`` on the active row.

    Renewals rotate implicitly: ``IssuanceService.renew`` mints a fresh credential
    for the new lineage row (the new license_id gets a new secret), so a renewed
    deployment naturally gets a new telemetry key in its refreshed secret bundle.
    """
    if old_deployment_secret_id is not None:
        old = session.get(DeploymentSecret, old_deployment_secret_id)
        if old is not None:
            session.delete(old)
    cred = mint_credential(customer_id)
    persist_credential(session, cred, customer_id=customer_id, license_id=license_id)
    return cred


def secret_for_license(session: "Session", license_id: str) -> Optional[str]:
    """Resolve the active telemetry secret for a license via the ledger pointer.

    Convenience for intake/debugging: ledger row -> deployment_secret_id -> secret.
    """
    led = session.get(IssuanceLedger, license_id)
    if led is None or led.deployment_secret_id is None:
        return None
    return get_secret(session, led.deployment_secret_id)


__all__ = [
    "DeploymentSecret",
    "TelemetryCredential",
    "mint_credential",
    "persist_credential",
    "get_secret",
    "sign_telemetry",
    "verify_telemetry_hmac",
    "rotate_credential",
    "secret_for_license",
]
