# external-secrets-operator

External Secrets Operator (ESO) wrapper. Installs the upstream
`external-secrets/external-secrets` v2.4.1 (operator + 6 cluster-scoped
CRDs) so vault-stored secrets can be projected into K8s Secrets via
`ExternalSecret` / `ClusterSecretStore` CRs.

Tracking issue: [xenoISA/isA_Cloud#234](https://github.com/xenoISA/isA_Cloud/issues/234)
(closes the "🔴 vault + Secret pre-creation" gap from the
deployment-readiness audit).

## Why this exists

The customer-prod profile references **5 `existingSecret`s** across the
big-data charts:

| Secret name | Used by | Keys |
|---|---|---|
| `apicurio-registry-db` | apicurio-registry chart | `username`, `password` |
| `hive-metastore-db` | hive-metastore chart | `username`, `password` |
| `minio-credentials` | minio chart + flink + iceberg-tools | `access-key`, `secret-key`, `rootUser`, `rootPassword` |
| `starrocks-root-credentials` | starrocks chart | `password` |
| `postgres-bigdata-auth` | postgres-bigdata chart | `postgres-password`, `password`, `replication-password` |

Without this chart + the companion `cluster-prereqs/external-secrets/` CRs,
operators have to hand-create those Secrets via `kubectl create secret`
(plaintext, no rotation, fragile) or commit ExternalSecret-flavored
manifests by hand.

## ⚠️ Install order is strict

```bash
# Step 1: ESO operator + CRDs
kubectl create namespace external-secrets
helm dependency update deployments/charts/external-secrets-operator
helm install external-secrets-operator deployments/charts/external-secrets-operator \
  --namespace external-secrets

# Step 2: ClusterSecretStore + 5 ExternalSecret CRs
kubectl apply -f deployments/cluster-prereqs/external-secrets/

# Step 3: populate vault with the canonical secret values
deployments/scripts/bootstrap-vault-secrets.sh

# Step 4: deploy the umbrella (ESO syncs the 5 K8s Secrets from vault)
deployments/scripts/setup-datalake.sh -p customer-prod
```

Reversing step 1 / step 2 produces `no matches for kind "ExternalSecret"
in version "external-secrets.io/v1beta1"`.

## What gets installed

The upstream chart ships:

- **6+ cluster-scoped CRDs**: ClusterSecretStore, SecretStore,
  ClusterExternalSecret, ExternalSecret, ClusterPushSecret, PushSecret
  (exact set varies slightly per release)
- **Operator Deployment** (the controller)
- **Webhook Deployment** (validating + mutating)
- **CertController Deployment** (manages webhook certs)
- ServiceAccounts, ClusterRoles, ClusterRoleBindings, Webhook configs

Footprint: ~3 pods + ~700 MiB RAM + ~0.6 vCPU.

## Why not a vault-specific operator?

`hashicorp/vault-secrets-operator` is vault-only; ESO is multi-store
(vault, AWS SM, GCP SM, Azure KeyVault, etc.). The same ExternalSecret
CR keeps working if the customer ever migrates secret stores. ESO is
the CNCF-graduated choice.

## Bumping ESO

1. Pick a new version from <https://external-secrets.io/latest/>.
2. Update `dependencies.version` in `Chart.yaml` and re-run
   `helm dependency update`.
3. Re-vendor the `.tgz` for air-gap.
4. Confirm no breaking CRD changes (ESO has been stable on `v1beta1` for
   a long time; major bumps would update the apiVersion).

## Out of scope (separate stories)

- **Vault server itself** — the platform's existing vault deploy
  (cluster_operations skill scripts) is assumed
- **AWS SM / GCP SM SecretStores** — not needed for on-prem;
  ClusterSecretStore template only ships the vault flavour
- **Push-back to vault** (PushSecret CRs) — out of scope; we read-only

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#259 — Strimzi Operator chart (sibling cluster-wide prereq)
- xenoISA/isA_Cloud#268 — Prometheus Operator chart (sibling)
- xenoISA/isA_Cloud#269 — cert-manager chart (sibling)
- `deployments/cluster-prereqs/external-secrets/` — the 5 ExternalSecret
  CRs + 1 ClusterSecretStore template that this chart's CRDs make work
- `deployments/scripts/bootstrap-vault-secrets.sh` — populates vault
  with random-generated passwords at the canonical paths
