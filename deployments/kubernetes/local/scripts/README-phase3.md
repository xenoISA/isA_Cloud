# n8n local bring-up runbook

> Brings up a minimal local `isa-cloud-n8n` kind cluster running
> **PostgreSQL + n8n**, plus the optional **Dataphin** infra stack — the scope
> needed to exercise the workflow-automation and data-middle-platform pieces
> locally.

This is a manual, scoped bring-up using only the manifests and values that ship
in this directory tree. It is **coexistence-safe**: the n8n cluster uses a
dedicated kind config (`../kind-config-n8n.yaml`) that maps **no** host ports,
so it runs alongside the full `isa-cloud-local` cluster without port collisions.

## Prerequisites

| Tool      | Install                          |
|-----------|----------------------------------|
| `docker`  | Docker Desktop (must be running) |
| `kind`    | `brew install kind`              |
| `helm`    | `brew install helm`              |
| `kubectl` | `brew install kubectl`           |
| `openssl` | ships with macOS                 |

## 1. Create the cluster + namespace

```bash
kind create cluster --config deployments/kubernetes/local/kind-config-n8n.yaml
kubectl create namespace isa-cloud-local --dry-run=client -o yaml | kubectl apply -f -
```

The kind config names the cluster `isa-cloud-n8n` and maps no host ports, so it
coexists with the existing `isa-cloud-local` cluster; nothing else is touched.

## 2. Create the n8n secrets (only if absent)

```bash
kubectl create secret generic n8n-encryption-key -n isa-cloud-local \
  --from-literal=N8N_ENCRYPTION_KEY="$(openssl rand -hex 24)" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic n8n-db-credentials -n isa-cloud-local \
  --from-literal=postgres-password="$(openssl rand -hex 24)" \
  --dry-run=client -o yaml | kubectl apply -f -

# Real key minted in the n8n UI after deploy (see below) — placeholder for now.
kubectl create secret generic n8n-api-key -n isa-cloud-local \
  --from-literal=api-key='' \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 3. Add Helm repos

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add community-charts https://community-charts.github.io/helm-charts
helm repo update
```

## 4. PostgreSQL + scoped n8n DB role

```bash
helm upgrade --install postgresql bitnami/postgresql -n isa-cloud-local \
  -f deployments/kubernetes/local/values/postgresql.yaml --wait

# Ensure the `n8n` database + scoped `n8n` role exist (idempotent).
kubectl exec -n isa-cloud-local postgresql-0 -c postgresql -- \
  psql -U postgres -c "SELECT 'CREATE DATABASE n8n' WHERE NOT EXISTS \
    (SELECT FROM pg_database WHERE datname='n8n')\gexec"
kubectl cp deployments/kubernetes/local/manifests/n8n-scoped-db-user.sql \
  isa-cloud-local/postgresql-0:/tmp/scoped.sql -c postgresql
kubectl exec -n isa-cloud-local postgresql-0 -c postgresql -- bash -c \
  'PGPASSWORD="$(cat $POSTGRES_PASSWORD_FILE)" psql -U postgres \
    -v pwd="$(openssl rand -hex 24)" -d n8n -f /tmp/scoped.sql'
```

## 5. n8n

```bash
helm upgrade --install n8n community-charts/n8n -n isa-cloud-local \
  -f deployments/kubernetes/local/values/n8n.yaml --wait
```

### Not included in this scoped bring-up

- **APISIX** is not deployed, so `manifests/n8n-apisix-route.yaml` is **not**
  applied.
- `manifests/n8n-network-policies.yaml` is **not** applied. Its allow-list only
  admits ingress from APISIX and `isa_maestro` pods; with APISIX absent it would
  block all ingress to n8n with no benefit. Apply it once APISIX is present.

## Verify

```bash
kubectl get pods -n isa-cloud-local
kubectl logs -n isa-cloud-local deploy/n8n --tail=100
helm list -n isa-cloud-local
```

Expect `postgresql-0` and the `n8n-*` pod both `Running` / `Ready`.

## Reach n8n

The n8n Service is `ClusterIP` (per `values/n8n.yaml`). Port-forward:

```bash
kubectl port-forward -n isa-cloud-local svc/n8n 5678:5678
# open http://localhost:5678
```

## Post-deploy — create the n8n API key (required)

The `n8n-api-key` secret is created with an empty placeholder. The real key can
only be minted in the n8n UI once n8n is up:

1. Open the n8n editor (above) → **Settings → n8n API → Create an API key**.
2. Store it in the secret:

   ```bash
   kubectl create secret generic n8n-api-key -n isa-cloud-local \
     --from-literal=api-key='<PASTE_KEY_HERE>' \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

Consumers (e.g. `isa_maestro`) read the public API key from this secret.

## Optional — Dataphin infra (on-prem-full)

The Dataphin data-middle-platform is an **opt-in** on-prem-full component
(`dataphin.enabled`, default off). Its dedicated stores deploy via the
`isa-dataphin-infra` umbrella into a separate `dataphin` namespace:

```bash
helm dependency update deployments/umbrella/isa-dataphin-infra
helm upgrade --install dataphin-infra deployments/umbrella/isa-dataphin-infra \
  -n dataphin --create-namespace
```

This provisions a dedicated PostgreSQL (`postgres-dataphin`) and a standalone
`redis` for Dataphin. The lakehouse backbone (HMS, Kafka, Apicurio, MinIO lake,
StarRocks, Flink, Iceberg) is consumed from the `isa-bigdata` umbrella, not this
one.

## Tear down

Deletes **only** the `isa-cloud-n8n` cluster — `isa-cloud-local` is untouched:

```bash
kind delete cluster --name isa-cloud-n8n
```
