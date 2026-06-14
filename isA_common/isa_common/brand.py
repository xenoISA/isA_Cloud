#!/usr/bin/env python3
"""
Brand configuration — the white-label "brand as config" contract.

Under the profile/edition model (see isA_Cloud/docs/saas-deployment/), the brand
that a customer SEES is a deploy-time config value, NOT a source rewrite. Internal
identifiers (isa_ packages, ISA_ env vars, class names, k8s namespaces) stay isa_
forever — this module does NOT touch them.

Every Python backend imports isa_common, so this single definition covers
Cloud / MCP / Model / Agent / Data / user / Creative / Marketing / Orch /
Training / Mate. Read once at startup, then use the values for customer-visible
surfaces: FastAPI title/description, A2A provider_org, observability service name,
emails, public URLs.

Defaults preserve current "isA" behaviour, so this is a zero-behaviour-change
addition until BRAND_* env vars are set (e.g. in the SN edition's values).

Usage:
    from isa_common import get_brand

    brand = get_brand()
    app = FastAPI(title=brand.openapi_title("Model Serving API"),
                  description=brand.openapi_description)
    setup_observability(app, service_name=brand.service_name("Model"))
    card = A2AAgentCard(provider_org=brand.org_name, ...)
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BrandConfig:
    """Customer-visible brand identity. Internal isa_ identifiers are unaffected."""

    # Core identity
    name: str = "isA"  # short brand word (logos, A2A short)
    display_name: str = "isA Platform"  # full product name (titles, headers)
    org_name: str = "isA"  # A2A provider_org / agent-card org

    # Contact + hosting (customer-visible)
    support_email: str = "dev@iapro.ai"
    cookie_domain: str = ".iapro.ai"  # auth cookie root (real prod domain)
    primary_host: str = "isa.dev"
    docs_url: str = "https://docs.isa.dev"

    # Optional surfaces
    agent_persona_name: Optional[str] = None  # agent system-prompt persona (e.g. "Mate")
    cli_name: Optional[str] = None  # CLI command name (e.g. "isa-vibe")

    # ------------------------------------------------------------------ helpers
    def openapi_title(self, service_suffix: str = "") -> str:
        """FastAPI title, e.g. 'isA Platform — Model Serving API'."""
        return f"{self.display_name} — {service_suffix}" if service_suffix else self.display_name

    @property
    def openapi_description(self) -> str:
        return f"{self.display_name} service API"

    def service_name(self, component: str) -> str:
        """Observability/OTEL/logger service name, e.g. 'isA_Model'.

        Kept as `<name>_<Component>` so existing dashboards keep working under the
        default brand; SN deployments get `SN_Model` by setting BRAND_NAME=SN.
        """
        return f"{self.name}_{component}"

    @classmethod
    def from_env(cls) -> "BrandConfig":
        """Load from BRAND_* env vars (set per edition in Helm values/ConfigMap)."""
        return cls(
            name=os.getenv("BRAND_NAME", "isA"),
            display_name=os.getenv("BRAND_DISPLAY_NAME", "isA Platform"),
            org_name=os.getenv("BRAND_ORG_NAME", os.getenv("BRAND_NAME", "isA")),
            support_email=os.getenv("BRAND_SUPPORT_EMAIL", "dev@iapro.ai"),
            cookie_domain=os.getenv("AUTH_COOKIE_DOMAIN", ".iapro.ai"),
            primary_host=os.getenv("BRAND_PRIMARY_HOST", "isa.dev"),
            docs_url=os.getenv("BRAND_DOCS_URL", "https://docs.isa.dev"),
            agent_persona_name=os.getenv("BRAND_AGENT_NAME") or None,
            cli_name=os.getenv("BRAND_CLI_NAME") or None,
        )


# Module-level singleton — read env once at import, reuse everywhere.
_brand: Optional[BrandConfig] = None


def get_brand() -> BrandConfig:
    """Return the process-wide BrandConfig (loaded from env on first call)."""
    global _brand
    if _brand is None:
        _brand = BrandConfig.from_env()
    return _brand
