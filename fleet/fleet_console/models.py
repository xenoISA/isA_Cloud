"""SQLAlchemy model for the license-issuance ledger (ADR 0009 §1).

One row per issued license / renewal. This is the **source of truth** for the
fleet console: it answers "who are all my customers, on what edition, with which
modules entitled, expiring when" with ZERO telemetry — which is exactly what
air-gapped customers contribute. Telemetry (#374/#375) only enriches it.

Data boundary (ADR 0009 §5): metadata ONLY. No customer business data, no PII.

Columns map 1:1 to the ADR 0009 §1 ledger row:

    license_id           text PK    — also the license.json license_id
    customer_id          text       — which customer
    edition              text       — must match ISA_EDITION at the deployment
    entitled_modules     json/array — licensed module keys
    quota_tier           text       — e.g. "enterprise"
    issued_at            timestamptz
    not_before           timestamptz
    expires_at           timestamptz (nullable — omitted = no expiry)
    superseded_by        text FK->self (nullable) — set when a renewal supersedes this row
    delivery             text       — how it was shipped (ADR 0007), e.g. "offline-bundle"
    deployment_secret_id text       (nullable) — populated by #374 (telemetry credential)

`deployment_secret_id` is intentionally left nullable and unpopulated here: #374
mints a per-deployment HMAC credential at issuance and writes its id back onto the
ledger row (UPDATE ... SET deployment_secret_id WHERE license_id = ...), so the
intake endpoint (#375) can validate telemetry against the ledger.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Declarative base for fleet_console models."""


class IssuanceLedger(Base):
    """One row per issued license / renewal (ADR 0009 §1)."""

    __tablename__ = "issuance_ledger"

    # Primary key — the license_id that is also signed into the license.json body.
    license_id: Mapped[str] = mapped_column(String, primary_key=True)

    customer_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    edition: Mapped[str] = mapped_column(String, nullable=False)

    # Entitled module keys. JSON (portable: jsonb on Postgres, TEXT on sqlite).
    entitled_modules: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)

    quota_tier: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Nullable: an omitted expires_at means "no expiry" (matches license.py).
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Self-referential: set on the PRIOR row when a renewal is issued. A row whose
    # superseded_by IS NULL is the current/active issuance for its lineage.
    superseded_by: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("issuance_ledger.license_id"), nullable=True
    )

    # How the signed bundle was shipped (ADR 0007), e.g. "offline-bundle".
    delivery: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Populated by #374 — per-deployment telemetry credential id. Left NULL here.
    deployment_secret_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"IssuanceLedger(license_id={self.license_id!r}, "
            f"customer_id={self.customer_id!r}, edition={self.edition!r}, "
            f"superseded_by={self.superseded_by!r})"
        )
