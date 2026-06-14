"""SQLAlchemy model for telemetry intake records (ADR 0009 §3, issue #375).

The telemetry-intake counterpart of the issuance ledger. Where the ledger
(``models.IssuanceLedger``, #373) is the authoritative "what isA issued", this
table is the best-effort "what each deployment chose to report back" — the
opt-in telemetry of ADR 0009 §3.

Data boundary (ADR 0009 §5): **metadata ONLY**. No customer business records, no
PII, no tenant content. Every column here is fleet metadata: which license, when
last seen, which editions/modules are active, and showback rollups (counters +
the ADR 0008 §3 ``over_license`` flag). The intake endpoint enforces this at the
schema layer (``intake.TelemetryPayload`` forbids extra fields) so business data
cannot be smuggled into the store.

All three reachability tiers (ADR 0009 §3 — realtime SaaS, periodic on-prem,
offline air-gapped upload) land in THIS one table; only the ``source`` column
distinguishes how a record arrived.

It re-uses the issuance ledger's declarative ``Base`` so a single
``Base.metadata.create_all()`` builds both tables, and so the FK to
``issuance_ledger.license_id`` is enforced.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

# Share the issuance ledger's Base so both tables live in one metadata/schema and
# the license_id FK resolves (ADR 0009 §3: telemetry is tied back to the ledger row).
from .models import Base


class TelemetryRecord(Base):
    """One reported telemetry snapshot for a deployment (ADR 0009 §3).

    Tied back to its ledger row by ``license_id`` (FK) and tagged with the
    ``deployment_secret_id`` that authenticated it. Metadata only.
    """

    __tablename__ = "telemetry_record"

    # Surrogate PK — many snapshots per license over time.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Ties the snapshot to its ledger row (ADR 0009 §3). FK so an unknown license
    # can't be reported against (intake also checks this before insert).
    license_id: Mapped[str] = mapped_column(
        String, ForeignKey("issuance_ledger.license_id"), nullable=False, index=True
    )

    # The credential that authenticated this record (the ledger's per-deployment
    # HMAC id, #374). Recorded for audit / honest-silence-per-deployment queries.
    deployment_secret_id: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, index=True
    )

    # When the deployment says it was last active (from the payload). Drives the
    # "no telemetry since X" honest-silence reporting (ADR 0009 §4).
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # When the console actually persisted this record (server clock). Lets us
    # distinguish "deployment's claimed last_seen" from "when we heard it".
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # How this record reached the console (ADR 0009 §3 tier): "realtime",
    # "periodic", or "offline-upload". One store, source-tagged.
    source: Mapped[str] = mapped_column(String, nullable=False, default="realtime")

    # The edition the deployment reports as actually active (vs. entitled).
    active_edition: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Module keys reported as actively used (metadata, not content).
    active_modules: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)

    # Per-module usage counters, e.g. {"erp": 1200, "mes": 340}. Counters only.
    module_usage: Mapped[Dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)

    # Showback rollup totals (ADR 0008 §3), e.g. {"requests": 50000, "seats": 12}.
    showback_totals: Mapped[Dict[str, float]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # ADR 0008 §3 over-license flag — was the deployment running beyond its license?
    over_license: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"TelemetryRecord(id={self.id!r}, license_id={self.license_id!r}, "
            f"last_seen={self.last_seen!r}, source={self.source!r}, "
            f"over_license={self.over_license!r})"
        )
