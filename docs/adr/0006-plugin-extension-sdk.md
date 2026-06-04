# ADR 0006 — Plugin / Extension SDK

> Status: Proposed (2026-06-04)
> Story: xenoISA/isA_Cloud#319 (plugin SDK / extension API), part of epic #313
> (profile/edition model). Supersedes the "issue #6 plugin API" note in
> `.claude/rules/white-label.md`.
> Sibling work: [[project-isa-editions]] (profile replaces fork),
> [[project-isa-maestro]] (first agent-plugin), the 24 customer-specific `sn_*`
> repos (first service-plugins).

## Context

Under the profile/edition model (ADR-less but documented in
`docs/saas-deployment/`), customer customization must happen by **extension, not
by forking the platform**. `isa_maestro` and the 24 customer-specific modules
(`sn_erp`, `sn_finance`, …) need to "plug in", not "change in". #319 is the
contract that makes that possible.

A 5-surface investigation (2026-06-04) found the platform **already has the
transport/registration seams** — they are just not unified, manifested, or
governed. Key finding: this is **unification + a missing manifest/registry**,
not greenfield.

### Existing seams (what already works)

| Extension kind | Existing seam | File evidence | State |
|---|---|---|---|
| **Tool / MCP plugin** | isA_MCP aggregator: `POST /api/v1/aggregator/servers` registers an external MCP server (org-scoped, persisted in `mcp.external_servers`, transport SSE/STDIO/HTTP), tools aggregated with `{server}__{tool}` namespace. Also `*_tools.py` auto-discovery. | `isA_MCP/services/aggregator_service/aggregator_service.py:130`, `server_registry.py:62-148`, `core/auto_discovery.py:572` | **Dynamic registration already works.** This is how Feishu MCP plugs in (#319→isa_maestro#18). |
| **Agent plugin** | isA_Agent_SDK A2A: `AgentServiceBuilder` stands up an agent service; `A2AAgentCard` self-describes at `/.well-known/agent-card.json`; `TeamRegistry.discover(urls)` / `DynamicTeamRegistry` + `TeamProvider` for discovery; OAuth2 scopes `a2a.invoke`/`a2a.tasks.*`; startup/shutdown hooks. | `isA_Agent_SDK/a2a.py:75-128,242-605`, `service_builder.py:166-336`, `delegation/registry.py:101-384` | **Peer-to-peer works; no central registry.** This is how `isa_maestro` plugs in. |
| **Service / app plugin** | isa_common Consul self-registration (`ConsulRegistry.register()` with `meta`), → APISIX route auto-sync CronJob every 5min reads `meta.api_path` → live gateway route. isA_OS pool_manager build/deploy: upload tar.gz → validate → gen Dockerfile → build image → semver version → Argo Rollout (canary/blue-green). | `isA_Cloud/isA_common/isa_common/consul_client.py:230-356`, `docs/apisix_route_consul_sync.md`, `isA_OS/.../pool_manager/src/deployments/build_service.py:137-296`, `deploy_service.py:155-233` | **Self-register → auto-exposed already works.** This is how `sn_erp` plugs in. |
| **Client / app-SDK plugin** | isA_App_SDK `IsAClient` — **monolithic, 37 hardcoded services, NO seam.** | `isA_App_SDK/packages/core/src/IsAClient.ts:199-319` | **Missing.** Needs new `@xenoisa/plugin` package. |

### What's missing everywhere (the unifying gaps)

Every investigation independently surfaced the same four gaps:
1. **No plugin manifest** — extensions self-describe ad-hoc (opaque A2A `skills`,
   Consul `meta`, MCP server config). No standard declaration of id / version /
   kind / capabilities / scopes / dependencies.
2. **No central plugin registry** — no single place that knows what is installed,
   enabled, by which tenant. (MCP aggregator's `external_servers` table is the
   closest; it's per-surface, not platform-wide.)
3. **No namespacing / capability / permission model** — tool-name collisions,
   no per-plugin or per-tenant isolation, no "which plugin owns this / what may
   it do".
4. **No client-side seam** — `IsAClient` can't accept a runtime-registered
   service/middleware/event.

## Decision

Define a **single Plugin contract** (one manifest, one registry) that **routes
each plugin KIND to its existing seam** rather than building new transport.
Don't reinvent A2A / MCP-aggregator / Consul — manifest + register on top of them.

### 1. One manifest, four kinds

`plugin.yaml` (language-neutral), shared shape across kinds:

```yaml
id: sn_erp                      # stable, unique; customer-specific never synced
name: "SN ERP Service"
version: 1.2.0
kind: service                   # one of: tool | agent | service | client
capabilities: [...]             # kind-specific (tools / skills / routes / services)
scopes: [a2a.invoke, ...]       # permissions requested
tenant: customer-sn | platform  # isolation / ownership
dependencies: [sn_auth>=1.0]    # other plugins
```

Kind → existing seam (the binding the platform already has):
- `tool`   → register via isA_MCP aggregator (`/api/v1/aggregator/servers`) or `*_tools.py`.
- `agent`  → stand up via `AgentServiceBuilder`; manifest's `capabilities` become the `A2AAgentCard.skills` (now SCHEMA'd, not opaque).
- `service`→ `ConsulRegistry.register()` with manifest fields mapped to `meta` (`plugin_id`, `plugin_kind`, `tenant`, `capabilities`); APISIX auto-route as today; optional pool_manager build/deploy pipeline for packaging.
- `client` → register into the new `@xenoisa/plugin` registry in `IsAClient`.

### 2. Central registry

A thin **Plugin Registry** service (extend isA_MCP's `external_servers` pattern,
or a small new table in isA_Cloud) that records every plugin's manifest, kind,
tenant, status (installed/enabled/disabled), and the seam it bound to. Backed by
Consul tags for discovery. Single source of truth for "what's plugged in".

### 3. Namespacing, capability, permission (uniform)

- **Namespace**: every plugin gets `plugin_id`; tools/routes/services are scoped
  `plugin_id::name` (MCP already prefixes `server__tool` — generalize it).
- **Capability/permission**: manifest `scopes` checked at the seam's existing auth
  point (A2A token validator scopes already exist; Consul `meta.auth_required`;
  MCP per-server). Tenant from manifest → multi-tenant isolation (ties to the
  SaaS multi-tenant story).

### 4. Client-side: new `@xenoisa/plugin` package

`PluginRegistry` + `PluginManifest` + `PluginContext` (service / middleware /
event capabilities, lifecycle init/ready/dispose). `IsAClient` gains
`config.plugins`, `getPlugin<T>()`, `initPlugins()`. (Detailed shape in the
isA_App_SDK investigation; out of scope for the backend MVP.)

## Reuse, don't reinvent (mapping)

| Need | Reuse | Don't build |
|---|---|---|
| Agent transport/discovery | `AgentServiceBuilder`, `A2AAgentCard`, `TeamProvider` | a new agent RPC/registry |
| Tool/server registration | MCP aggregator `register_server` + `external_servers` | a new tool bus |
| Service register → expose | `ConsulRegistry` + APISIX route-sync | a new gateway |
| Packaging/build/deploy | pool_manager upload→build→version→rollout | a new CI for plugins |
| Scaffolding | extend `isA_Orch/scaffold.py` (today: test dirs only) | a new generator |

## Phased plan (stories under #319)

1. **Manifest spec** — define `plugin.yaml` schema (Pydantic in `isa_common` +
   TS type) covering all 4 kinds. Smallest unblocking deliverable.
2. **Service-plugin path** (highest value, unblocks the 24 customer modules):
   `isa_common` helper `PluginRegistry(ConsulRegistry)` mapping manifest→`meta`;
   document "drop a `plugin.yaml`, self-register, get an APISIX route".
3. **Agent-plugin path** (unblocks `isa_maestro`): manifest→`A2AAgentCard.skills`
   schema; optional central `TeamProvider` backed by the registry.
4. **Tool-plugin path**: manifest wrapper over MCP aggregator register; covers
   Feishu MCP (isa_maestro#18).
5. **Central registry** service + namespacing/capability enforcement.
6. **`@xenoisa/plugin`** TS package + `IsAClient` integration.
7. **Scaffold**: `isa_orch scaffold plugin <kind>` generates manifest + skeleton.

## Consequences

- **Positive**: customer modules and `isa_maestro` plug in with no platform fork;
  most transport already exists so MVP is small; manifest gives governance
  (versioning, scopes, tenant) the ad-hoc seams lack; aligns with editions +
  multi-tenant work.
- **Negative / risk**: four kinds means the manifest must stay coherent without
  becoming a lowest-common-denominator blob — keep kind-specific `capabilities`
  typed per kind. Central registry adds a component to operate. Namespacing
  retrofit touches MCP tool naming (back-compat needed).
- **Out of scope here**: sandboxing/hot-reload (later), marketplace/distribution
  (later), full client-side plugin runtime (#319 phase 6).

## Open questions

- Registry home: extend isA_MCP `external_servers`, or a new isA_Cloud service?
- Manifest single-file for all kinds vs per-kind variants sharing a core?
- Do customer `service` plugins need the pool_manager build pipeline, or just
  Consul self-registration (they own their own deploy)?
