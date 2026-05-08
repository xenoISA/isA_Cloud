# minio (big-data foundation)

MinIO object storage for the isA platform's big-data foundation —
Paimon warehouse, Flink checkpoints, Dataphin export staging.
Tracking issue: [isA_Cloud#241](https://github.com/xenoISA/isA_Cloud/issues/241).

## What this chart does

Wraps the upstream `minio/minio` chart (v5.4.0, MinIO release `2024-12-18`)
with profile-aware defaults. The upstream subchart owns the actual
Deployment/StatefulSet, Services, NetworkPolicy, PDB, ServiceMonitor, and
bucket-creation Job. This chart only:

- Pins the upstream chart version + vendors the `.tgz` for air-gap
- Renders an optional `Secret` (`minio-credentials`) when `auth.create=true`
  with keys (`access-key`, `secret-key`) matching what `hive-metastore`'s
  S3A client reads, plus (`rootUser`, `rootPassword`) for the upstream chart
- Pre-creates `paimon`, `flink-checkpoints`, `dataphin-export` buckets

## Why a separate chart from the existing isA platform MinIO

This deploy is **share-nothing** with the pre-existing
`deployments/kubernetes/<env>/values/minio*.yaml` files (see #241 discover).
Different namespace (`isa-bigdata`), different bucket layout, different
auth Secret. Customer-prod runs two MinIO clusters; revisit if storage
cost becomes a concern.

A future refactor (similar to #236's path-drift conversation) can
consolidate the legacy values files into a chart wrapper. Out of scope
for this PR.

## Profile differential

| | kind-local | dev-shared | customer-prod |
|---|---|---|---|
| Mode | standalone | standalone | distributed |
| Replicas | 1 | 1 | 4 (EC:2, 4+2) |
| Storage | local-path 20Gi | default-class 50Gi | infortrend-iscsi 200Gi × 4 |
| Auth | plaintext (`auth.create=true`) | `existingSecret: minio-credentials` | `existingSecret: minio-credentials` (vault-provisioned) |
| Anti-affinity | n/a | n/a | per-host hard rule |
| PDB | n/a (1 pod) | n/a (1 pod) | minAvailable=3 |
| NetworkPolicy | off | off | on |
| ServiceMonitor | off | on | on |
| PriorityClass | (none) | (none) | `infra-critical` |
| Console exposure | NodePort | ClusterIP | ClusterIP |

## Bucket layout

| Bucket | Consumer | Notes |
|---|---|---|
| `paimon` | hive-metastore warehouse path; flink-cdc-jobs writes here; starrocks reads here | Primary big-data bucket |
| `flink-checkpoints` | flink-jobmanager / flink-cdc-jobs (future) | Reserved; off-peak retention recommended |
| `dataphin-export` | dataphin (future) | Reserved for vendor export drops |

## Secret contract

When `auth.create=true` (kind only) this chart renders:

```yaml
kind: Secret
metadata:
  name: minio-credentials
type: Opaque
stringData:
  access-key: <auth.rootUser>          # consumed by hive-metastore S3A
  secret-key: <auth.rootPassword>      # consumed by hive-metastore S3A
  rootUser: <auth.rootUser>            # consumed by upstream minio/minio chart
  rootPassword: <auth.rootPassword>    # consumed by upstream minio/minio chart
```

Production must pre-provision the same Secret externally with all four
keys. The upstream chart's `existingSecret` reads `rootUser`/`rootPassword`;
the hive-metastore chart reads `access-key`/`secret-key`.

## S3 endpoint

The MinIO ClusterIP Service is reachable in-cluster as:

```
minio.isa-bigdata.svc.cluster.local:9000
```

This matches the `s3a.endpoint` already wired into `hive-metastore`'s
profile values.

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#235 / #238 / #240 — kafka, postgres-bigdata, hive-metastore (already merged)
- xenoISA/sn-commercial-tower ADR-0002 §2.5 — chart layout
- xenoISA/sn-commercial-tower `docs/design/00-infra-architecture-overview.md` §6.1 (W2 kind), §6.2 (W3 prod 4副本 EC 4+2), §1.4 risk #1 (V-3 = highest-risk gate)
