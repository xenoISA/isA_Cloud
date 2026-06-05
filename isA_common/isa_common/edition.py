#!/usr/bin/env python3
"""
Edition configuration — the runtime "which edition + which features" contract.

Under the profile/edition model (see ADR 0006 and isA_Cloud/docs/saas-deployment/),
the platform ships in a few deployment EDITIONS — the managed SaaS, a full
on-prem install, and a lite on-prem install — and each edition turns a small set
of feature modules on or off (big-data analytics, metering, charging,
multi-tenancy). This module is the RUNTIME half of that story: the Helm edition
profiles (#316) set the env, and every Python backend reads it back here to know
what is active. Internal isa_ identifiers are unaffected — this is config, not a
source rewrite.

Every Python backend imports isa_common, so this single definition covers
Cloud / MCP / Model / Agent / Data / user / Creative / Marketing / Orch /
Training / Mate. Read once at startup, then branch on the flags to gate optional
subsystems (e.g. skip the metering pipeline on a lite install, disable charging
on-prem, fan out per-tenant only when multi_tenant is on).

Defaults are conservative: with no env set the process behaves as an on-prem-lite
install (everything customer-billing-related off, metering on as a core signal),
so this is a safe addition until ISA_EDITION / ISA_*_ENABLED env vars are set
(e.g. in the SaaS edition's Helm values).

Usage:
    from isa_common import get_edition

    edition = get_edition()
    if edition.charging_enabled:
        await charge_org(org_id, usage)
    if edition.multi_tenant:
        scope = f"tenant:{tenant_id}"
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class EditionType(str, Enum):
    """The deployment edition a process is running under."""

    SAAS = "saas"
    ON_PREM_FULL = "on-prem-full"
    ON_PREM_LITE = "on-prem-lite"


# Per-edition feature defaults. Metering is a core/always-on signal by default,
# but is kept as a flag for completeness (and per-flag override below).
_EDITION_DEFAULTS: Dict[EditionType, Dict[str, bool]] = {
    EditionType.SAAS: {
        "bigdata_enabled": False,
        "metering_enabled": True,
        "charging_enabled": True,
        "multi_tenant": True,
    },
    EditionType.ON_PREM_FULL: {
        "bigdata_enabled": True,
        "metering_enabled": True,
        "charging_enabled": False,
        "multi_tenant": False,
    },
    EditionType.ON_PREM_LITE: {
        "bigdata_enabled": False,
        "metering_enabled": True,
        "charging_enabled": False,
        "multi_tenant": False,
    },
}


def _parse_bool(value: Optional[str]) -> Optional[bool]:
    """Parse a tri-state env flag.

    Returns True for "true"/"1"/"yes", False for "false"/"0"/"no" (case- and
    whitespace-insensitive), and None when unset/blank/unrecognised so callers
    can fall back to the edition default.
    """
    if value is None:
        return None
    token = value.strip().lower()
    if token in ("true", "1", "yes"):
        return True
    if token in ("false", "0", "no"):
        return False
    return None


@dataclass(frozen=True)
class EditionConfig:
    """Active deployment edition + the feature modules it enables."""

    edition: EditionType
    bigdata_enabled: bool
    metering_enabled: bool
    charging_enabled: bool
    multi_tenant: bool

    @classmethod
    def from_env(cls) -> "EditionConfig":
        """Load from ISA_EDITION + per-flag ISA_*_ENABLED env vars.

        ISA_EDITION selects the edition (default / unknown / blank →
        on-prem-lite). The edition's matrix supplies the feature defaults, then
        each flag may be explicitly overridden via its own env var when set:
        ISA_BIGDATA_ENABLED, ISA_METERING_ENABLED, ISA_CHARGING_ENABLED,
        ISA_MULTI_TENANT. Unset overrides keep the edition default.
        """
        raw = (os.getenv("ISA_EDITION") or "").strip().lower()
        try:
            edition = EditionType(raw)
        except ValueError:
            # Unknown or blank ISA_EDITION → fall back to the safe lite default.
            edition = EditionType.ON_PREM_LITE

        defaults = _EDITION_DEFAULTS[edition]

        def resolve(flag: str, env_var: str) -> bool:
            override = _parse_bool(os.getenv(env_var))
            return override if override is not None else defaults[flag]

        return cls(
            edition=edition,
            bigdata_enabled=resolve("bigdata_enabled", "ISA_BIGDATA_ENABLED"),
            metering_enabled=resolve("metering_enabled", "ISA_METERING_ENABLED"),
            charging_enabled=resolve("charging_enabled", "ISA_CHARGING_ENABLED"),
            multi_tenant=resolve("multi_tenant", "ISA_MULTI_TENANT"),
        )


# Module-level singleton — read env once at import, reuse everywhere.
_edition: Optional[EditionConfig] = None


def get_edition() -> EditionConfig:
    """Return the process-wide EditionConfig (loaded from env on first call)."""
    global _edition
    if _edition is None:
        _edition = EditionConfig.from_env()
    return _edition
