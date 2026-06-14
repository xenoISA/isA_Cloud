# ADR 0010 — isa_data_product: tower framework, tower = profile

> Status: Proposed (2026-06-11)
> Story: TBD. Extends the fork→profile philosophy (ADR 0006 editions, ADR 0008/0009
> licensing) to the **data-product / "tower" layer**. Grounded in a structural survey
> of `sn_commercial_tower`, `sn_scm_tower`, `sn_ipd_tower`, `sn_operation_tower`,
> `sn_dtc`, and `isA_Data` (2026-06-11). Sibling: `docs/saas-deployment/edition-boundary.md`,
> `fork-to-profile-decommission.md`.

## Context

SN ships several **"tower"** repos — domain dashboards + data pipelines over a
business area: `sn_commercial_tower` (commercial), `sn_scm_tower` (supply chain),
`sn_ipd_tower` (product dev), `sn_operation_tower` (operations), and `sn_dtc`
(DTC analytics). Today each is a **bespoke per-customer repo**. Three observations
make that the wrong shape:

1. **They are the same 5-stage product, at different maturity.** Every tower
   instantiates one spine: **source registry/collectors → data-product contracts →
   medallion transform → product serving API → dashboard + agentic overlay.**
   `sn_commercial_tower` is the full reference; `sn_scm_tower` is frontend+BFF that
   already *delegates its data to isA_Data*; `sn_ipd_tower` and `sn_operation_tower`
   are **literal skeleton clones** (identical `docs/product/` filenames, stub UI) —
   someone already templated it; `sn_dtc` is the same spine on a different substrate.

2. **isA_Data already implements ~60–70% of the platform half.** It has the
   adapter/collector framework (`src/adapters/*`), the **data-product contract
   schemas + certification/governance/lineage/quality/catalog** (`src/contracts/
   data_products/*`, `framework.py`), and **per-tower product services** already
   served at `GET /api/v1/data/products/{tower}/{product_id}` (`scm_products.py`,
   `commerce_products.py`). The towers are increasingly thin consumers of it.

3. **The only real divergence is substrate, not shape.** The SN towers run
   Dataphin + StarRocks/Iceberg + Kafka/Flink + Frappe; `sn_dtc` runs BigQuery +
   dbt + GCP. Same logical pipeline (medallion + contracts + serving + Next/Recharts
   dashboard), different engine.

Maintaining N bespoke towers means re-building the same spine N times and forking
the platform per domain — the exact anti-pattern the editions/profile model removed
for deployment.

## Decision

Extract a first-class **`isa_data_product`** capability in the isA platform, built
on isA_Data, where **a tower is a *profile*, not a repo**. A data product / tower is
**declared** (a manifest) and composed from shared framework modules; the bespoke
per-tower repos collapse to *a domain profile + a thin BFF*.

### 1. The shared spine (framework modules, in isA upstream)
| Stage | Framework module (extract from) | Per-tower supplies |
|---|---|---|
| **Ingest** | source-registry + vendor/adapter framework (`isA_Data/src/adapters`, commercial `data_platform/collectors` + `vendor_framework.py`) | which sources/connectors (`sources/*.yaml`) |
| **Contracts** | data-product contract schemas + certification/quality (`isA_Data/src/contracts/data_products`) | canonical dims/facts + product list (`models/*.yaml`) |
| **Transform** | medallion pipeline runner (ODS→DWD→DWS→ADS / staging→marts) — **pluggable engine** | domain transforms |
| **Serving** | product API `/api/v1/data/products/{tower}/{id}` (already in isA_Data) | product IDs |
| **Dashboard + agents** | dashboard SDK (generalize `sn-tower-kit`) + standard `api/bff/*`, `api/agents/*`, `api/stream/*`, MCP module | domain pages + BFF route names |

### 2. Tower = profile (manifest-driven)
A tower instance is a declared profile, not a fork:
```yaml
# data-product profile (per tower/customer)
tower: commercial
sources:   [amazon_ads, walmart_connect, shopify, internal_erp, ...]   # → collector framework
canonical: { dimensions: [...], facts: [...] }                         # → contract framework
products:  [com_pricing, com_elasticity, com_pmf, ...]                 # → serving API
dashboard: { pages: [pricing, advertising, channel, ...] }            # → dashboard SDK
substrate: dataphin            # or: bigquery (see §3)
```
`sn_ipd_tower`/`sn_operation_tower` already work this way in spirit (PRD + domain
config + stub UI) — this just makes the framework real instead of clone-and-edit.

