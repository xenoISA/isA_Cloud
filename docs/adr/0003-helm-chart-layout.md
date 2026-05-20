# ADR-0003: Helm chart layout — `deployments/` over `helm/`

* **Status**: Accepted
* **Date**: 2026-05-20
* **Closes**: [#236](https://github.com/xenoISA/isA_Cloud/issues/236)
* **Supersedes** (partially): xenoISA/sn-commercial-tower ADR-0002 §2.5 (path layout)

## Context

xenoISA/sn-commercial-tower's [ADR-0002 §2.5](https://github.com/xenoISA/sn-commercial-tower/blob/main/docs/adr/0002-bigdata-platform-architecture.md) and `docs/design/bigdata-architecture.md` §4.1 specified the big-data foundation charts layout as:

```
isA_Cloud/helm/
├── charts/
├── umbrella/
├── values/
└── docs/
```

But the actual repo layout — established by earlier `isa-service` and `pgbouncer` charts, and continued in the recent big-data delivery (#235 — kafka, apicurio-registry, etc.) — uses:

```
isA_Cloud/deployments/
├── charts/
│   ├── kafka/
│   ├── apicurio-registry/
│   ├── flink/
│   ├── flink-cdc-jobs/
│   ├── fluss/
│   ├── hive-metastore/
│   ├── iceberg-tools/
│   ├── isa-service/
│   ├── pgbouncer/
│   ├── ...
├── umbrella/
├── values/
└── kubernetes/
```

Every chart shipped to date lives under `deployments/`. ArgoCD applications, `deploy.sh`, the CI `validate-manifests` matrix, and per-component README all reference `deployments/`.

## Decision

**Charts canonically live under `deployments/` in isA_Cloud.** The design docs in xenoISA/sn-commercial-tower are out of date and will be patched to match (a separate PR in that repo).

`deployments/charts/`, `deployments/umbrella/`, `deployments/values/` are the canonical paths. Future charts (#234 follow-ups: starrocks, paimon-tools, pg-bigdata, etc.) MUST land here.

## Alternatives considered

| Option | Pro | Con |
|---|---|---|
| **A. Migrate `deployments/` → `helm/`** (match the original design) | Closer to original design intent | Touches ArgoCD applications + `deploy.sh` + CI matrix + every per-chart README; high-blast-radius rename for no functional gain |
| **B. Update design to match repo (this ADR)** ✓ | Cheap, zero rename churn, zero risk to ArgoCD/deploy.sh | One-time doc-sync PR in sn-commercial-tower |

Option B chosen — Option A's cost is real (ArgoCD applications would all need to re-bind) while the benefit (cosmetic doc alignment) can be captured for free by patching the design docs instead.

## Consequences

* `deployments/` becomes the canonical home for all Helm charts in this repo.
* xenoISA/sn-commercial-tower ADR-0002 §2.5 and `docs/design/bigdata-architecture.md` §4.1 are out of date — to be patched in a separate PR there.
* No code/config rename in isA_Cloud. ArgoCD applications, deploy.sh, CI all remain pointing at `deployments/` as today.
* New chart authors should NOT create `helm/` paths — use `deployments/charts/<name>/`.

## Follow-up (cross-repo)

* xenoISA/sn-commercial-tower: patch ADR-0002 §2.5 + `docs/design/bigdata-architecture.md` §4.1 + `docs/design/00-infra-architecture-overview.md` §4.3 to reference `deployments/` instead of `helm/`. Tracked by the merge of this ADR.
