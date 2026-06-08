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
- :mod:`fleet_console.telemetry_credential` — per-deployment telemetry credential
  (#374, ADR 0009 §3): minted at issuance, its id written to the ledger row and its
  HMAC secret stored in an isolated ``deployment_secret`` table; defines the
  ``verify_telemetry_hmac`` scheme the intake endpoint (#375) calls.
"""

from .issuance import (
    IssuanceRequest,
    IssuanceResult,
    IssuanceService,
    issue_license,
    renew_license,
)
from .models import Base, IssuanceLedger
from .queries import by_customer, expiring_soon, roster
from .telemetry_credential import (
    DeploymentSecret,
    TelemetryCredential,
    get_secret,
    mint_credential,
    persist_credential,
    rotate_credential,
    secret_for_license,
    sign_telemetry,
    verify_telemetry_hmac,
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
    # #374 — telemetry credential
    "DeploymentSecret",
    "TelemetryCredential",
    "mint_credential",
    "persist_credential",
    "get_secret",
    "secret_for_license",
    "sign_telemetry",
    "verify_telemetry_hmac",
    "rotate_credential",
]
