"""Telemetry intake endpoint (ADR 0009 §3, issue #375).

The single internet-facing intake for opt-in fleet telemetry. ADR 0009 §3 defines
three reachability tiers that ALL land in one store (``telemetry_record``):

    realtime  — SaaS direct push           → POST /telemetry
    periodic  — connected on-prem heartbeat → POST /telemetry
    offline   — air-gapped signed bundle    → POST /telemetry/upload (file)

Both entrypoints feed ONE persistence path (``_persist``), validate the SAME
strict metadata-only schema (``TelemetryPayload``), and require the SAME
per-deployment HMAC (#374) over the RAW payload bytes BEFORE any parsing.

Security posture (ADR 0009 §3, §5):
  - **Auth first.** Every request carries ``deployment_secret_id`` + an HMAC
    signature over the raw body bytes; we verify it BEFORE parsing/persisting and
    reject with 401 on bad/missing HMAC. (Verification = #374's
    ``verify_telemetry_hmac``; see telemetry_credential.py for the stub note.)
  - **Metadata only.** ``TelemetryPayload`` sets ``extra="forbid"`` so any unknown
    field (i.e. smuggled business data / PII) is rejected with 422.
  - **Tied to the ledger.** The reported ``license_id`` must exist in the issuance
    ledger and (when the ledger row carries a ``deployment_secret_id``) must match
    the authenticating credential.

App wiring follows the isa_common style (``create_*`` factory, like
``setup_observability``/``setup_licensing``): ``create_intake_app(session_factory)``
returns a FastAPI app; ``build_intake_router(session_factory)`` returns just the
APIRouter for mounting into a larger app.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from .models import IssuanceLedger
from .telemetry_credential import verify_telemetry_hmac
from .telemetry_models import TelemetryRecord

try:  # pragma: no cover - typing convenience
    from sqlalchemy.orm import Session
except Exception:  # pragma: no cover
    Session = object  # type: ignore

logger = logging.getLogger("fleet_console.intake")

# Header names carrying the auth credential (ADR 0009 §3).
HEADER_SECRET_ID = "X-Deployment-Secret-Id"
HEADER_SIGNATURE = "X-Telemetry-Signature"

# A session factory: called with no args, returns a context-manager SQLAlchemy
# Session (e.g. ``lambda: Session(engine)``). Mirrors how a service injects its DB.
SessionFactory = Callable[[], "Session"]


# --------------------------------------------------------------------------- #
# Strict metadata-only schema (ADR 0009 §3, §5)
# --------------------------------------------------------------------------- #
class TelemetryPayload(BaseModel):
    """The ONLY shape the intake accepts — fleet metadata, nothing else.

    ``extra="forbid"`` is the data-boundary guard (ADR 0009 §5): any field not
    listed below — i.e. any attempt to smuggle business data or PII — makes the
    request fail validation (422). No business records, no tenant content.
    """

    model_config = ConfigDict(extra="forbid")

    # Ties the record to a ledger row (ADR 0009 §3).
    license_id: str = Field(..., min_length=1)

    # When the deployment was last active (its clock). Drives honest-silence (§4).
    last_seen: datetime

    # Editions/modules ACTUALLY active (vs. merely entitled).
    active_edition: Optional[str] = None
    active_modules: List[str] = Field(default_factory=list)

    # Per-module usage counters — counters only, never content. {"erp": 1200}.
    module_usage: Dict[str, int] = Field(default_factory=dict)

    # Showback rollup totals (ADR 0008 §3). {"requests": 50000, "seats": 12}.
    showback_totals: Dict[str, float] = Field(default_factory=dict)

    # ADR 0008 §3 over-license flag.
    over_license: bool = False


def _verify_or_401(deployment_secret_id: Optional[str], raw: bytes, signature: Optional[str]) -> str:
    """HMAC-verify the raw bytes BEFORE any parsing; raise 401 on any failure."""
    if not deployment_secret_id or not signature:
        raise HTTPException(status_code=401, detail="missing telemetry credential")
    if not verify_telemetry_hmac(deployment_secret_id, raw, signature):
        raise HTTPException(status_code=401, detail="invalid telemetry signature")
    return deployment_secret_id


def _parse_payload_or_422(raw: bytes) -> TelemetryPayload:
    """Parse + strictly validate the raw bytes into a TelemetryPayload (422 on bad)."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=422, detail=f"invalid JSON payload: {e}") from e
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="payload must be a JSON object")
    # model_validate enforces extra="forbid" → unknown fields raise ValidationError.
    from pydantic import ValidationError

    try:
        return TelemetryPayload.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=json.loads(e.json())) from e


