# Per-Edition Bill of Materials (what each edition ships)

> The definitive "SaaS ships X / SN ships Y" list. Pairs with `edition-boundary.md`
> (repo taxonomy), the `deployments/editions/` Helm overlays (the toggles), and
> `isa_common.edition` (the runtime flags). Source of truth for what a given
> edition actually deploys.
> Updated 2026-06-05 (#332).

## Editions

| Edition | `ISA_EDITION` | Who | Brand |
|---|---|---|---|
| **SaaS** | `saas` | isA self-hosted, multi-tenant developers | isA |
| **Enterprise full (SN)** | `on-prem-full` | white-label customer (SN), single-tenant | SN (white-label) |
| **Enterprise lite** | `on-prem-lite` | smaller on-prem customer | per-customer |

## Common core — ALL editions

Every edition deploys the **platform**:

- **17 platform services / mirrors** (the sync/release set — see `edition-boundary.md` §A):
  agent, agent_sdk, app_sdk, cloud, console, **admin**, user, mcp, model, data, mate,
  creative, marketing, docs, os, training, vibe. (Images: see
  `deployments/release/platform-services.yaml` — 14 ship container images; app_sdk/vibe/cloud are libs/tooling.)
- **Lightweight data stores**: PostgreSQL, Redis, MinIO, DuckDB, Qdrant.
- **Gateway + discovery**: APISIX, Consul.
- **Metering** (core, always on — emits usage events regardless of edition).

## Edition deltas (what differs)

| Component / capability | SaaS | Enterprise full (SN) | Enterprise lite |
|---|:---:|:---:|:---:|
| Platform core (above) | ✅ | ✅ | ✅ |
| Metering (usage events) | ✅ | ✅ | ✅ |
| **Multi-tenant control plane** | ✅ | ❌ (single-tenant) | ❌ |
| **Charging / external billing** | ✅ (revenue) | ❌ → **showback** (internal cost) | ❌ → showback |
| **Big-data umbrella** (Kafka, Flink, StarRocks, Iceberg, **Dataphin**) | ❌ | ✅ | ❌ |
| **Customer-specific modules** | ❌ | ✅ (SN's set, below) | ❌ |
| Brand | isA | SN (white-label) | per-customer |
| Delivery | isA cloud / GitOps | offline bundle → customer Harbor → helm (see `release/SN-DELIVERY.md`) | offline bundle → helm |

Toggles are enforced by `isa_common.edition` flags (`bigdata_enabled`,
`metering_enabled`, `charging_enabled`, `multi_tenant`) + the `deployments/editions/`
values; the big-data umbrella is a **separate Helm release** installed only when
`bigdata.enabled` (full edition).

## SN-only: customer-specific modules (Enterprise full)

Beyond the platform, SN deploys its **24 customer-specific modules** (no isA upstream —
see `edition-boundary.md` §B; these are SN business systems, NOT shipped to SaaS or lite):

`sn_erp · sn_mes · sn_plm · sn_srm · sn_scm_tower · sn_finance · sn_commerce ·
sn_seeyon · sn_feishu · sn_mdm · sn_maestro · sn_aom · sn_arch · sn_iam ·
sn_commercial_tower · sn_ipd_tower · sn_operation_tower · sn_plan · sn_pxm ·
sn_tower_kit · sn_dtc · sn_gcp · SN-BI · SN-TROBS`

These live only in the SN environment and are delivered/operated separately from the
platform release (they consume the platform via the plugin SDK / public APIs, not by
forking it).

## isA-only (not in any customer edition)

Per #324: `isA_IDE`, `isA_Orch`, `isA_Reading`, `isA_Trade`, `isA_Chain`,
`isA_Frame(EmoFrame)` are **isA-only products/tooling** — not in any customer edition.
(`isA_Admin` was promoted to the platform set, so it IS in all editions.)

## Quick answer

- **SaaS** = platform core (17) + multi-tenant + charging, **no** big-data, **no** customer modules, isA brand.
- **SN (on-prem-full)** = platform core (17) + big-data (Dataphin) + the 24 customer modules, single-tenant, showback, SN brand.
- **Enterprise lite** = platform core (17) only, no big-data / multi-tenant / charging / customer modules.
