"""Fleet console HTTP API (ADR 0009 §4 UI + §2 issuance) — issue #377.

The query / issuance / telemetry functions in this package (#373/#374/#375) are a
Python *library*: there is no HTTP surface over them yet (only the telemetry INTAKE
endpoint, ``intake.py``, which is the deployment→vendor push, not the operator-facing
read/issue API). The Fleet UI (#377) needs an operator-facing API, so this module
exposes the read + write library functions over FastAPI.

It follows the same ``create_*`` factory / ``session_factory`` wiring as
``intake.py`` (and the isa_common ``setup_*`` factories):

    create_fleet_api(session_factory, signing_key_pem=...) -> FastAPI
    build_fleet_router(session_factory, signing_key_pem=...) -> APIRouter

Endpoints (all vendor-internal — this is NOT the internet-facing intake):

    GET  /fleet/roster                  -> roster() + derived status + last-seen/silence
    GET  /fleet/customers/{customer_id} -> by_customer() + entitlement view
    GET  /fleet/expiring?within_days=N  -> expiring_soon() + derived status
    GET  /fleet/showback                -> telemetry rollup per customer (honest silence)
    POST /fleet/issue                   -> IssuanceService.issue()
    POST /fleet/renew                   -> IssuanceService.renew()
    POST /fleet/revoke                  -> IssuanceService.revoke()  (ledger flag)

Data boundary (ADR 0009 §5) — **metadata only**. Every response model below is built
ONLY from ledger columns (license_id / customer_id / edition / entitled_modules /
quota_tier / dates / delivery / status) and telemetry *metadata* (last_seen, active
edition/modules, usage COUNTERS, showback rollup totals, over_license). No customer
business data, no PII, no tenant content is ever read or returned — this API has no
path to a customer database at all (push-only intake is the only inbound data).

Signing key custody (ADR 0009 §2). ``issue`` / ``renew`` need the offline ed25519
private key. The API NEVER stores it hot: ``create_fleet_api(...,
signing_key_pem=...)`` is the dev/test wiring, but in real ops the operator supplies
the key PER REQUEST (``signing_key_pem`` in the POST body, e.g. pasted/streamed from
an HSM or air-gapped keystore at issuance time) and it is dropped after the call. The
console "calls the signer, it does not run a hot key service."
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .issuance import IssuanceRequest, IssuanceService
from .models import IssuanceLedger
from .queries import by_customer, expiring_soon, roster
from .telemetry_queries import DeploymentSilence, last_seen_per_deployment, latest_record

try:  # pragma: no cover - typing convenience
    from sqlalchemy.orm import Session
except Exception:  # pragma: no cover
    Session = object  # type: ignore

# A no-arg factory returning a context-manager Session — same contract as intake.py.
SessionFactory = Callable[[], "Session"]


# --------------------------------------------------------------------------- #
# Derived status (ADR 0009 §4: roster shows current / expired / expiring)
# --------------------------------------------------------------------------- #
def derive_status(
    row: IssuanceLedger,
    *,
    expiring_within_days: int = 30,
    now: Optional[datetime] = None,
) -> str:
    """Derive a UI status for a ledger row from its expiry window (metadata only).

    Mirrors the in-deployment ``isa_common.license`` status semantics, but at the
    fleet/metadata layer (we never load the signed artifact here):

        revoked   — the ledger row is flagged revoked (#377)
        perpetual — no expires_at (never expires)
        expired   — past expires_at (the deployment's own grace handling is local)
        expiring  — within ``expiring_within_days`` of expiry
        current   — in-window, beyond the expiring threshold
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if row.revoked_at is not None:
        return "revoked"
    if row.expires_at is None:
        return "perpetual"
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        return "expired"
    if (expires - now).days <= expiring_within_days:
        return "expiring"
    return "current"


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Response models (metadata-only by construction)
# --------------------------------------------------------------------------- #
class RosterRow(BaseModel):
    """One roster entry — ledger metadata + derived status + last-seen/silence."""

    license_id: str
    customer_id: str
    edition: str
    entitled_modules: List[str]
    quota_tier: Optional[str] = None
    issued_at: Optional[str] = None
    not_before: Optional[str] = None
    expires_at: Optional[str] = None
    delivery: Optional[str] = None
    deployment_secret_id: Optional[str] = None
    status: str  # current | expiring | expired | perpetual | revoked
    revoked_at: Optional[str] = None
    revoked_reason: Optional[str] = None
    # Honest-silence enrichment (ADR 0009 §4): may be absent if telemetry isn't joined.
    last_seen: Optional[str] = None
    silent: Optional[bool] = None


def _row_to_model(
    row: IssuanceLedger,
    *,
    now: datetime,
    expiring_within_days: int,
    silence: Optional[DeploymentSilence] = None,
) -> RosterRow:
    return RosterRow(
        license_id=row.license_id,
        customer_id=row.customer_id,
        edition=row.edition,
        entitled_modules=list(row.entitled_modules or []),
        quota_tier=row.quota_tier,
        issued_at=_iso(row.issued_at),
        not_before=_iso(row.not_before),
        expires_at=_iso(row.expires_at),
        delivery=row.delivery,
        deployment_secret_id=row.deployment_secret_id,
        status=derive_status(row, expiring_within_days=expiring_within_days, now=now),
        revoked_at=_iso(row.revoked_at),
        revoked_reason=row.revoked_reason,
        last_seen=_iso(silence.last_seen) if silence else None,
        silent=silence.silent if silence else None,
    )


class CustomerView(BaseModel):
    """Per-customer entitlement view (ADR 0009 §4 entitlement view)."""

    customer_id: str
    licenses: List[RosterRow]
    # Union of entitled modules across the customer's current license(s).
    entitled_modules: List[str]


class ShowbackRow(BaseModel):
    """Per-customer showback rollup (ADR 0009 §4) — honest about telemetry state."""

    customer_id: str
    license_id: str
    edition: str
    # "realtime" (SaaS) | "last-upload" (connected on-prem) | "none" (silent/air-gapped)
    telemetry_state: str
    last_seen: Optional[str] = None
    source: Optional[str] = None  # the telemetry tier that last reported
    active_edition: Optional[str] = None
    active_modules: List[str] = Field(default_factory=list)
    module_usage: Dict[str, int] = Field(default_factory=dict)
    showback_totals: Dict[str, float] = Field(default_factory=dict)
    over_license: bool = False
    note: Optional[str] = None  # e.g. "no telemetry since 2026-01-02" for silent


# --------------------------------------------------------------------------- #
# Request models for write actions
# --------------------------------------------------------------------------- #
class IssueBody(BaseModel):
    """Issue request — mirrors IssuanceRequest + the operator-supplied signing key.

    ``signing_key_pem`` is optional ONLY because dev/test wiring may pin a key on the
    app (``create_fleet_api(signing_key_pem=...)``). In real ops the operator supplies
    it here, per request, from the offline keystore (ADR 0009 §2) and it is never
    persisted. ``extra="forbid"`` keeps the body metadata-only — no business data.
    """

    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(..., min_length=1)
    edition: str = Field(..., min_length=1)
    entitled_modules: List[str] = Field(default_factory=list)
    quota_tier: Optional[str] = None
    expires_at: Optional[str] = None
    not_before: Optional[str] = None
    grace_days: int = 0
    seats: int = -1
    license_id: Optional[str] = None
    delivery: Optional[str] = None
    signing_key_pem: Optional[str] = None  # PEM text; per-request offline key

    def to_request(self) -> IssuanceRequest:
        return IssuanceRequest(
            customer_id=self.customer_id,
            edition=self.edition,
            entitled_modules=list(self.entitled_modules),
            quota_tier=self.quota_tier,
            expires_at=self.expires_at,
            not_before=self.not_before,
            grace_days=self.grace_days,
            seats=self.seats,
            license_id=self.license_id,
            delivery=self.delivery,
        )


class RenewBody(IssueBody):
    """Renew request — an IssueBody plus the prior license_id being superseded."""

    prior_license_id: str = Field(..., min_length=1)


class RevokeBody(BaseModel):
    """Revoke request — a ledger flag, no signing (ADR 0009 §4 / future CRL note)."""

    model_config = ConfigDict(extra="forbid")

    license_id: str = Field(..., min_length=1)
    reason: Optional[str] = None


class IssueResponse(BaseModel):
    """The signed license body + the persisted ledger row (metadata) + cred pointer.

    The ``credential.secret`` (sensitive HMAC key) is NOT returned over this API: it
    must ride the offline secret bundle, not an HTTP response. Only the non-secret
    ``deployment_secret_id`` pointer is surfaced.
    """

    license: dict  # the signed license.json (operator delivers it offline)
    ledger_row: RosterRow
    deployment_secret_id: Optional[str] = None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _resolve_key(body_key: Optional[str], pinned: Optional[bytes]) -> bytes:
    """Resolve the signing key: per-request body key wins, else the pinned dev key."""
    if body_key:
        return body_key.encode("utf-8") if isinstance(body_key, str) else body_key
    if pinned is not None:
        return pinned
    raise HTTPException(
        status_code=400,
        detail="no signing key: supply signing_key_pem in the request "
        "(offline key, ADR 0009 §2) or configure the app with one",
    )


# --------------------------------------------------------------------------- #
# Router / app factory (intake.py style)
# --------------------------------------------------------------------------- #
def build_fleet_router(
    session_factory: SessionFactory,
    *,
    signing_key_pem: Optional[bytes] = None,
    expiring_within_days: int = 30,
) -> APIRouter:
    """Build the operator-facing fleet APIRouter bound to a session factory.

    ``signing_key_pem`` (optional) pins a signing key for dev/test; in real ops the
    key is supplied per-request in the issue/renew body and dropped after the call.
    """
    router = APIRouter(prefix="/fleet", tags=["fleet"])

    @router.get("/roster", response_model=List[RosterRow])
    async def get_roster(
        include_superseded: bool = Query(default=False),
        expiring_days: int = Query(default=expiring_within_days, ge=0),
    ) -> List[RosterRow]:
        """All current licenses × edition × derived status + last-seen/silence (§4)."""
        now = datetime.now(timezone.utc)
        with session_factory() as session:
            rows = roster(session, include_superseded=include_superseded)
            silence = {
                d.license_id: d
                for d in last_seen_per_deployment(
                    session, include_superseded=include_superseded
                )
            }
            return [
                _row_to_model(
                    r,
                    now=now,
                    expiring_within_days=expiring_days,
                    silence=silence.get(r.license_id),
                )
                for r in rows
            ]

    @router.get("/customers/{customer_id}", response_model=CustomerView)
    async def get_customer(
        customer_id: str,
        include_superseded: bool = Query(default=False),
    ) -> CustomerView:
        """One customer's current license(s) + entitlement view (§4)."""
        now = datetime.now(timezone.utc)
        with session_factory() as session:
            rows = by_customer(
                session, customer_id, include_superseded=include_superseded
            )
            if not rows:
                raise HTTPException(
                    status_code=404, detail=f"no licenses for customer {customer_id!r}"
                )
            silence = {
                d.license_id: d
                for d in last_seen_per_deployment(
                    session, include_superseded=include_superseded
                )
            }
            models = [
                _row_to_model(
                    r,
                    now=now,
                    expiring_within_days=expiring_within_days,
                    silence=silence.get(r.license_id),
                )
                for r in rows
            ]
            modules: List[str] = []
            for r in rows:
                for m in r.entitled_modules or []:
                    if m not in modules:
                        modules.append(m)
            return CustomerView(
                customer_id=customer_id, licenses=models, entitled_modules=modules
            )

    @router.get("/expiring", response_model=List[RosterRow])
    async def get_expiring(
        within_days: int = Query(default=30, ge=0),
    ) -> List[RosterRow]:
        """Current licenses expiring within N days (expiry calendar / alerts, §4)."""
        now = datetime.now(timezone.utc)
        with session_factory() as session:
            rows = expiring_soon(session, within_days=within_days, now=now)
            return [
                _row_to_model(r, now=now, expiring_within_days=within_days)
                for r in rows
            ]

    @router.get("/showback", response_model=List[ShowbackRow])
    async def get_showback(
        silent_after_days: Optional[int] = Query(default=None, ge=0),
    ) -> List[ShowbackRow]:
        """Per-customer showback rollup — honest about telemetry state (§4).

        Realtime/last-upload from the newest telemetry record; an explicit
        "no telemetry since X" for silent / air-gapped deployments (never fabricated).
        Metadata only: usage counters + showback rollup totals + over_license.
        """
        now = datetime.now(timezone.utc)
        out: List[ShowbackRow] = []
        with session_factory() as session:
            silences = last_seen_per_deployment(
                session, silent_after_days=silent_after_days, now=now
            )
            # Need edition per license for the rollup row; pull from the roster once.
            editions = {r.license_id: r.edition for r in roster(session)}
            for d in silences:
                rec = latest_record(session, d.license_id)
                if rec is None or d.silent:
                    # Honest "no telemetry" (never reported) OR stale past threshold.
                    note = (
                        f"no telemetry since {_iso(d.last_seen)}"
                        if d.last_seen is not None
                        else "no telemetry on record"
                    )
                    out.append(
                        ShowbackRow(
                            customer_id=d.customer_id,
                            license_id=d.license_id,
                            edition=editions.get(d.license_id, ""),
                            telemetry_state="none",
                            last_seen=_iso(d.last_seen),
                            note=note,
                        )
                    )
                    continue
                # Live telemetry: realtime (SaaS) vs last-upload (connected/offline).
                state = "realtime" if rec.source == "realtime" else "last-upload"
                out.append(
                    ShowbackRow(
                        customer_id=d.customer_id,
                        license_id=d.license_id,
                        edition=editions.get(d.license_id, rec.active_edition or ""),
                        telemetry_state=state,
                        last_seen=_iso(d.last_seen),
                        source=rec.source,
                        active_edition=rec.active_edition,
                        active_modules=list(rec.active_modules or []),
                        module_usage=dict(rec.module_usage or {}),
                        showback_totals=dict(rec.showback_totals or {}),
                        over_license=bool(rec.over_license),
                    )
                )
        return out

    @router.post("/issue", response_model=IssueResponse, status_code=201)
    async def post_issue(body: IssueBody) -> IssueResponse:
        """Sign + ledger-write a NEW license (ADR 0009 §2 issuance workflow)."""
        key = _resolve_key(body.signing_key_pem, signing_key_pem)
        now = datetime.now(timezone.utc)
        with session_factory() as session:
            svc = IssuanceService(session, key)
            try:
                result = svc.issue(body.to_request())
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return IssueResponse(
                license=result.license,
                ledger_row=_row_to_model(
                    result.ledger_row,
                    now=now,
                    expiring_within_days=expiring_within_days,
                ),
                deployment_secret_id=result.credential.deployment_secret_id,
            )

    @router.post("/renew", response_model=IssueResponse, status_code=201)
    async def post_renew(body: RenewBody) -> IssueResponse:
        """Issue a renewal, supersede the prior row (ADR 0009 §2)."""
        key = _resolve_key(body.signing_key_pem, signing_key_pem)
        now = datetime.now(timezone.utc)
        with session_factory() as session:
            svc = IssuanceService(session, key)
            try:
                result = svc.renew(body.prior_license_id, body.to_request())
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return IssueResponse(
                license=result.license,
                ledger_row=_row_to_model(
                    result.ledger_row,
                    now=now,
                    expiring_within_days=expiring_within_days,
                ),
                deployment_secret_id=result.credential.deployment_secret_id,
            )

    @router.post("/revoke", response_model=RosterRow)
    async def post_revoke(body: RevokeBody) -> RosterRow:
        """Revoke a license by flagging its ledger row (ADR 0009 §4; no signing).

        Online revocation / CRL is a FUTURE extension (ADR 0009): an offline-signed
        license can't be remotely killed, so this stamps a vendor-side ledger flag so
        the fleet view stops counting the row as live. No private key is needed.
        """
        now = datetime.now(timezone.utc)
        with session_factory() as session:
            # revoke() is a pure ledger flag — no signing key required (ADR 0009 §4).
            svc = IssuanceService(session)
            try:
                row = svc.revoke(body.license_id, reason=body.reason)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return _row_to_model(
                row, now=now, expiring_within_days=expiring_within_days
            )

    return router


def create_fleet_api(
    session_factory: SessionFactory,
    *,
    signing_key_pem: Optional[bytes] = None,
    expiring_within_days: int = 30,
) -> FastAPI:
    """App factory (isa_common ``create_*`` style) for the fleet console API.

    Returns a FastAPI app with the fleet router mounted + a liveness ``/healthz``.
    ``signing_key_pem`` is the dev/test convenience pin; production supplies the
    offline key per request (ADR 0009 §2). A real deployment would also call
    ``setup_observability(app, ...)`` and put this behind vendor-internal auth/VPN —
    it is NOT the internet-facing intake.
    """
    app = FastAPI(title="Fleet Console API", version="0.1.0")
    app.include_router(
        build_fleet_router(
            session_factory,
            signing_key_pem=signing_key_pem,
            expiring_within_days=expiring_within_days,
        )
    )

    @app.get("/healthz")
    async def healthz() -> dict:  # pragma: no cover - trivial liveness
        return {"status": "ok"}

    return app


def signature_bytes(signed_license: dict) -> bytes:  # pragma: no cover - helper
    """Decode the base64 ``signature`` of a signed license to raw bytes (helper)."""
    return base64.b64decode(signed_license["signature"])


__all__ = [
    "create_fleet_api",
    "build_fleet_router",
    "derive_status",
    "RosterRow",
    "CustomerView",
    "ShowbackRow",
    "IssueBody",
    "RenewBody",
    "RevokeBody",
    "IssueResponse",
]
