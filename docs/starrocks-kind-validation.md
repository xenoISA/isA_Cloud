# StarRocks on kind — W2.2 Validation Report

> Acceptance gate for [xenoISA/isA_Cloud#272](https://github.com/xenoISA/isA_Cloud/issues/272)
> (W2.2 — StarRocks bringup on kind). Profile: `kind-local`. Cluster:
> `kind-isa-cloud-local` (1 control-plane + 2 workers, kindest/node:v1.34.0).

## Goal

Prove the `deployments/charts/starrocks` chart wraps the upstream
`starrocks-community/kube-starrocks` operator + cluster CR cleanly enough
that a kind cluster can:

1. Boot a single-replica FE + single-replica BE.
2. Accept mysql-protocol connections on port 9030 from outside the cluster
   (via `kubectl port-forward`).
3. Answer `SHOW DATABASES` with the default `_statistics_` + `information_schema`
   set, proving the FE has finished metadata initialization.
4. Accept the post-install `starrocks-catalog-init` Helm hook Job which
   registers the `iceberg_hms` external catalog wired to HMS Thrift.

The full V-4 catalog query (SHOW CATALOGS / SELECT through Iceberg) lives
in the V-1..V-9 verification gates documented in
[xenoISA/isA_Cloud#275](https://github.com/xenoISA/isA_Cloud/issues/275)
and exercised by `deployments/scripts/verify/verify-bigdata-kind.sh`.

## Bringup procedure (reproducible)

```bash
# Prerequisites — already running on the operator's machine
kind get clusters | grep isa-cloud-local
helm version --short
kubectl get nodes

# 1. Cluster prereqs — PriorityClass tiers (idempotent)
kubectl apply -f deployments/cluster-prereqs/priorityclasses.yaml

# 2. cert-manager — Strimzi-adjacent prereq because flink-operator
#    bundles Certificate / Issuer CRs in its sub-chart
helm dependency update deployments/charts/cert-manager
helm upgrade --install cert-manager deployments/charts/cert-manager \
  --namespace cert-manager --create-namespace --wait --timeout 5m

# 3. Pre-create the watched namespace (Strimzi projects RoleBindings
#    into it at install time; chicken-and-egg if it doesn't exist)
kubectl create namespace isa-bigdata

# 4. Full umbrella bringup (Strimzi + 10-chart umbrella)
make setup-datalake-kind
# equivalent to:
#   bash deployments/scripts/setup-datalake.sh -p kind-local

# 5. Wait for FE + BE to roll out
kubectl -n isa-bigdata rollout status statefulset/bigdata-starrocks-fe --timeout=15m
kubectl -n isa-bigdata rollout status statefulset/bigdata-starrocks-be --timeout=15m
```

## Probe — mysql-protocol connectivity

```bash
# Open a port-forward to the FE Service in another terminal:
kubectl -n isa-bigdata port-forward svc/bigdata-starrocks-fe-service 9030:9030 &

# Connect with the default root credential (kind-local profile)
mysql -h 127.0.0.1 -P 9030 -u root --password=starrocks-kind -e "SHOW DATABASES;"
```

**Expected output:**

```
+--------------------+
| Database           |
+--------------------+
| _statistics_       |
| information_schema |
+--------------------+
```

If the query returns those two databases, the FE is healthy. The
absence of `_statistics_` indicates the FE init Job hasn't completed
yet — re-run after another minute.

## Probe — Iceberg catalog registration

The `starrocks-catalog-init` Helm hook Job runs once on first install
and executes:

```sql
CREATE EXTERNAL CATALOG iceberg_hms
PROPERTIES (
  "type" = "iceberg",
  "iceberg.catalog.type" = "hive",
  "hive.metastore.uris" = "thrift://hive-metastore.isa-bigdata.svc.cluster.local:9083"
);
```

Verify:

```bash
kubectl -n isa-bigdata get job starrocks-catalog-init \
  -o jsonpath='{.status.succeeded}'
# Expected: 1

# And from the mysql client:
mysql -h 127.0.0.1 -P 9030 -u root --password=starrocks-kind -e "SHOW CATALOGS;"
# Expected to include `iceberg_hms` alongside the default catalog.
```

## Sizing on kind

The kind-local profile pins minimal-but-functional sizing:

| Component | Replicas | CPU req / lim | Mem req / lim | Storage |
|---|---|---|---|---|
| Operator | 1 | 50m / 250m | 128Mi / 256Mi | — |
| FE | 1 | 250m / 1 | 1Gi / 2Gi | 5Gi local-path |
| BE | 1 | 500m / 2 | 1Gi / 4Gi | 20Gi local-path |

Total: ~2 CPU req, ~5 Gi Mem req, 25 Gi disk. Comfortably fits on a
single Docker Desktop node with 8 CPU / 12 Gi RAM allocated.

## What this validates vs. what stays for W3

**Validated on kind:**

- Operator chart renders cleanly with kind-local values.
- FE / BE StatefulSets reach Ready within 5 minutes on a warm node.
- mysql-protocol port reachable through `kubectl port-forward`.
- Default credentials work (root + chart-managed `rootPassword` Secret).
- `starrocks-catalog-init` Job succeeds — Iceberg external catalog
  registers without HMS being fully populated yet.
- Pod resource requests fit kind defaults (no scheduling failures).

**Deferred to W3 hardware bringup:**

- Multi-FE quorum (3 FE replicas, leader election under partition).
- BE storage sizing on real NVMe (kind uses `local-path` over the
  control-plane node's disk; not representative of real I/O).
- StarRocks ↔ HMS over TLS (HMS Thrift TLS is W3 opt-in).
- Backup/restore via `BACKUP` / `RESTORE` SQL into MinIO (kind MinIO
  is single-replica; no representative HA path).
- PriorityClass eviction behavior under cluster pressure.
- Admin UI (`http://<FE>:8030/`) accessibility through APISIX Ingress.

## Known kind-only deviations from customer-prod

| Knob | kind-local | customer-prod |
|---|---|---|
| FE replicas | 1 | 3 |
| BE replicas | 1 | 3+ |
| `priorityClassName` | (none) | `infra-critical` |
| Storage class | `local-path` | customer's CSI (TopoLVM / Rook / etc.) |
| `existingSecret` for root password | chart-rendered | ESO from Vault |
| ServiceMonitor | off | on (prometheus-operator scrape) |
| NetworkPolicy | off | on |
| externalService | ClusterIP | NodePort/LoadBalancer/Ingress |

Switching profile is `setup-datalake.sh -p customer-prod`; the chart
templates handle the difference declaratively.

## Failure modes seen during W2 bringup

1. **`PriorityClass "system-critical" is invalid: ... 'system-' prefix
   is reserved`** — fixed in this branch by renaming the highest tier
   to `platform-critical`. See commit `fix(infra): rename PriorityClass
   system-critical → platform-critical`.

2. **`namespaces "isa-bigdata" not found`** during Strimzi install —
   the Strimzi chart projects RoleBindings into watched namespaces at
   install time. Fixed in setup-datalake.sh by pre-creating both
   namespaces before the strimzi-operator helm install.

3. **`no matches for kind "Certificate" in version "cert-manager.io/v1"`** —
   the bundled `flink-kubernetes-operator` sub-chart issues
   `Certificate` + `Issuer` CRs for its admission webhook. cert-manager
   must be installed before the umbrella. The setup-datalake.sh script
   does not yet hard-fail on missing cert-manager; this is captured as
   a follow-up so future operators get a clean error instead of an
   opaque CRD-mapping failure. **W3 deploy.sh `infrastructure` subcommand
   installs cert-manager first**, so the customer-prod path is unaffected.

## References

- Chart: `deployments/charts/starrocks/`
- Profile values: `deployments/values/kind-local.yaml` (`starrocks:` block)
- Catalog init Job: `deployments/charts/starrocks/templates/catalog-init-job.yaml`
- V-4 verification: `deployments/scripts/verify/verify-bigdata-kind.sh`
- pytest equivalent: `tests/bigdata_kind/test_v4_starrocks_iceberg_catalog.py`
- Architecture: `docs/design/00-infra-architecture-overview.md` §6.1
- W2.2 issue: <https://github.com/xenoISA/isA_Cloud/issues/272>
