# hive-metastore

Apache Hive Metastore (HMS) running standalone — the catalog server for
the isA platform's big-data foundation. Tracking issue:
[isA_Cloud#239](https://github.com/xenoISA/isA_Cloud/issues/239).

## What this chart does

Self-written chart (no upstream Helm chart for HMS standalone). Renders:

- `ConfigMap` — `hive-site.xml` with JDBC, Thrift, warehouse, and S3A blocks
- `Secret`s — DB creds + S3A creds (only when `auth.create=true`; kind only)
- `Service` — Thrift `:9083`
- `StatefulSet` — HMS pods running `hive --service metastore`
- `Job` — `schematool -initSchema -dbType postgres` (Helm pre-install + pre-upgrade hook)
- `NetworkPolicy` — optional ingress allowlist
- `PodDisruptionBudget` — only when `replicas > 1`
- `ServiceMonitor` — stub, off by default until the JMX exporter sidecar lands

## Backing PostgreSQL

This chart points at the `postgres-bigdata` chart's primary by default:

```
db.host: bigdata-postgresql.isa-bigdata.svc.cluster.local
db.port: 5432
db.name: hive_metastore
```

The `hive_metastore` database + `hive_metastore` role are pre-created by
`postgres-bigdata`'s initdb scripts (#237) in kind/dev profiles. In
customer-prod, an external vault job pre-creates them.

## Schema initialization

`schemaInit.enabled` (default `true`) renders a Helm pre-install +
pre-upgrade `Job` that runs `schematool`:

1. **First install**: schema is empty → `schematool -initSchema -dbType postgres`
2. **Upgrade**: schema present → `schematool -upgradeSchema -dbType postgres`
3. **Re-install with same schema**: schematool detects the existing
   `SCHEMA_VERSION` and exits cleanly.

For `customer-prod` the operator pre-runs schemaInit via a vault-driven
Job and disables this hook (`schemaInit.enabled: false`) so a Helm
re-install does not race with the live database.

## Profile differential

| | kind-local | dev-shared | customer-prod |
|---|---|---|---|
| Replicas | 1 | 1 | 2 (active-active) |
| DB auth | plaintext (`auth.create=true`) | `existingSecret: hive-metastore-db` | `existingSecret: hive-metastore-db` (vault-provisioned) |
| S3A auth | plaintext kind creds | `existingSecret: minio-credentials` | `existingSecret: minio-credentials` |
| schemaInit | runs | runs | DISABLED (vault-provisioned) |
| Anti-affinity | n/a | n/a | per-host hard rule |
| PDB | n/a (1 pod) | n/a (1 pod) | minAvailable=1 |
| NetworkPolicy | off | off | on (`isa-bigdata` / `isa-data` / `isa-mcp`) |
| PriorityClass | (none) | (none) | `infra-critical` |

## Warehouse path (Iceberg-on-MinIO)

`warehouse.dir` defaults to `s3a://lake/warehouse/`. HMS doesn't write
there — it returns this path to clients (Flink CDC, Dataphin, StarRocks)
when they create unqualified tables. The S3A endpoint defaults to
`http://minio.isa-bigdata.svc.cluster.local:9000`; override per profile
once the minio chart lands.

## Bumping Hive

1. Update `image.tag` and `appVersion` in `Chart.yaml`.
2. Re-render → the `pre-upgrade` hook runs `schematool -upgradeSchema`.
3. Verify schema migration completes:
   ```
   kubectl -n isa-bigdata logs job/hive-metastore-init-schema
   ```

## Out of scope (follow-ups)

- **Kerberos auth** — HMS supports it but adds significant config; opt-in later
- **JMX-Prometheus sidecar** — needed for real metrics; ServiceMonitor stub is in place
- **Live V-2 / V-3 verification** — separate story, depends on minio + flink + iceberg-tools

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#235 (kafka + apicurio), #238 (postgres-bigdata) — already merged
- xenoISA/sn-commercial-tower ADR-0002 §2.5 — chart layout
- xenoISA/sn-commercial-tower `docs/design/bigdata-architecture.md` §4.1 + §12.2
