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

# 3. Prometheus Operator stack (CRDs for ServiceMonitor /
#    PodMonitor / Prometheus / AlertManager / etc.)
#    REQUIRED when customer-prod profile (or any profile with
#    `serviceMonitor.enabled: true`) is in use; otherwise
#    ServiceMonitor CRs from the umbrella fail with "no matches for
#    kind ServiceMonitor in version monitoring.coreos.com/v1".
kubectl create namespace monitoring
helm dependency update deployments/charts/prometheus-operator
helm install prometheus-operator deployments/charts/prometheus-operator \
  --namespace monitoring

# 4. cert-manager + ClusterIssuer (CRDs for Certificate / Issuer /
#    ClusterIssuer / Order / Challenge)
#    REQUIRED when any chart issues Certificate or Issuer CRs (HTTPS
#    Ingress, mTLS, customer-facing endpoints). Renders a default
#    selfsigned-issuer ClusterIssuer; flip clusterIssuers.internalCA
#    or clusterIssuers.acme on per environment.
kubectl create namespace cert-manager
helm dependency update deployments/charts/cert-manager
helm install cert-manager deployments/charts/cert-manager \
  --namespace cert-manager

# 5. External Secrets Operator (ESO) — projects vault paths into K8s
#    Secrets via ExternalSecret + ClusterSecretStore CRs.
#    REQUIRED for customer-prod where the umbrella's `existingSecret:`
#    references must come from vault. kind/dev profiles use
#    `auth.create=true` chart modes and skip this entirely.
kubectl create namespace external-secrets
helm dependency update deployments/charts/external-secrets-operator
helm install external-secrets-operator deployments/charts/external-secrets-operator \
  --namespace external-secrets

# 5a. ClusterSecretStore + 5 ExternalSecret CRs (vault → K8s Secret mapping).
#     Edit 00-cluster-secret-store.yaml first to point at your vault
#     address + auth method.
kubectl apply -f deployments/cluster-prereqs/external-secrets/

# 5b. Populate vault with the canonical secret values (random-generated).
#     Requires VAULT_ADDR + VAULT_TOKEN env vars. Add --backup-file to
#     write a sealed copy locally (then move to a password manager).
deployments/scripts/bootstrap-vault-secrets.sh

# 5c. Wait for ESO to sync the 5 K8s Secrets out
kubectl -n isa-bigdata wait externalsecret --all --for=condition=Ready --timeout=2m

# 6. Big-data umbrella
helm dependency update deployments/charts/postgres-bigdata
helm dependency update deployments/charts/minio
helm dependency update deployments/charts/starrocks
helm dependency update deployments/charts/flink
helm dependency update deployments/umbrella/isa-bigdata
helm install bigdata deployments/umbrella/isa-bigdata \
  --namespace isa-bigdata --create-namespace \
  --values deployments/values/customer-prod.yaml
```

## Files in this directory

| File / dir | What it creates |
|---|---|
| `priorityclasses.yaml` | 3 cluster-scoped `PriorityClass` objects: `system-critical` (1,000,000), `infra-critical` (100,000), `application` (1,000, globalDefault) — referenced by `customer-prod.yaml` profile values across kafka / postgres / hms / minio / starrocks / flink / iceberg-tools |
| `external-secrets/` | 1 `ClusterSecretStore` + 5 `ExternalSecret` CRs that project vault paths under `secret/data/isa-bigdata/*` into the 5 K8s Secrets the umbrella references via `existingSecret:`. Companion script: `deployments/scripts/bootstrap-vault-secrets.sh`. |

## Sibling cluster-wide prereqs (Helm charts in `deployments/charts/`)

| Chart | Why it's a prereq |
|---|---|
| `strimzi-operator` (xenoISA/isA_Cloud#259) | Owns Kafka / KafkaNodePool / KafkaUser / KafkaTopic / KafkaConnect / KafkaConnector / KafkaMirrorMaker2 / KafkaRebalance CRDs. Must apply before the umbrella's kafka chart. |
| `prometheus-operator` (xenoISA/isA_Cloud#234) | Owns ServiceMonitor / PodMonitor / Prometheus / AlertManager / PrometheusRule / etc. CRDs. Must apply before the umbrella when any profile flips `serviceMonitor.enabled: true`. |
| `cert-manager` (xenoISA/isA_Cloud#234) | Owns Certificate / CertificateRequest / Issuer / ClusterIssuer / Order / Challenge CRDs. Must apply before any chart that issues `Certificate` CRs (HTTPS Ingress / mTLS / customer-facing TLS). |
| `external-secrets-operator` (xenoISA/isA_Cloud#234) | Owns ClusterSecretStore / SecretStore / ClusterExternalSecret / ExternalSecret / ClusterPushSecret / PushSecret CRDs. Must apply before the 5 ExternalSecret CRs in `external-secrets/` reach a cluster. |

## Why PriorityClass not in a chart?

Helm 3 supports cluster-scoped resources but ties their lifecycle to the
chart release. PriorityClass should outlive any single chart upgrade —
deleting and re-creating it during a release cycle would temporarily
strip priority from running pods and trigger reschedules. Keeping them
as raw manifests applied once at cluster bring-up sidesteps that. Same
reasoning applies to the operator + CRD charts — they live in
`deployments/charts/` (so Helm can manage their version pins) but get
installed BEFORE the umbrella, not as umbrella subcharts.

## Cross-repo context

- `xenoISA/sn-commercial-tower/docs/design/bigdata-architecture.md` §12.4 — the priority-tier policy
- `xenoISA/sn-commercial-tower/docs/design/00-infra-architecture-overview.md` §3 / §6.2 — sizing tables that reference these classes
- `xenoISA/isA_Cloud#234` — parent epic
