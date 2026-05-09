# starrocks (big-data foundation)

StarRocks OLAP query layer for the isA platform's big-data foundation.
Tracking issue: [isA_Cloud#245](https://github.com/xenoISA/isA_Cloud/issues/245).

## What this chart does

Wraps the upstream `starrocks/kube-starrocks` chart (v1.11.4 / StarRocks
3.5) which itself bundles two subcharts:

- `operator` — the StarRocks Kubernetes Operator
- `starrocks` — the `StarRocksCluster` CR + FE/BE component specs

On top of that this chart adds:

- **Optional `starrocks-root-credentials` Secret** — rendered when
  `rootPassword.create=true` (kind only; production pre-provisions externally)
- **`Job` `starrocks-catalog-init`** (gated by `catalogInit.enabled`) —
  Helm `post-install`/`post-upgrade` hook that polls FE on `:9030` until
  reachable, then issues `CREATE EXTERNAL CATALOG IF NOT EXISTS paimon_catalog`
  with the same wiring as `paimon-tools`' `paimon-catalog` ConfigMap

The Job is idempotent (`IF NOT EXISTS`) so re-installs and chart upgrades
re-run safely.

## Triple-nesting heads-up

The upstream chart structure forces a verbose value path from profile files:

```
starrocks.kube-starrocks.starrocks.starrocksFESpec.replicas: 3
│         │              │         └── inner subchart's spec key
│         │              └── inner subchart name (kube-starrocks's child)
│         └── upstream parent chart name
└── this chart's name in the umbrella
```

This is unavoidable without forking the upstream. Profile values files
follow the same pattern.

## Profile differential

| | kind-local | dev-shared | customer-prod |
|---|---|---|---|
| FE replicas | 1 | 1 | 3 |
| BE replicas | 1 | 1 | 3 |
| FE storage | local-path 5Gi | default-class 10Gi | infortrend-iscsi 50Gi |
| BE storage | local-path 20Gi | default-class 50Gi | infortrend-iscsi 200Gi |
| Root password | rendered (`rootPassword.create=true`) | `existingSecret: starrocks-root-credentials` | `existingSecret` (vault-provisioned) |
| Catalog init Job | runs (registers `paimon_catalog`) | runs | **disabled** (operator runs combined V-2/V-3/V-4 smoke) |
| FE/BE anti-affinity | n/a (1 of each) | n/a | per-host hard rule (FE + BE separately) |
| PDB | n/a | n/a | minAvailable=2 each |
| NetworkPolicy | off | off | on |
| ServiceMonitor | off | on | on |
| PriorityClass | (none) | (none) | `infra-critical` |

## paimon_catalog DDL contract

The init Job runs the equivalent of:

```sql
CREATE EXTERNAL CATALOG IF NOT EXISTS paimon_catalog
PROPERTIES (
  "type" = "paimon",
  "paimon.catalog.type" = "hive",
  "hive.metastore.uris" = "thrift://hive-metastore.isa-bigdata.svc.cluster.local:9083",
  "aws.s3.endpoint" = "http://minio.isa-bigdata.svc.cluster.local:9000",
  "aws.s3.access_key" = "${env:AWS_ACCESS_KEY_ID}",
  "aws.s3.secret_key" = "${env:AWS_SECRET_ACCESS_KEY}",
  "aws.s3.enable_path_style_access" = "true",
  "aws.s3.enable_ssl" = "false"
);
```

Once the catalog is registered, query Paimon tables via
`SELECT * FROM paimon_catalog.<db>.<table>` from any StarRocks client.
Until `flink-cdc-jobs` lands and writes to Paimon, the catalog will
list zero tables — but registration succeeds and the connection test
proves V-4 plumbing.

## Connection target

In-cluster FE Service (default release name `bigdata`):

```
bigdata-starrocks-fe-service.isa-bigdata.svc.cluster.local:9030  # MySQL query
bigdata-starrocks-fe-service.isa-bigdata.svc.cluster.local:8030  # HTTP/web UI
```

For ad-hoc kind access:

```bash
kubectl -n isa-bigdata port-forward svc/bigdata-starrocks-fe-service 9030:9030
mysql -h 127.0.0.1 -P 9030 -u root --password="<from secret>"
```

## Bumping StarRocks

1. Pick a new `kube-starrocks` chart version from
   <https://starrocks.github.io/starrocks-kubernetes-operator>.
2. Update the version pin in `Chart.yaml` and re-run
   `helm dependency update`.
3. Re-vendor the `.tgz` for air-gap.
4. Confirm FE/BE image tags via `helm show values starrocks/kube-starrocks --version <new>` —
   StarRocks supports rolling FE/BE upgrades but breaking changes
   between majors require operator coordination.

## Out of scope (follow-ups)

- **CN (Compute Node) separation-of-storage** — current chart uses BE; CN-mode is a future optimization
- **Iceberg / Hudi / Hive-only external catalogs** — only `paimon` for V-4
- **OIDC SSO + RBAC role wiring** — separate auth story
- **StarRocks Manager UI / dashboard** — out of scope
- **Live V-4 verification on a real kind cluster** — needs flink-cdc-jobs first to populate Paimon tables; separate story
- **Routine query / bulk load benchmarks** — separate perf story

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#235 / #238 / #240 / #242 / #244 — kafka, postgres-bigdata, hive-metastore, minio, paimon-tools (already merged)
- xenoISA/sn-commercial-tower ADR-0002 §2.5 — chart layout
- xenoISA/sn-commercial-tower `docs/design/00-infra-architecture-overview.md` §6.1 (W2 kind 1+1) and §6.2 (W3 prod 3+3)
