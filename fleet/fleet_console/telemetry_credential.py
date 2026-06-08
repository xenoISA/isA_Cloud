"""Per-deployment telemetry credential + HMAC verification (ADR 0009 §3).

==============================================================================
STUB — OWNED BY #374, NOT #375.
==============================================================================

#375 (the intake endpoint) only *consumes* one function from here:

    verify_telemetry_hmac(deployment_secret_id, payload_bytes, signature) -> bool

That signature is the #374 contract. At the time #375 was written, #374 had not
yet merged into this branch, so this module provides a **thin, standard
implementation** of that one function plus the secret-resolution seam #374 owns.
It deliberately does NOT invent a divergent HMAC scheme — it uses the obvious
HMAC-SHA256 construction ADR 0009 §3 describes, so #374 can drop in its real
secret store (replacing ``_resolve_secret``) and keep the same verify contract.

TODO(#374): replace this whole module with the real telemetry-credential
implementation:
  - mint a per-deployment HMAC secret at issuance and write its id onto the
    ledger row (``IssuanceLedger.deployment_secret_id``);
  - back ``_resolve_secret`` with the real secret store (e.g. a secrets table /
    KMS / vault keyed by ``deployment_secret_id``), NOT the env fallback below;
  - keep ``verify_telemetry_hmac``'s signature byte-for-byte so #375's intake
    keeps working unchanged.

If #374 merges first, this file should be REPLACED by its real version; #375's
``intake.py`` imports ``verify_telemetry_hmac`` from here and needs no change.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Optional

logger = logging.getLogger("fleet_console.telemetry_credential")

# Env-var prefix for the stub secret store. #374 replaces this seam entirely.
# A deployment's secret is read from  FLEET_TELEMETRY_SECRET__<deployment_secret_id>.
_ENV_PREFIX = "FLEET_TELEMETRY_SECRET__"


def _resolve_secret(deployment_secret_id: str) -> Optional[bytes]:
    """Resolve the raw HMAC secret bytes for a deployment_secret_id.

    TODO(#374): back this with the real secret store. The stub reads from an
    env var so tests/dev can exercise the intake path without #374's store.
    Returns None when no secret is known for the id (→ verification fails closed).
    """
    if not deployment_secret_id:
        return None
    raw = os.getenv(_ENV_PREFIX + deployment_secret_id)
    if raw is None:
        return None
    return raw.encode("utf-8")


def compute_telemetry_hmac(secret: bytes, payload_bytes: bytes) -> str:
    """Compute the hex HMAC-SHA256 of ``payload_bytes`` under ``secret``.

    Exposed so the air-gap export tooling (#?) and tests can produce a matching
    signature with the SAME construction the verifier checks. HMAC-SHA256 over
    the RAW payload bytes, hex-encoded (ADR 0009 §3).
    """
    return hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()


def verify_telemetry_hmac(
    deployment_secret_id: str, payload_bytes: bytes, signature: str
) -> bool:
    """Verify an HMAC-SHA256 signature over the raw telemetry payload bytes.

    This is the #374 contract consumed by #375's intake endpoint. Returns True
    only when ``deployment_secret_id`` resolves to a known secret AND
    ``signature`` is a valid HMAC-SHA256 of ``payload_bytes`` under it. Fails
    CLOSED (returns False) on missing id, unknown secret, or missing/garbled
    signature — never raises for an auth failure.

    Comparison is constant-time (``hmac.compare_digest``).
    """
    if not deployment_secret_id or not signature:
        return False
    secret = _resolve_secret(deployment_secret_id)
    if secret is None:
        logger.warning(
            "no telemetry secret resolved for deployment_secret_id=%r (stub #374)",
            deployment_secret_id,
        )
        return False
    expected = compute_telemetry_hmac(secret, payload_bytes)
    try:
        return hmac.compare_digest(expected, signature.strip())
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return False


__all__ = ["verify_telemetry_hmac", "compute_telemetry_hmac"]
