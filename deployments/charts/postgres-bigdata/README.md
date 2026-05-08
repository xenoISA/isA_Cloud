# postgres-bigdata

Shared PostgreSQL instance backing the big-data foundation's metadata
stores. Tracking issue: [isA_Cloud#237](https://github.com/xenoISA/isA_Cloud/issues/237).

## What this chart does

Wraps the upstream `bitnami/postgresql` chart with profile-aware defaults.
The bitnami subchart owns the actual `StatefulSet`, `Service`, `Secret`,
`NetworkPolicy`, and `ServiceMonitor`. This chart only:

- Pins the bitnami chart version
- Sets defaults that match the kafka + apicurio-registry charts in this repo
- Documents the per-consumer database contract (apicurio / hive_metastore / dataphin)

## Consumer database contract

Each downstream chart connects to **one named database** with **one named
role**, both pre-created at first startup by the initdb scripts in the
per-profile values file:

| Consumer chart | Database | Role | Secret it reads |
|---|---|---|---|
| `apicurio-registry` | `apicurio` | `apicurio` | `apicurio-registry-db` (keys: `username`, `password`) |
| `hive-metastore` (future) | `hive_metastore` | `hive_metastore` | `hive-metastore-db` |
| `dataphin` (future) | `dataphin` | `dataphin` | `dataphin-db` |

The `bigdata` role from `auth.username` is the chart's own primary user —
it owns the `bigdata` database that bitnami creates by default. It is
**not** consumed by any downstream chart; it exists because the bitnami
chart requires a primary user.

### Adding a new consumer

1. Add a `CREATE USER ... CREATE DATABASE ... GRANT` block to the
   `postgres-bigdata.postgresql.primary.initdb.scripts` map in each of
   `kind-local.yaml` / `dev-shared.yaml` / `customer-prod.yaml`.
2. Render or pre-provision a `Secret` named `<consumer>-db` with keys
   `username` and `password` matching the SQL above.
3. Update this README's table.

## Profile differential

| | kind-local | dev-shared | customer-prod |
|---|---|---|---|
| Architecture | standalone | standalone | replication (1 primary + 2 read replicas) |
| Storage | local-path 4Gi | default-class 50Gi | infortrend-iscsi 500Gi |
| Auth | plaintext | `existingSecret` | `existingSecret` (provisioned by external-secrets) |
| initdb runs | yes (creates apicurio user) | yes (creates apicurio user) | no (pre-provisioned) |
| NetworkPolicy | off | off | on (allow `isa-bigdata` / `isa-data` / `isa-mcp`) |
| Anti-affinity | n/a (1 pod) | n/a (1 pod) | per-host hard rule |
| PriorityClass | (none) | (none) | `infra-critical` |
| ServiceMonitor | off | on | on |

## Verification

`bash deployments/scripts/verify/verify-bigdata-charts.sh`

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic (kafka + apicurio + 9 more charts)
- xenoISA/isA_Cloud#235 — kafka + apicurio-registry (merged); apicurio's
  `customer-prod.yaml` references `postgresql-bigdata.isa-bigdata.svc.cluster.local`
  with `existingSecret: apicurio-registry-db`
- xenoISA/sn-commercial-tower ADR-0002 §2.5 / `docs/design/bigdata-architecture.md` §4.1
