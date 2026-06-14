# Edition Helm profiles

> xenoISA/isA_Cloud #316 — part of follow-up epic #328.

**One platform, three editions.** The same `xenoISA/isA_*` code ships as the
managed SaaS, a full on-prem install, and a lite on-prem install. An edition is
just a set of Helm values overlays that (a) set the runtime edition env and
(b) toggle the optional big-data umbrella.

These values overlay the base service chart at
[`../charts/isa-service`](../charts/isa-service). The chart renders
`.Values.env` verbatim onto every service container, so the env keys below are
read at runtime by `isa_common.edition` (#317) and `isa_common.brand`.

## Edition matrix

| Edition | `ISA_EDITION` | big-data umbrella | multi-tenant | charging | metering | brand |
|---|---|:---:|:---:|:---:|:---:|---|
| **SaaS** (isA-hosted) | `saas` | ❌ off | ✅ on | ✅ on | ✅ on | isA |
| **On-Prem · Full** | `on-prem-full` | ✅ on | ❌ off | ❌ off | ✅ on | white-label |
| **On-Prem · Lite** | `on-prem-lite` | ❌ off | ❌ off | ❌ off | ✅ on | white-label |

Two orthogonal module switches (per `docs/saas-deployment/README.md`):

1. **Big-data** (`isa-bigdata` umbrella: Kafka/Flink/StarRocks/Iceberg/Dataphin)
   — on-prem installs choose; **SaaS never installs it**.
2. **Multi-tenant + charging** (registration / API key / metering / billing)
   — **SaaS only**; on-prem single-tenant does not need it and it must **not**
   sync into the white-label `sn_*` fork.

## Files

| File | Purpose |
|---|---|
| `values-base.yaml` | Common to all editions: core services + lightweight stores, metering on, isA brand defaults (documented overlay point). |
| `values-saas.yaml` | `ISA_EDITION=saas`; bigdata off; multi-tenant + charging on; brand = isA. |
| `values-on-prem-full.yaml` | `ISA_EDITION=on-prem-full`; bigdata **on**; multi-tenant/charging off; white-labelable. |
| `values-on-prem-lite.yaml` | `ISA_EDITION=on-prem-lite`; bigdata off; multi-tenant/charging off. |
| `values-brand-sn.example.yaml` | Example brand overlay (`BRAND_*` for SN) applied on top of an on-prem edition. |

## Deploy

Apply `values-base.yaml` first, then the edition file, then (optionally) a brand
overlay last so its env wins:

```bash
# SaaS (isA brand, no big-data, multi-tenant + charging)
helm install isa-saas ./deployments/charts/isa-service \
  -f deployments/editions/values-base.yaml \
  -f deployments/editions/values-saas.yaml

# On-prem full, white-labelled to SN (installs the platform)
helm install isa-on-prem ./deployments/charts/isa-service \
  -f deployments/editions/values-base.yaml \
  -f deployments/editions/values-on-prem-full.yaml \
  -f deployments/editions/values-brand-sn.example.yaml

# On-prem lite (no big-data)
helm install isa-on-prem-lite ./deployments/charts/isa-service \
  -f deployments/editions/values-base.yaml \
  -f deployments/editions/values-on-prem-lite.yaml \
  -f deployments/editions/values-brand-sn.example.yaml
```

### Big-data umbrella (full edition only)

`values-on-prem-full.yaml` sets `bigdata.enabled: true`. Because the big-data
stack is a **separate Helm release** (it has its own chart, not a subchart of
`isa-service`), enabling the full edition means ALSO installing the umbrella:

```bash
helm dependency update deployments/umbrella/isa-bigdata
helm install isa-bigdata ./deployments/umbrella/isa-bigdata \
  -f deployments/values/customer-prod.yaml
```

The umbrella's own subchart `enabled` flags
(`deployments/umbrella/isa-bigdata/values.yaml`) gate the individual components
(Kafka, Flink, StarRocks, …). The `bigdata.enabled` flag in the edition values
is the single switch the deploy tooling / ArgoCD application reads to decide
whether that umbrella release is installed at all; `ISA_BIGDATA_ENABLED` in the
env block is its runtime mirror for `isa_common.edition`.

## Brand overlay

Brand is white-labelled by overlaying a `values-brand-<customer>.yaml` that
restates the `BRAND_*` / `AUTH_COOKIE_DOMAIN` env keys (Helm replaces list
values, so restate the edition's `ISA_*` keys too). See
`values-brand-sn.example.yaml`. The isA→SN sanitizer also rewrites `ISA_*→SN_*`
and brand strings mechanically on sync; the overlay is for the
customer-specific values (domains, support email) the sanitizer can't infer.

## References

- `docs/saas-deployment/README.md` — edition matrix + module boundary.
- `docs/saas-deployment/saas-production-architecture-design.md` — SaaS architecture.
- `docs/saas-deployment/brand-surface-audit.md` — full `BRAND_*` surface list.
- `docs/saas-deployment/edition-boundary.md` — repo taxonomy + white-label boundary.
- `docs/adr/0006-plugin-extension-sdk.md` — edition/plugin ADR.
- `isa_common.edition` (#317) / `isa_common.brand` — runtime readers of this env.