def _persist(
    session: "Session",
    payload: TelemetryPayload,
    *,
    deployment_secret_id: str,
    source: str,
) -> TelemetryRecord:
    """The single persistence path shared by BOTH ingestion entrypoints.

    Ties the record to its ledger row (ADR 0009 §3): the license must exist, and
    when the ledger row pins a ``deployment_secret_id`` the authenticating
    credential must match it. Writes one metadata-only ``telemetry_record`` row.
    """
    ledger_row = session.get(IssuanceLedger, payload.license_id)
    if ledger_row is None:
        raise HTTPException(
            status_code=404, detail=f"unknown license_id: {payload.license_id!r}"
        )
    # If the ledger row pins a credential (#374), it must match the caller's.
    if (
        ledger_row.deployment_secret_id is not None
        and ledger_row.deployment_secret_id != deployment_secret_id
    ):
        raise HTTPException(
            status_code=403,
            detail="deployment_secret_id does not match the ledger row for this license",
        )

    record = TelemetryRecord(
        license_id=payload.license_id,
        deployment_secret_id=deployment_secret_id,
        last_seen=payload.last_seen,
        received_at=datetime.now(timezone.utc),
        source=source,
        active_edition=payload.active_edition,
        active_modules=list(payload.active_modules),
        module_usage=dict(payload.module_usage),
        showback_totals=dict(payload.showback_totals),
        over_license=payload.over_license,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _ingest(
    session: "Session",
    raw: bytes,
    *,
    deployment_secret_id: Optional[str],
    signature: Optional[str],
    source: str,
) -> dict:
    """Full auth→validate→persist pipeline shared by POST and file-upload."""
    sid = _verify_or_401(deployment_secret_id, raw, signature)
    payload = _parse_payload_or_422(raw)
    record = _persist(session, payload, deployment_secret_id=sid, source=source)
    return {
        "status": "accepted",
        "id": record.id,
        "license_id": record.license_id,
        "last_seen": record.last_seen.isoformat() if record.last_seen else None,
        "source": record.source,
    }


def build_intake_router(session_factory: SessionFactory) -> APIRouter:
    """Build the telemetry intake APIRouter bound to a SQLAlchemy session factory.

    Two entrypoints, one persistence path:
      - ``POST /telemetry``         — realtime/periodic JSON push (tiers a/b).
      - ``POST /telemetry/upload``  — air-gapped signed bundle upload (tier c).
    """
    router = APIRouter(tags=["telemetry"])

    @router.post("/telemetry", status_code=201)
    async def post_telemetry(  # noqa: D401 - FastAPI handler
        request: Request,
        x_deployment_secret_id: Optional[str] = Header(default=None),
        x_telemetry_signature: Optional[str] = Header(default=None),
    ) -> dict:
        """Realtime/periodic telemetry push (ADR 0009 §3 tiers realtime + periodic).

        HMAC is verified over the RAW request body before any parsing.
        """
        raw = await request.body()
        with session_factory() as session:
            return _ingest(
                session,
                raw,
                deployment_secret_id=x_deployment_secret_id,
                signature=x_telemetry_signature,
                source="realtime",
            )

    @router.post("/telemetry/upload", status_code=201)
    async def upload_telemetry(  # noqa: D401 - FastAPI handler
        file: UploadFile,
        x_deployment_secret_id: Optional[str] = Header(default=None),
        x_telemetry_signature: Optional[str] = Header(default=None),
    ) -> dict:
        """Air-gapped signed-bundle upload (ADR 0009 §3 offline tier).

        SAME schema + SAME HMAC validation as the POST path — only the transport
        (a multipart file) and the recorded ``source`` differ. The uploaded file's
        RAW bytes are exactly what the deployment's exporter HMAC-signed.
        """
        raw = await file.read()
        with session_factory() as session:
            return _ingest(
                session,
                raw,
                deployment_secret_id=x_deployment_secret_id,
                signature=x_telemetry_signature,
                source="offline-upload",
            )

    return router


def create_intake_app(session_factory: SessionFactory) -> FastAPI:
    """App factory (isa_common ``create_*`` style) for the telemetry intake service.

    Returns a FastAPI app with the intake router mounted and a liveness ``/healthz``.
    A real deployment would also call ``setup_observability(app, ...)`` here.
    """
    app = FastAPI(title="Fleet Telemetry Intake", version="0.1.0")
    app.include_router(build_intake_router(session_factory))

    @app.get("/healthz")
    async def healthz() -> dict:  # pragma: no cover - trivial liveness
        return {"status": "ok"}

    return app


__all__ = [
    "TelemetryPayload",
    "build_intake_router",
    "create_intake_app",
    "HEADER_SECRET_ID",
    "HEADER_SIGNATURE",
]