### 3. Pluggable lake/transform substrate (the load-bearing decision)
The framework must treat the **lake + transform engine as a pluggable backend** —
the one place the towers genuinely differ. The seam already exists: the commercial
tower's `commercial_data` service has a `mock | sn-data | live` backend switch and a
`select_lake_backend()` "swap point". Generalize it to a `SubstrateAdapter`:
- **Dataphin/StarRocks/Iceberg** adapter (the SN on-prem towers).
- **dbt/BigQuery** adapter (the `sn_dtc`-style cloud-native deployments).
Forcing a single substrate would make `sn_dtc` resist; a pluggable adapter fits all five.

### 4. How each tower maps
- **commercial** → the reference the framework is *extracted from*; becomes a profile + thin BFF.
- **scm** → already a thin consumer of isA_Data; becomes a profile (its data products already live in isA_Data `scm_products.py`).
- **ipd / operation** → already template clones → become pure profiles (manifest + domain PRD).
- **dtc** → a profile on the **bigquery/dbt** substrate adapter; keeps its GCP-native pipeline behind the same framework contracts/serving/dashboard.

### 5. What isA_Data already covers vs the new layer
- **Already in isA_Data (reuse):** adapters, contract schemas + certification/governance/
  lineage/quality/catalog, the product-serving API + per-tower services. ~60–70%.
- **New `isa_data_product` layer adds:** the **profile/manifest abstraction**, the
  **pluggable substrate adapter**, a **scaffolded dashboard SDK** (generalized
  `sn-tower-kit` + BFF route generators bound to product IDs), and the **agentic
  overlay** (MCP/agent BFF/stream) as a standard module.

## Consequences

**Positive**
- N bespoke tower repos → a framework + N small profiles. New domains become config,
  not a repo (ipd/operation already prove this).
- Reuses isA_Data's existing 60–70%; the framework is mostly *extraction*, not greenfield.
- Same fork→profile win at the data layer: customers consume the data-product
  capability via profile instead of forking it (consistent with editions + licensing).
- A data-product capability is also sellable/entitleable via the license
  `entitled_modules` (ADR 0008) — a tower becomes a licensed feature.

**Negative / risks**
- **Extraction effort** from a live `sn_commercial_tower`; must not regress the
  running commercial product.
- **Substrate abstraction risk** — the Dataphin-vs-BigQuery seam is real work; if the
  adapter leaks, the abstraction fails. The existing `mock|sn-data|live` switch
  de-risks this but only for the SN side.
- **Migration** — scm/ipd/operation are easy (already thin/templated); commercial and
  dtc are the heavy lifts.

## Relationship to fork→profile

This is the **same move one layer up**. ADR 0006 made *deployment* a profile (don't
fork the platform images); this makes the *data-product/tower* a profile (don't fork
the spine per domain). It directly reshapes the decommission taxonomy:
- The tower repos move from "bespoke customer-specific repos to maintain" toward
  "domain profiles of an isA capability."
- Separately, the 2026-06-11 archive verification already found `sn_model` and
  `sn_training` carry real SweetNight business logic (not clean mirrors) — those are
  reclassified to customer-specific in `edition-boundary.md`. The data-product work is
  the *constructive* counterpart: give that customer-specific domain logic a platform
  framework to live in rather than a fork.

## Implementation sketch (phased, after sign-off)

1. **Extract** the framework from `sn_commercial_tower/data_platform` + `sn-tower-kit`
   into an `isa_data_product` package on top of isA_Data (don't disturb the live tower).
2. **Define** the profile/manifest schema + the `SubstrateAdapter` interface
   (Dataphin and dbt/BigQuery adapters).
3. **Re-express scm** as a profile (lowest-risk; already a thin consumer) — proof of model.
4. **Generalize** `sn-tower-kit` into the dashboard SDK (BFF route generators + standard pages).
5. **Migrate** commercial → profile; **onboard** ipd/operation as profiles; **fold** dtc
   via the bigquery adapter.
6. Wire the capability into editions/licensing (`entitled_modules`).
