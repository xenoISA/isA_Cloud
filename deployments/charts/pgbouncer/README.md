# pgbouncer Helm Chart

Transaction-pooling layer between isA platform services and Postgres.
Tracking issue: [`xenoISA/isA_Cloud#231`](https://github.com/xenoISA/isA_Cloud/issues/231).
Consumer-side cutover: [`xenoISA/isA_user#359`](https://github.com/xenoISA/isA_user/issues/359).

## Why this chart exists

`xenoISA/isA_user` PR #358 introduced replica-aware connection pool sizing.
At HPA-max (10 replicas × 35 services × per-pod pool ≤ 11) the upper-bound
client demand is ~3,850 connections. Production Postgres
`max_connections=500` (`postgresql-ha.yaml:38`). PgBouncer in
`pool_mode = transaction` multiplexes those ~3,850 client connections onto
~100-200 backend connections — comfortably under the 500 ceiling — and
without it Epic #345 cannot ship.

## Capacity budget

| | HPA-min replicas=2 | HPA-max replicas=10 | Postgres ceiling |
|---|---|---|---|
| Per-pod app pool | 5 | 11 | — |
| Total client conns | 350 | 3,850 | — |
| Backend conns through pgbouncer | ~50 | ~150 | 500 |

PgBouncer's own knobs (per replica):

```
max_client_conn      = 5000          # 30% headroom over HPA-max worst case
default_pool_size    = 25            # backend conns per database
reserve_pool_size    = 5             # burst headroom
pool_mode            = transaction
```

3 production replicas × 25 backend conns/db × 1 db = **75 backend conns at
idle**, plus reserve_pool 15 = **~90 peak**. Roughly 18% of the Postgres
500-conn ceiling.

## Chart contents

```
deployments/charts/pgbouncer/
├── Chart.yaml
├── values.yaml
├── README.md
└── templates/
    ├── _helpers.tpl
    ├── configmap.yaml       # pgbouncer.ini
    ├── secret.yaml          # auth (only when auth.create=true; local only)
    ├── deployment.yaml      # pgbouncer + pgbouncer-exporter sidecar
    ├── service.yaml         # ClusterIP on 6432 (+ 9127 metrics)
    ├── pdb.yaml             # PodDisruptionBudget
    ├── networkpolicy.yaml   # optional ingress allowlist
    └── servicemonitor.yaml  # optional prometheus-operator scrape
```

## Per-environment values

| Environment | Values file | Replicas | Auth source |
|---|---|---|---|
| Local kind | `deployments/kubernetes/local/values/pgbouncer.yaml` | 1 | rendered by chart (plaintext) |
| Staging | `deployments/kubernetes/staging/values/pgbouncer.yaml` | 2 | pre-provisioned `pgbouncer-auth` Secret |
| Production | `deployments/kubernetes/production/values/pgbouncer.yaml` | 3 | external-secrets → `pgbouncer-auth` Secret |

## Prerequisites

- A reachable Postgres backend (`postgresql` Service in local/staging,
  `postgresql-ha-pgpool` in production).
- For staging/production: a Kubernetes Secret named `pgbouncer-auth`
  containing the keys below — see *Provisioning credentials*.
- For staging/production with metrics: `prometheus-operator`
  (`kube-prometheus-stack`) with the `release: prometheus` selector.

## Install

### Local (kind)

```bash
helm upgrade --install pgbouncer \
  ~/Documents/Fun/isA/isA_Cloud/deployments/charts/pgbouncer \
  -n isa-cloud-local \
  -f ~/Documents/Fun/isA/isA_Cloud/deployments/kubernetes/local/values/pgbouncer.yaml \
  --set auth.adminPassword=staging_postgres_2024 \
  --set auth.statsPassword=staging_postgres_2024
```

### Staging / Production

```bash
# 1) Provision the auth Secret first (see "Provisioning credentials").
# 2) Install the chart.
helm upgrade --install pgbouncer \
  ~/Documents/Fun/isA/isA_Cloud/deployments/charts/pgbouncer \
  -n isa-cloud-staging \
  -f ~/Documents/Fun/isA/isA_Cloud/deployments/kubernetes/staging/values/pgbouncer.yaml
```

## Provisioning credentials

The auth Secret must contain these keys:

| Key | Purpose |
|---|---|
| `admin-username` | PgBouncer admin role (used by the chart for the `admin_users` directive). |
| `admin-password` | Admin password. |
| `stats-username` | Read-only role used by the prometheus-exporter sidecar (`stats_users`). |
| `stats-password` | Stats password. |
| `userlist.txt` | Full pgbouncer userlist (one `"user" "hash"` row per line). MUST include the application user(s) used by isA_user services. |

### Generating `userlist.txt`

For SCRAM-SHA-256 (Postgres 14+ — the default for the platform), the hash
is the literal contents of `pg_authid.rolpassword` for each role. Pull it
straight out of Postgres:

```bash
PGPASSWORD=$ADMIN_PW psql -h <postgres-host> -U postgres -d postgres -tAc \
  "SELECT format('\"%s\" \"%s\"', rolname, rolpassword)
   FROM pg_authid
   WHERE rolname IN ('isa_admin', 'pgbouncer_stats')" \
  > userlist.txt
```

### Creating the Secret

```bash
kubectl create secret generic pgbouncer-auth \
  -n isa-cloud-staging \
  --from-literal=admin-username=isa_admin \
  --from-literal=admin-password="$ADMIN_PW" \
  --from-literal=stats-username=pgbouncer_stats \
  --from-literal=stats-password="$STATS_PW" \
  --from-file=userlist.txt=./userlist.txt
```

For production, drive this through `ExternalSecret` so credential rotation
flows from the source-of-truth (Vault / AWS SM) without a manual
`kubectl create secret`.

## Operator playbook

### Verifying a fresh install

```bash
# Wait for the deployment to roll.
kubectl rollout status deploy/pgbouncer -n isa-cloud-staging

# Open a port-forward and run a SHOW POOLS / SHOW STATS against pgbouncer.
kubectl port-forward -n isa-cloud-staging svc/pgbouncer 6432:6432 &
PGPASSWORD=$STATS_PW psql -h localhost -p 6432 -U pgbouncer_stats -d pgbouncer \
  -c "SHOW POOLS;" -c "SHOW STATS;"
```

### Tuning `default_pool_size`

`default_pool_size` is the backend-pool ceiling **per database, per
pgbouncer replica**. The whole platform uses a single `isa_platform`
database, so the cluster-wide backend draw is roughly
`replicas × default_pool_size`. Total budget vs. Postgres
`max_connections` is monitored by the `pgbouncer_pools` /
`pgbouncer_stats_*` metrics — pull them up in Grafana before changing
this.

### Debugging "no more connections allowed" errors

This is almost always one of:

1. `max_client_conn` exceeded — bump it in the values file. Each idle
   client connection costs ~2KB on the pgbouncer pod.
2. `default_pool_size` saturated — backends are slow or too few.
   `SHOW POOLS;` shows `cl_waiting > 0` and `sv_active = default_pool_size`.
   Either raise `default_pool_size` or fix the slow backend query.
3. Postgres `max_connections` hit — check
   `kubectl logs deploy/postgresql-ha-postgresql -n isa-cloud-production`
   for `FATAL: sorry, too many clients already`.

## Out of scope for the initial chart PR

- Routing isA_user services through pgbouncer
  (`POSTGRES_HOST`/`POSTGRES_PORT` flip). Tracked separately in
  `xenoISA/isA_user`.
- Tuning the per-service application pool back up to 5/3 once pgbouncer
  is in place. Tracked in the same follow-up.
- Multi-region / geo-replicated pooling.

## Related

- Issue: [`xenoISA/isA_Cloud#231`](https://github.com/xenoISA/isA_Cloud/issues/231)
- Consumer cutover: [`xenoISA/isA_user#359`](https://github.com/xenoISA/isA_user/issues/359)
- Parent epic: [`xenoISA/isA_user#345`](https://github.com/xenoISA/isA_user/issues/345)
- PgBouncer upstream: <https://www.pgbouncer.org/config.html>
- Bitnami pgbouncer image: <https://hub.docker.com/r/bitnami/pgbouncer>
