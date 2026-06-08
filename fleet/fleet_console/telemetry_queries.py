"""Read-side telemetry queries — honest silence reporting (ADR 0009 §3–4, #375).

The fleet UI (#377) must show usage "honestly as such" (ADR 0009 §4): realtime
for SaaS, last-uploaded for connected on-prem, and an explicit **"no telemetry
since X"** for silent / air-gapped deployments — never a fabricated dashboard.

These helpers answer that from the ``telemetry_record`` store joined against the
issuance ledger so EVERY current license appears, even ones that have NEVER
reported (last_seen = None ⇒ honestly silent).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func, select

from .models import IssuanceLedger
from .telemetry_models import TelemetryRecord

try:  # pragma: no cover - typing convenience
    from sqlalchemy.orm import Session
except Exception:  # pragma: no cover
    Session = object  # type: ignore


@dataclass
class DeploymentSilence:
    """Honest last-seen status for one current license (ADR 0009 §4).

    ``last_seen is None`` ⇒ the deployment has NEVER reported telemetry (silent /
    air-gapped) — surface it as such, do not fabricate usage. ``silent`` is True
    when there is no telemetry at all OR the newest record is older than the
    caller's staleness threshold.
    """

    license_id: str
    customer_id: str
    deployment_secret_id: Optional[str]
    last_seen: Optional[datetime]
    silent: bool


def latest_record(session: "Session", license_id: str) -> Optional[TelemetryRecord]:
    """The most recent telemetry record for a license (by last_seen), or None."""
    stmt = (
        select(TelemetryRecord)
        .where(TelemetryRecord.license_id == license_id)
        .order_by(TelemetryRecord.last_seen.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def last_seen_per_deployment(
    session: "Session",
    *,
    silent_after_days: Optional[int] = None,
    now: Optional[datetime] = None,
    include_superseded: bool = False,
) -> List[DeploymentSilence]:
    """Last-seen (and silence) status for every current license (ADR 0009 §4).

    Builds one row per current (non-superseded) ledger license, LEFT-joined to the
    max ``last_seen`` in ``telemetry_record``. Licenses that have never reported
    come back with ``last_seen=None`` and ``silent=True`` — the honest
    "no telemetry" state the UI must show for air-gapped/silent deployments.

    Args:
        silent_after_days: if given, a deployment whose newest telemetry is older
            than this many days from ``now`` is flagged ``silent=True``. If None,
            only never-reported deployments are silent.
        now: reference time for the staleness check (default: utcnow).
        include_superseded: include superseded ledger rows too (default: False).
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # max(last_seen) per license_id from the telemetry store.
    max_seen = (
        select(
            TelemetryRecord.license_id.label("license_id"),
            func.max(TelemetryRecord.last_seen).label("last_seen"),
        )
        .group_by(TelemetryRecord.license_id)
        .subquery()
    )

    stmt = select(IssuanceLedger, max_seen.c.last_seen).outerjoin(
        max_seen, max_seen.c.license_id == IssuanceLedger.license_id
    )
    if not include_superseded:
        stmt = stmt.where(
            IssuanceLedger.superseded_by.is_(None),
            IssuanceLedger.revoked_at.is_(None),
        )
    stmt = stmt.order_by(IssuanceLedger.customer_id, IssuanceLedger.license_id)

    threshold = (
        now - timedelta(days=silent_after_days) if silent_after_days is not None else None
    )

    out: List[DeploymentSilence] = []
    for ledger_row, last_seen in session.execute(stmt).all():
        ls = _as_aware(last_seen)
        if ls is None:
            silent = True
        elif threshold is not None:
            silent = ls < threshold
        else:
            silent = False
        out.append(
            DeploymentSilence(
                license_id=ledger_row.license_id,
                customer_id=ledger_row.customer_id,
                deployment_secret_id=ledger_row.deployment_secret_id,
                last_seen=ls,
                silent=silent,
            )
        )
    return out


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalise a possibly-naive DB datetime (sqlite drops tzinfo) to UTC-aware."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


__all__ = ["DeploymentSilence", "latest_record", "last_seen_per_deployment"]
