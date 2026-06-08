"""Read-side query API for the issuance ledger (ADR 0009 §1, §4 UI roster/expiry).

Library-level (no HTTP yet) — these back the fleet UI (#377). All functions take a
SQLAlchemy ``Session`` and return ``IssuanceLedger`` rows.

"Current" / "active" == ``superseded_by IS NULL AND revoked_at IS NULL`` (a renewed
row points its ``superseded_by`` at its successor, so the lineage's live row is the
one with no successor; a revoked row (#377) is flagged ``revoked_at`` and also drops
out of the active set). ``include_superseded=True`` returns the full historical
ledger, INCLUDING superseded and revoked rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select

from .models import IssuanceLedger

try:  # pragma: no cover - typing convenience
    from sqlalchemy.orm import Session
except Exception:  # pragma: no cover
    Session = object  # type: ignore


def roster(session: "Session", *, include_superseded: bool = False) -> List[IssuanceLedger]:
    """All current (non-superseded) licenses — the fleet roster.

    Pass ``include_superseded=True`` to get the full historical ledger instead.
    Ordered by customer_id then issued_at for stable display.
    """
    stmt = select(IssuanceLedger)
    if not include_superseded:
        stmt = stmt.where(
            IssuanceLedger.superseded_by.is_(None),
            IssuanceLedger.revoked_at.is_(None),
        )
    stmt = stmt.order_by(IssuanceLedger.customer_id, IssuanceLedger.issued_at)
    return list(session.scalars(stmt).all())


def by_customer(
    session: "Session", customer_id: str, *, include_superseded: bool = False
) -> List[IssuanceLedger]:
    """All licenses for one customer.

    By default returns only the current (non-superseded) issuance(s); pass
    ``include_superseded=True`` for the customer's full renewal history.
    Ordered newest-issued first.
    """
    stmt = select(IssuanceLedger).where(IssuanceLedger.customer_id == customer_id)
    if not include_superseded:
        stmt = stmt.where(
            IssuanceLedger.superseded_by.is_(None),
            IssuanceLedger.revoked_at.is_(None),
        )
    stmt = stmt.order_by(IssuanceLedger.issued_at.desc())
    return list(session.scalars(stmt).all())


def expiring_soon(
    session: "Session",
    within_days: int,
    *,
    now: Optional[datetime] = None,
    include_superseded: bool = False,
) -> List[IssuanceLedger]:
    """Current licenses expiring within ``within_days`` from ``now`` (default: utcnow).

    Drives the expiry calendar / renewal alerts (ADR 0009 §4). Rows with no
    ``expires_at`` (perpetual) are excluded. Already-expired rows ARE included
    (their expires_at is <= the window end), so the UI can surface lapsed licenses
    too. Ordered by soonest expiry first.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    window_end = now + timedelta(days=within_days)

    stmt = select(IssuanceLedger).where(
        IssuanceLedger.expires_at.is_not(None),
        IssuanceLedger.expires_at <= window_end,
    )
    if not include_superseded:
        stmt = stmt.where(
            IssuanceLedger.superseded_by.is_(None),
            IssuanceLedger.revoked_at.is_(None),
        )
    stmt = stmt.order_by(IssuanceLedger.expires_at)
    return list(session.scalars(stmt).all())


__all__ = ["roster", "by_customer", "expiring_soon"]
