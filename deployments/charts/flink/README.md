# flink (big-data foundation)

Apache Flink Kubernetes Operator + a long-running session cluster for
the isA platform's big-data foundation. Tracking issue:
[isA_Cloud#248](https://github.com/xenoISA/isA_Cloud/issues/248).

## Three-tier model

```
┌─────────────────────────────────────────────────────┐
│ 1. Operator (upstream chart, cluster-wide)          │
│    Reconciles FlinkDeployment / FlinkSessionJob CRs │
├─────────────────────────────────────────────────────┤
│ 2. Session cluster (THIS chart's CR)                │
│    Long-running JM + TMs that accept jar uploads    │
├─────────────────────────────────────────────────────┤
│ 3. Per-job submissions (flink-cdc-jobs chart, NEXT) │
│    Templated FlinkSessionJob CRs per CDC source     │
└─────────────────────────────────────────────────────┘
```

This chart ships layers 1 and 2. The flink-cdc-jobs chart will ship
layer 3.

## What this chart does

- **Wraps** `flink-operator/flink-kubernetes-operator` v1.10.0 (operator + CRDs)
- **Renders** a `FlinkDeployment` CR for the session cluster, pre-wired for:
  - Paimon-on-MinIO (mounts the `paimon-catalog` ConfigMap from #244 at `/etc/paimon/paimon-catalog.properties`)
  - S3A creds env-injected from `minio-credentials` Secret (#242)
  - State backend: RocksDB with incremental checkpoints to `s3a://flink-checkpoints/`
  - Prometheus metrics on `:9249`
- **Optional** `NetworkPolicy` on JM web UI + RPC + metrics ports (customer-prod only)
- **Optional** `PodDisruptionBudget` for TM (and JM if replicas > 1)

## Profile differential

| | kind-local | dev-shared | customer-prod |
|---|---|---|---|
| JobManager | 1 replica, 2GB | 1 replica, 4GB | 1 replica, 8GB (native HA) |
| TaskManager | 1 replica, 2GB | 1 replica, 4GB | **3 replicas, 16GB** |
| TM slots | 2 | 4 | 4 |
| TM anti-affinity | n/a | n/a | per-host hard rule |
| Native HA | off | off | **on** (Kubernetes leader election; no ZooKeeper) |
| Checkpoints | `s3a://flink-checkpoints/` (ephemeral cluster but state persists in MinIO) | same | same |
| TM PDB | n/a | n/a | minAvailable=2 |
| NetworkPolicy | off | off | on (`isa-bigdata` / `isa-data` / `isa-mcp`) |
| PriorityClass | (none) | (none) | `infra-critical` |

## Mount contract for downstream consumers

Per-job FlinkSessionJob CRs (from `flink-cdc-jobs`) submit jars to the
session cluster's REST API. They don't need extra mounts — the JM + TM
pods already have:

```
/etc/paimon/paimon-catalog.properties   # via ConfigMap mount (this chart)
$AWS_ACCESS_KEY_ID + $AWS_SECRET_ACCESS_KEY   # via Secret env-vars (this chart)
```

Jobs reference the catalog with:

```sql
CREATE CATALOG paimon WITH (
  'type'='paimon',
  -- properties read from /etc/paimon/paimon-catalog.properties
);
```

## helm template caveat — CRDs at apply time

The `FlinkDeployment` CR uses the `flink.apache.org/v1beta1` API which
is installed by the operator subchart. `helm template` renders the CR
without validating against the CRD schema (because `helm template`
doesn't talk to the cluster). `kubectl apply` enforces validation.

That means smoke tests pass on `helm template` even if the operator
isn't running. To catch real schema bugs you must `helm install` or
`kubectl apply --dry-run=server` against a cluster that has the CRDs
loaded.

## Bumping Flink + Operator

The operator chart version dictates the supported Flink version range:

| Operator version | Flink versions |
|---|---|
| 1.10.0 | 1.18 / 1.19 / 1.20 |
| 1.9.0 | 1.16 / 1.17 / 1.18 / 1.19 |

When bumping:

1. Update `Chart.yaml`'s `flink-kubernetes-operator` dependency version.
2. Re-run `helm dependency update` and re-vendor the `.tgz`.
3. Update `Chart.yaml`'s `appVersion` and `values.yaml`'s
   `session.image.tag` to the target Flink version.
4. Verify FlinkDeployment / FlinkSessionJob CR schema didn't break.

## Out-of-cluster JobManager UI access

```bash
kubectl -n isa-bigdata port-forward svc/flink-session-rest 8081:8081
open http://localhost:8081
```

In kind, also accessible via NodePort if `session.service.type` is
overridden in `kind-local.yaml` (default `ClusterIP`).

## Out of scope (follow-ups)

- **`flink-cdc-jobs` chart** — separate story; templates per-CDC-source FlinkSessionJob CRs that submit to this session cluster
- **Per-job FlinkDeployment CRs** — those go in `flink-cdc-jobs` or are operator-driven from outside this chart
- **Reactive scaling / autoscaling** — Flink 1.18+ supports it; opt-in later
- **OIDC SSO for the JobManager UI** — separate auth story
- **Live V-2 / V-3 / V-5 verification on a real kind cluster** — needs `flink-cdc-jobs` first
- **Flink savepoint backup automation** — separate `flink-backup` story

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#235 / #238 / #240 / #242 / #244 / #247 — kafka, postgres, hms, minio, paimon-tools, starrocks (already merged)
- xenoISA/sn-commercial-tower ADR-0002 §2.5 — chart layout
- xenoISA/sn-commercial-tower `docs/design/00-infra-architecture-overview.md` §6.1 (W2 1JM+1TM), §6.2 (W3 1JM+3TM)
