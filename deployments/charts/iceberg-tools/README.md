# iceberg-tools (big-data foundation)

Apache Iceberg catalog config + smoke Job for the isA platform's big-data
foundation. Tracking issue:
[isA_Cloud#260](https://github.com/xenoISA/isA_Cloud/issues/260)
(Paimon → Iceberg migration).

Replaces the earlier `paimon-tools` chart per the v3 architecture
revision in xenoISA/sn-commercial-tower (commit `6c6bb4d`,
`docs/project-plan/appendix-architecture-v3-iceberg.md`, drafted
2026-05-09).

## Why this exists (and why "tools" not a server)

HMS-backed Iceberg topology — **no separate Iceberg REST catalog
server**. Per the v3 plan §四 ("我们用 HMS 路径,Iceberg REST 不必装"):

```
metadata: HMS Postgres (#240)              data: MinIO `lake` bucket (#242)
                  │                                       │
                  └────────── Iceberg table ──────────────┘
                                  │
                  consumed by:
                    Flink + flink-cdc-jobs (write)
                    StarRocks (read + write via external catalog)
                    Dataphin (read + write)
```

This chart's role is to **centralize the catalog properties** so each
consumer mounts the same ConfigMap (`iceberg-catalog`) and points at
the same HMS + MinIO stack. The smoke Job catches mis-wired hosts,
ports, or missing buckets at install time.

## What's in this chart

| Resource | Purpose |
|---|---|
| `ConfigMap/iceberg-catalog` | Catalog properties + `consumer-credentials-secret` discovery hint |
| `Job/iceberg-tools-smoke` | Helm pre-install / pre-upgrade hook; `alpine:3.19` running DNS + nc + curl against HMS + MinIO + the `lake` bucket |

No Deployments. No Services. No PDBs. Iceberg is a library; runtimes consume it.

## Catalog property contract

The ConfigMap renders `iceberg-catalog.properties` with the keys
consumers expect when they call `Catalog.create(properties)` or
`CREATE EXTERNAL CATALOG ... PROPERTIES (...)`:

```properties
type = iceberg
catalog-type = hive
catalog-impl = org.apache.iceberg.hive.HiveCatalog
uri = thrift://hive-metastore.isa-bigdata.svc.cluster.local:9083
warehouse = s3a://lake/warehouse/
default-database = iceberg_default

# S3A (Hadoop-style)
fs.s3a.endpoint = http://minio.isa-bigdata.svc.cluster.local:9000
fs.s3a.path.style.access = true
fs.s3a.connection.ssl.enabled = false
fs.s3a.access.key = ${env:AWS_ACCESS_KEY_ID}
fs.s3a.secret.key = ${env:AWS_SECRET_ACCESS_KEY}
fs.s3a.impl = org.apache.hadoop.fs.s3a.S3AFileSystem

# StarRocks-style aliases (mirror the v3 plan §五 reference DDL)
aws.s3.endpoint = http://minio.isa-bigdata.svc.cluster.local:9000
aws.s3.path_style_access = true
aws.s3.access_key = ${env:AWS_ACCESS_KEY_ID}
aws.s3.secret_key = ${env:AWS_SECRET_ACCESS_KEY}
```

## Migration notes (paimon-tools → iceberg-tools)

| Before | After |
|---|---|
| ConfigMap `paimon-catalog` | `iceberg-catalog` |
| Mount path `/etc/paimon/paimon-catalog.properties` | `/etc/iceberg/iceberg-catalog.properties` |
| Properties: `catalog.type`, `catalog.metastore`, `catalog.uri`, `warehouse` | `type`, `catalog-type`, `catalog-impl`, `uri`, `warehouse` |
| Bucket: `paimon` | `lake` |
| Connector jar: `paimon-flink-1.20-1.0.0.jar` | `iceberg-flink-runtime-1.20-1.6.1.jar` |
| StarRocks DDL: `CREATE EXTERNAL CATALOG paimon_catalog (type=paimon)` | `CREATE EXTERNAL CATALOG iceberg_hms (type=iceberg)` |

## Bumping Iceberg

1. Update `appVersion` in `Chart.yaml` and `icebergVersion` in `values.yaml`.
2. Verify the Flink connector matrix in
   `deployments/runner/flink-sql-runner/jars.txt` — `iceberg-flink-runtime-<flink>-<iceberg>.jar`.
3. Verify StarRocks's Iceberg connector supports the new format-version
   (Iceberg v2 is current default; v3 is on the horizon).

## Out of scope

- **Iceberg REST catalog server** — not deployed (HMS-only path)
- **Iceberg snapshot expiration / compaction Jobs** — separate `iceberg-maint` story
- **Format-version v3 migration** — separate story when GA
- **Live V-2 / V-3 verification** — separate retargeting of #257 against Iceberg

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#260 — Paimon → Iceberg migration epic (this chart's primary issue)
- xenoISA/sn-commercial-tower commit `6c6bb4d` — `docs(project-plan): v3 修订 — 湖仓表格式 Paimon → Iceberg`
- xenoISA/sn-commercial-tower `docs/project-plan/appendix-architecture-v3-iceberg.md`
