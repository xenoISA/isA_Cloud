# fluss (W12+ shell)

Apache Fluss chart shell — deliberate placeholder for the W12+ Paimon 1.3
upgrade-path decision. Tracking issue:
[isA_Cloud#253](https://github.com/xenoISA/isA_Cloud/issues/253).

## Why this exists today

The big-data foundation in epic #234 ships an 11-chart inventory per
design (xenoISA/sn-commercial-tower ADR-0002 §2.5 + bigdata-architecture.md §4.1).
This is chart 11. Apache Fluss is currently incubating and not yet GA;
the team's W12+ pilot evaluation will decide whether to enable it for
real-time analytics atop the existing Paimon stack.

Filing the chart as a shell now (vs. waiting for W12+) means:

1. **Inventory completeness** — the umbrella's chart-list matches the
   design's 11-chart spec; ops aren't confused by a missing chart.
2. **No-op activation toggle** — when W12 evaluation says "go", flipping
   `fluss.enabled: true` in `customer-prod` values is the only change
   needed to render the *first* placeholder; no scaffold catch-up.
3. **Documented contract** — this README captures activation criteria,
   design decisions outstanding, and what to do *when* Fluss goes GA.

## Current behavior

- **`enabled: false` (default)** — chart renders zero resources. Fluss
  is fully absent from `helm template` output across all 3 profiles.
- **`enabled: true`** — chart renders a single ConfigMap named
  `fluss-shell` with `status: shell-not-implemented`. Ops can grep
  for that string to detect accidental early activation.

## Activation gate (for the W12+ follow-up)

Cannot flip `enabled: true` for production use until **all four** of
these are true:

1. **Apache Fluss is GA.** Track <https://fluss.apache.org/> for the
   release that drops the `incubating` qualifier.
2. **Paimon 1.3 is GA with Fluss interop verified.** The Paimon
   project's release notes need to call out Fluss table support
   explicitly; we don't want to ship a custom integration.
3. **Capacity check** confirms the 3-node KSi5008U cluster (per
   `00-infra-architecture-overview.md` §3.2) has headroom for the
   additional Fluss workload alongside the existing big-data stack.
4. **A follow-up ADR** records the activation decision (mirroring
   ADR-0002 §A2.2 "B: Paimon 单层 + Fluss chart shell 预留" → "A:
   Paimon + Fluss dual-layer activated").

When all four are true:

1. Replace `templates/placeholder.yaml` with real StatefulSet / Service
   / NetworkPolicy / PDB / ServiceMonitor templates.
2. Bump `appVersion` in `Chart.yaml` from `0.0.0-shell` to the target
   Fluss release tag.
3. Fill in the `image.repository`, `replicas`, `storage`,
   `catalog.hiveMetastoreUri`, etc. fields in `values.yaml` (currently
   stubbed with empty strings + TODO comments).
4. Wire the per-profile `customer-prod.yaml` overrides (kind/dev stay
   off; activation is a customer-prod decision).
5. Add a Fluss section to `deployments/scripts/verify/verify-bigdata-charts.sh`
   that asserts the new resources render in `customer-prod`.

## Reserved values structure

The following keys in `values.yaml` exist as **stubs with empty
defaults**. They're listed so the future activation diff is legible —
when someone fills in real values, the structure is already in place
and `helm diff` shows just the value changes:

- `image.{repository,tag,pullPolicy}` — Fluss container image
- `replicas` — broker count (planned 1 for kind, 3 for prod, mirroring kafka)
- `storage.{enabled,size,storageClass}` — persistence
- `catalog.{enabled,hiveMetastoreUri}` — HMS integration so Fluss tables
  register in the same metastore as Paimon (#240)
- `networkPolicy.enabled` / `podDisruptionBudget.enabled` /
  `serviceMonitor.enabled` — observability / safety toggles

## Profile differential

| | kind-local | dev-shared | customer-prod |
|---|---|---|---|
| `fluss.enabled` | **false** (umbrella default) | **false** (umbrella default) | **false** (umbrella default; flip post-W12 ADR) |

All three profiles render zero Fluss resources today. This is the
correct behavior at shell stage.

## Smoke verification

Standalone, with `enabled=true`, exercises the placeholder render path:

```bash
helm template fluss-test deployments/charts/fluss --set enabled=true
# Renders one ConfigMap named fluss-shell with status: shell-not-implemented
```

The umbrella's `verify-bigdata-charts.sh` lints + templates this chart
standalone with `--set enabled=true` to catch regressions in the
helper / labels / placeholder ConfigMap. It does **not** assert any
Fluss resources in umbrella renders, since the umbrella ships
`fluss.enabled: false`.

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#235, #238, #240, #242, #244, #247, #249, #252 — the nine merged big-data charts (#235 covers 2 charts: kafka + apicurio-registry)
- xenoISA/sn-commercial-tower ADR-0002 §A2.2 — "实时热层" decision currently parked at "B: Paimon 单层 + Fluss chart shell 预留"
- xenoISA/sn-commercial-tower `docs/design/00-infra-architecture-overview.md` §6.5 (Phase 3.2 W12-W17 Fluss enablement decision gate)
- xenoISA/sn-commercial-tower `docs/design/bigdata-architecture.md` §4.1 (chart inventory)
