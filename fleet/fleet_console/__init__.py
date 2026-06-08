"""fleet_console — vendor-side Fleet / License Console (ADR 0009).

This package is the *vendor* half of the licensing system. ADR 0008 issues and
enforces a license *inside one deployment*; ADR 0009 aggregates issuance (and,
later, opt-in telemetry) on the *vendor* side into one fleet view across ALL
customers — on-prem and SaaS.

Data boundary (ADR 0009 §5): this component holds fleet **metadata only** — the
license-issuance ledger. It NEVER connects to a customer database and NEVER holds
customer business data. It is a separate deployment from isA_Admin.

Public surface
--------------
- :mod:`fleet_console.models`   — the SQLAlchemy ``IssuanceLedger`` model + ``Base``.
- :mod:`fleet_console.issuance` — :class:`IssuanceService` / :func:`issue_license`,
  the workflow that signs (via ``isa_common.license_sign``) AND writes the ledger
  row atomically.
- :mod:`fleet_console.queries` — read-side helpers backing the fleet UI (#377):
  roster, by-customer, expiring-soon.
- :mod:`fleet_console.intake`   — the telemetry intake endpoint (#375): HMAC-
  authenticated, metadata-only, realtime/periodic POST + air-gapped file upload.
- :mod:`fleet_console.telemetry_models`  — the ``TelemetryRecord`` store (#375).
- :mod:`fleet_console.telemetry_queries` — honest-silence / last-seen reporting (#375).
- :mod:`fleet_console.telemetry_credential` — HMAC verify (#374 contract; stub here).
"""

from .intake import (
    TelemetryPayload,
    build_intake_router,
    create_intake_app,
)
from .issuance import (
    IssuanceRequest,
    IssuanceResult,
    IssuanceService,
    issue_license,
    renew_license,
)
from .models import Base, IssuanceLedger
from .queries import by_customer, expiring_soon, roster
from .telemetry_models import TelemetryRecord
from .telemetry_queries import (
    DeploymentSilence,
    last_seen_per_deployment,
    latest_record,
)

__all__ = [
    "Base",
    "IssuanceLedger",
    "IssuanceRequest",
    "IssuanceResult",
    "IssuanceService",
    "issue_license",
    "renew_license",
    "roster",
    "by_customer",
    "expiring_soon",
    # telemetry intake (#375)
    "TelemetryPayload",
    "build_intake_router",
    "create_intake_app",
    "TelemetryRecord",
    "DeploymentSilence",
    "last_seen_per_deployment",
    "latest_record",
]
