# fluss (W12+ shell — DEPRECATED-IN-WAITING)

> **Status (2026-05-09)**: this chart's W12+ activation gate is now
> moot. The big-data foundation pivoted from Paimon to Iceberg per
> v3 plan ([sn-commercial-tower commit `6c6bb4d`](https://github.com/xenoISA/sn-commercial-tower/commit/6c6bb4d), `appendix-architecture-v3-iceberg.md`), and Fluss is a Paimon-derived
> real-time format. Without Paimon, there's no upgrade path to enable.
>
> The chart stays in the umbrella inventory at `enabled: false` until
> ADR-0003 ratifies the Iceberg path on 2026-05-13. After that the
> chart will be **removed in a follow-up PR**. Do not touch it.

Apache Fluss chart shell — placeholder for the (now-cancelled) W12+
Paimon 1.3 upgrade-path decision. Tracking issue:
[isA_Cloud#253](https://github.com/xenoISA/isA_Cloud/issues/253)
(superseded by #260's Iceberg pivot).

## Why it's still here

Removing the chart now would create churn for ops dashboards that
already reference the umbrella's 11-chart inventory. Keeping it as a
zero-resource shell until ADR-0003 lands lets the deprecation happen
in a single coordinated cleanup PR instead of mid-flight.

## Current behavior

- **`enabled: false` (default)** — chart renders zero resources.
- **`enabled: true`** — chart renders a single ConfigMap named
  `fluss-shell` with `status: shell-not-implemented`. Ops can grep for
  that string to detect accidental activation.

**Do not flip `enabled: true`.** With Paimon out of scope, the original
W12+ activation gate (Fluss GA + Paimon 1.3 + capacity + ADR) is
unsatisfiable.

## Removal plan

When ADR-0003 ratifies the Iceberg path (planned 2026-05-13):

1. Open a follow-up PR removing `deployments/charts/fluss/` entirely.
2. Drop the dependency from `deployments/umbrella/isa-bigdata/Chart.yaml`.
3. Drop the passthrough block from `deployments/umbrella/isa-bigdata/values.yaml`.
4. Drop the lint+template lines from `deployments/scripts/verify/verify-bigdata-charts.sh`.
5. Note the removal in ADR-0003 / appendix-architecture-v3-iceberg.md.

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#260 — Paimon → Iceberg migration epic (which moots this chart)
- xenoISA/isA_Cloud#253 — the original story for this shell (now superseded)
- xenoISA/sn-commercial-tower commit `6c6bb4d` + `docs/project-plan/appendix-architecture-v3-iceberg.md`
