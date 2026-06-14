#!/usr/bin/env python3
"""
Plugin / Extension SDK — manifest contract + service-plugin registration.

Implements ADR 0006 (isA_Cloud/docs/adr/0006-plugin-extension-sdk.md): customer
modules (sn_erp, ...) and platform extensions (isa_maestro) plug in by
*extension*, not by forking the platform. The contract is ONE manifest
(`plugin.yaml`) with FOUR kinds, each routed to a transport seam the platform
already has:

    kind=tool    -> isA_MCP aggregator (POST /api/v1/aggregator/servers)
    kind=agent   -> isA_Agent_SDK AgentServiceBuilder + A2A agent-card
    kind=service -> Consul self-registration -> APISIX auto-route   <-- THIS MODULE
    kind=client  -> @xenoisa/plugin (TS, separate package)

Phase 1 (manifest) + Phase 2 (service-plugin path) live here. A service plugin
drops a `plugin.yaml`, calls PluginServiceRegistry(...).register(), and the
existing Consul->APISIX route-sync exposes it through the gateway — no platform
fork, no new transport.

Usage (service plugin):
    from isa_common import PluginServiceRegistry

    reg = PluginServiceRegistry.from_manifest_file("plugin.yaml",
                                                   consul_host="consul")
    reg.register()        # self-register in Consul; APISIX picks it up
    reg.start_maintenance()
    ...
    reg.deregister()
"""

import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from .consul_client import ConsulRegistry


class PluginKind(str, Enum):
    """The four extension kinds, each bound to an existing platform seam."""

    TOOL = "tool"  # MCP tools / external MCP server
    AGENT = "agent"  # A2A agent service (e.g. isa_maestro)
    SERVICE = "service"  # HTTP microservice (e.g. sn_erp) via Consul + APISIX
    CLIENT = "client"  # client-side SDK extension (@xenoisa/plugin)


class ServiceBinding(BaseModel):
    """kind=service binding — what Consul/APISIX need to expose the plugin."""

    api_path: str = Field(..., description="Gateway path prefix, e.g. /api/v1/plugins/erp")
    port: int = Field(..., ge=1, le=65535)
    auth_required: bool = True
    health_check_type: str = "ttl"  # ttl | http

    @field_validator("api_path")
    @classmethod
    def _path_leading_slash(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError("api_path must start with '/'")
        return v.rstrip("/")

    @field_validator("health_check_type")
    @classmethod
    def _health_kind(cls, v: str) -> str:
        if v not in ("ttl", "http"):
            raise ValueError("health_check_type must be 'ttl' or 'http'")
        return v


class PluginManifest(BaseModel):
    """The `plugin.yaml` contract — shared core + kind-specific binding.

    Single-file for all kinds (ADR 0006 decision): the shared fields below apply
    to every plugin; `service`/`capabilities` carry the kind-specific detail.
    """

    id: str = Field(..., description="Stable unique id, lowercase/underscore (e.g. sn_erp)")
    name: str
    version: str
    kind: PluginKind
    description: str = ""
    tenant: str = "platform"  # 'platform' or a customer id (e.g. customer-sn)
    scopes: List[str] = Field(default_factory=list)  # permissions requested
    dependencies: List[str] = Field(default_factory=list)  # other plugin ids/constraints
    capabilities: Dict[str, Any] = Field(default_factory=dict)  # kind-specific (tools/skills/...)

    # kind=service binding (required when kind == service)
    service: Optional[ServiceBinding] = None

    @field_validator("id")
    @classmethod
    def _id_shape(cls, v: str) -> str:
        if not v or not all(c.islower() or c.isdigit() or c == "_" for c in v):
            raise ValueError("id must be lowercase letters/digits/underscores")
        return v

    @model_validator(mode="after")
    def _require_service_binding(self) -> "PluginManifest":
        if self.kind == PluginKind.SERVICE and self.service is None:
            raise ValueError("kind=service requires a `service:` binding block")
        return self


def load_manifest(source: Union[str, Path, Dict[str, Any]]) -> PluginManifest:
    """Load + validate a plugin manifest from a YAML file path or a dict."""
    if isinstance(source, dict):
        return PluginManifest.model_validate(source)
    import yaml  # lazy: keep isa_common importable in runtimes without pyyaml

    data = yaml.safe_load(Path(source).read_text())
    if not isinstance(data, dict):
        raise ValueError(f"plugin manifest {source} is not a YAML mapping")
    return PluginManifest.model_validate(data)


class PluginServiceRegistry:
    """Register a kind=service plugin with Consul so APISIX auto-exposes it.

    Maps the manifest onto Consul `meta`/`tags` (the existing APISIX route-sync
    reads `meta.api_path`). This is the seam customer service modules use instead
    of forking the platform.
    """

    def __init__(
        self,
        manifest: PluginManifest,
        *,
        consul_host: str = "localhost",
        consul_port: int = 8500,
        service_host: Optional[str] = None,
    ):
        if manifest.kind != PluginKind.SERVICE:
            raise ValueError(
                f"PluginServiceRegistry requires kind=service, got '{manifest.kind.value}'. "
                f"Use the A2A/MCP/client seam for that kind (see ADR 0006)."
            )
        assert manifest.service is not None  # guaranteed by manifest validator
        svc = manifest.service
        self.manifest = manifest

        meta: Dict[str, str] = {
            "plugin_id": manifest.id,
            "plugin_kind": manifest.kind.value,
            "plugin_version": manifest.version,
            "tenant": manifest.tenant,
            "api_path": svc.api_path,  # drives APISIX route creation
            "auth_required": "true" if svc.auth_required else "false",
        }
        if manifest.scopes:
            meta["plugin_scopes"] = ",".join(manifest.scopes)
        if manifest.capabilities:
            meta["plugin_capabilities"] = json.dumps(manifest.capabilities, separators=(",", ":"))

        self._registry = ConsulRegistry(
            service_name=manifest.id,
            service_port=svc.port,
            consul_host=consul_host,
            consul_port=consul_port,
            service_host=service_host,
            tags=["plugin", f"kind:{manifest.kind.value}", f"tenant:{manifest.tenant}"],
            meta=meta,
            health_check_type=svc.health_check_type,
        )

    @classmethod
    def from_manifest_file(cls, path: Union[str, Path], **kwargs: Any) -> "PluginServiceRegistry":
        return cls(load_manifest(path), **kwargs)

    def register(self, cleanup_stale: bool = True) -> bool:
        return self._registry.register(cleanup_stale=cleanup_stale)

    def deregister(self) -> bool:
        return self._registry.deregister()

    def start_maintenance(self) -> None:
        return self._registry.start_maintenance()

    @property
    def consul_registry(self) -> ConsulRegistry:
        """Escape hatch to the underlying ConsulRegistry (KV config, discovery)."""
        return self._registry
