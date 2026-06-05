# isa-dataphin-infra

Umbrella for the dedicated infrastructure Dataphin needs **in addition to**
the `isa-bigdata` backbone. Optional on-prem-full component
(`dataphin.enabled`, default off). Local-deploy runbook:
`deployments/kubernetes/local/scripts/README-phase3.md`.

## Scope

| Subchart | Why it's here |
|---|---|
| `postgres-dataphin` | Dataphin's installer needs a postgres **superuser** to create ~18 datasource DBs/roles — can't share `postgres-bigdata`. |
| `redis` | Dataphin needs a Redis; nothing else in the platform provides one it may use. |

What this umbrella does **not** cover (Dataphin consumes these from
`isa-bigdata`): HMS, Kafka, Apicurio, MinIO lake, StarRocks, Flink, Iceberg.

## Deploy

Into the `dataphin` namespace (separate from `isa-bigdata`):

```bash
helm dependency update deployments/umbrella/isa-dataphin-infra
helm upgrade --install dataphin-infra deployments/umbrella/isa-dataphin-infra \
  -n dataphin --create-namespace \
  -f deployments/values/on-prem-full.yaml
```

Or via an ArgoCD Application
`deployments/argocd/applications/isa-dataphin-infra.yaml`.

This is a **prerequisite** for the Dataphin install itself: provision these
stores first, then point Dataphin's `values.yaml`
`global.postgresql.*` / `global.redis.*` at them.

## Secrets

Production reads Vault-provisioned Secrets (External Secrets), matching the
`postgres-bigdata` pattern:

| Secret | Keys | Used by |
|---|---|---|
| `postgres-dataphin-auth` | `postgres-password`, `password` | postgres-dataphin |
| `redis-dataphin-auth` (or inline) | `redis-password` | redis |
