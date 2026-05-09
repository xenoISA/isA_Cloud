# isa-bigdata umbrella

Aggregates the big-data foundation Helm charts so a single
`helm template` / `helm install` brings up the runtime that
sn-commercial-tower's `data_platform/` specs target.

## Current scope

- `kafka` (Strimzi-managed, KRaft mode)
- `apicurio-registry` (Apicurio 2.6, PostgreSQL backend)

## Planned dependencies (not yet wired)

Per `docs/design/bigdata-architecture.md` §4.1 in xenoISA/sn-commercial-tower:

- `postgres-bigdata` — Postgres for HMS + Apicurio metadata
- `hive-metastore`
- `flink-operator`, `flink-jobmanager`, `flink-taskmanager`
- `flink-cdc-jobs`
- `iceberg-tools`
- `starrocks-fe`, `starrocks-be`

## Usage

```bash
# Pull subchart deps (no remote repos — file:// only).
helm dependency update deployments/umbrella/isa-bigdata

# Render kind-local profile.
helm template isa-bigdata deployments/umbrella/isa-bigdata \
  --values deployments/values/kind-local.yaml

# Render customer-prod profile.
helm template isa-bigdata deployments/umbrella/isa-bigdata \
  --values deployments/values/customer-prod.yaml
```

## Verification

`deployments/scripts/verify/verify-bigdata-charts.sh` runs `helm lint` +
`helm template` + manifest-parse smoke checks across both profiles.
Wire it into CI alongside the existing chart smoke jobs.
