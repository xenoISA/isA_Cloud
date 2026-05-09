# Cluster prerequisites

Cluster-wide K8s objects that the `isa-bigdata` umbrella expects to exist
**before** `helm install`. Each manifest is applied via `kubectl apply -f`
(no Helm), since these are cluster-scoped and shouldn't be coupled to the
release lifecycle of any single chart.

## One-shot path (recommended)

```bash
# Steps 1-2 + 4 below in one command.
deployments/scripts/setup-datalake.sh -p customer-prod
# Or for kind:
deployments/scripts/setup-datalake.sh -p kind-local
# Try --dry-run first:
deployments/scripts/setup-datalake.sh -p customer-prod --dry-run
```

## Manual path (if scripting is unavailable)

```bash
# 1. PriorityClass tiers (system-critical / infra-critical / application)
kubectl apply -f deployments/cluster-prereqs/priorityclasses.yaml

# 2. Strimzi Kafka Operator (cluster-scoped CRDs + operator)
kubectl create namespace strimzi-system
helm install strimzi-operator deployments/charts/strimzi-operator \
  --namespace strimzi-system

# 3. (TBD by separate stories — not yet in this dir)
#    - cert-manager + ClusterIssuer (xenoISA/isA_Cloud#TBD)
#    - prometheus-operator (xenoISA/isA_Cloud#TBD)
#    - vault + external-secrets (customer-prod only)

# 4. Big-data umbrella
helm dependency update deployments/charts/postgres-bigdata
helm dependency update deployments/charts/minio
helm dependency update deployments/charts/starrocks
helm dependency update deployments/charts/flink
helm dependency update deployments/umbrella/isa-bigdata
helm install bigdata deployments/umbrella/isa-bigdata \
  --namespace isa-bigdata --create-namespace \
  --values deployments/values/customer-prod.yaml
```

## Files

| File | What it creates |
|---|---|
| `priorityclasses.yaml` | 3 cluster-scoped `PriorityClass` objects: `system-critical` (1,000,000), `infra-critical` (100,000), `application` (1,000, globalDefault) — referenced by `customer-prod.yaml` profile values across kafka / postgres / hms / minio / starrocks / flink / iceberg-tools |

## Why not in a chart?

Helm 3 supports cluster-scoped resources but ties their lifecycle to the
chart release. PriorityClass should outlive any single chart upgrade —
deleting and re-creating it during a release cycle would temporarily
strip priority from running pods and trigger reschedules. Keeping them
as raw manifests applied once at cluster bring-up sidesteps that.

## Cross-repo context

- `xenoISA/sn-commercial-tower/docs/design/bigdata-architecture.md` §12.4 — the priority-tier policy
- `xenoISA/sn-commercial-tower/docs/design/00-infra-architecture-overview.md` §3 / §6.2 — sizing tables that reference these classes
- `xenoISA/isA_Cloud#234` — parent epic
