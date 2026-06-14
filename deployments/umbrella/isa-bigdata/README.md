# isa-bigdata umbrella

Aggregates the big-data foundation Helm charts so a single
`helm template` / `helm install` brings up the runtime that
sn-commercial-tower's `data_platform/` specs target.

## Current scope

- `kafka` (Strimzi-managed, KRaft mode)
- `apicurio-registry` (Apicurio 2.6, PostgreSQL backend)
- `postgres-bigdata` (HMS + Apicurio metadata)
- `hive-metastore`
- `minio` lake storage
- `iceberg-tools`
- `flink` operator + session cluster
- `starrocks` FE/BE
- `flink-cdc-jobs` (disabled until source onboarding)

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

## Production runbook

For on-prem-full deployment order, known failure modes, and Dataphin attachment
prep, see:

```text
docs/runbooks/on-prem-bigdata-backbone-and-dataphin-prep.md
```
