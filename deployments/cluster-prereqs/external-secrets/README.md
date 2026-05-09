# external-secrets — vault → K8s Secret CRs

Five `ExternalSecret` CRs + one `ClusterSecretStore` that map the
customer's vault paths into the K8s Secrets the big-data charts
reference via `existingSecret`.

Apply order:

```bash
# 1. Install ESO operator + CRDs (sibling chart)
helm install external-secrets-operator deployments/charts/external-secrets-operator \
  --namespace external-secrets --create-namespace

# 2. Apply the 6 manifests in this directory
kubectl apply -f deployments/cluster-prereqs/external-secrets/

# 3. Populate vault with the canonical secret values
deployments/scripts/bootstrap-vault-secrets.sh

# 4. Wait for ExternalSecrets to sync
kubectl -n isa-bigdata wait externalsecret --all --for=condition=Ready --timeout=2m

# 5. Verify the 5 K8s Secrets exist
kubectl -n isa-bigdata get secrets \
  apicurio-registry-db hive-metastore-db minio-credentials \
  starrocks-root-credentials postgres-bigdata-auth
```

## File index

| File | Renders |
|---|---|
| `00-cluster-secret-store.yaml` | `ClusterSecretStore/isa-bigdata-vault` — vault provider config |
| `10-apicurio-registry-db.yaml` | `ExternalSecret` → `Secret/apicurio-registry-db` (2 keys) |
| `11-hive-metastore-db.yaml` | `ExternalSecret` → `Secret/hive-metastore-db` (2 keys) |
| `12-minio-credentials.yaml` | `ExternalSecret` → `Secret/minio-credentials` (4 keys) |
| `13-starrocks-root-credentials.yaml` | `ExternalSecret` → `Secret/starrocks-root-credentials` (1 key) |
| `14-postgres-bigdata-auth.yaml` | `ExternalSecret` → `Secret/postgres-bigdata-auth` (3 keys) |

## Vault path layout (canonical)

```
secret/data/isa-bigdata/
├── apicurio-registry-db
│     ├── username
│     └── password
├── hive-metastore-db
│     ├── username
│     └── password
├── minio-credentials
│     ├── access-key
│     ├── secret-key
│     ├── rootUser
│     └── rootPassword
├── starrocks-root-credentials
│     └── password
└── postgres-bigdata-auth
      ├── postgres-password
      ├── password
      └── replication-password
```

## ClusterSecretStore customization

`00-cluster-secret-store.yaml` defaults to:

- vault address `http://vault.vault.svc.cluster.local:8200` (in-cluster vault)
- KV-v2 mount `secret/`
- Kubernetes auth via the `external-secrets` ServiceAccount
- Vault role `isa-bigdata-reader` (must have read on `secret/data/isa-bigdata/*`)

Edit the file directly OR overlay via Kustomize before `kubectl apply`.

### Vault role setup (one-time, before applying these manifests)

```bash
# In vault — grant the ESO controller's SA read access
vault auth enable kubernetes  # if not already enabled

vault write auth/kubernetes/role/isa-bigdata-reader \
  bound_service_account_names=external-secrets \
  bound_service_account_namespaces=external-secrets \
  policies=isa-bigdata-reader \
  ttl=1h

vault policy write isa-bigdata-reader - <<EOF
path "secret/data/isa-bigdata/*" {
  capabilities = ["read"]
}
EOF
```

The `bootstrap-vault-secrets.sh` script handles the per-secret value
writes; the role + policy above are a separate one-time vault admin
step.

## Cross-repo context

- xenoISA/isA_Cloud#234 — parent epic
- xenoISA/isA_Cloud#259 / #266 / #268 / #269 — sibling cluster-wide prereqs (Strimzi, PriorityClass, Prometheus, cert-manager)
- xenoISA/isA_Cloud `deployments/scripts/bootstrap-vault-secrets.sh` — populates the vault paths above with random-generated passwords
- xenoISA/isA_Cloud `deployments/values/customer-prod.yaml` — the umbrella values that reference these 5 K8s Secrets via `existingSecret:`
