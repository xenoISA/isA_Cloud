# ISA Cloud — Production Deployment Guide

> Step-by-step guide for deploying the full isA Cloud platform on any Kubernetes cluster.
> Provider-agnostic with Infotrend Enterprise Cloud as the reference implementation.

## Prerequisites

### Cluster Requirements

| Profile | Nodes | CPU (per node) | RAM (per node) | Disk (per node) |
|---------|-------|----------------|----------------|-----------------|
| 3-node  | 3     | 8 cores        | 16 GB          | 500 GB SSD      |
| 5-node  | 5     | 8 cores        | 32 GB          | 500 GB SSD      |
| Default | 5+    | 16 cores       | 32 GB          | 1 TB SSD        |

### Software Requirements

- Kubernetes ≥ 1.27
- Helm ≥ 3.12
- kubectl configured with cluster access
- ArgoCD (for application services deployment)
- `mc` (MinIO client — optional, for backups)

### Network Requirements

- Inter-node communication (all ports)
- DNS resolution (CoreDNS)
- Access to container registries: `docker.io`, `quay.io`, `gcr.io`, `registry.k8s.io`
- Helm chart repositories (see deploy.sh for full list)

---

## Step 0: Choose Your Provider Profile

The deployment uses **provider profiles** to abstract storage configuration. Each profile maps logical storage tiers to provider-specific StorageClasses.

Available profiles:

| Profile | Block | Fast | NFS | Object | Use Case |
|---------|-------|------|-----|--------|----------|
| `infotrend` | infotrend-block | infotrend-block-fast | infotrend-nfs | infotrend-object | Infotrend Enterprise Cloud |
| `aws` | gp3 | io2 | efs-sc | — (S3 via IAM) | AWS EKS |
| `generic` | (default) | (default) | (default) | (default) | Any K8s cluster |

To add a new provider, create `profiles/<provider-name>.yaml`:

```yaml
provider: my-provider
description: "My provider description"
storage:
  block: my-block-sc
  fast: my-fast-sc
  nfs: my-nfs-sc
  object: my-object-sc
```

---

## Step 1: Prepare Storage Classes

### Infotrend Example

1. Install the Infotrend CSI driver on all nodes (refer to Infotrend documentation)
2. Apply StorageClass manifests:

```bash
kubectl apply -f manifests/storage-classes/infotrend-storage-classes.yaml
```

3. Verify:

```bash
kubectl get storageclass
# Should show: infotrend-block, infotrend-block-fast, infotrend-nfs, infotrend-object
```

### Generic / Other Providers

Ensure your cluster has a default StorageClass or create provider-specific classes and update the profile file.

---

## Step 2: Run Pre-Flight Checks

```bash
cd deployments/kubernetes/production/scripts

./preflight.sh --provider infotrend --nodes 3
```

This validates:
- Kubernetes version
- Node count and capacity
- StorageClass availability
- Helm repo access
- Network connectivity

Fix any errors before proceeding.

---

## Step 3: Deploy Secrets Management

```bash
./deploy.sh secrets --provider infotrend
```

This deploys:
- **HashiCorp Vault** (HA with Consul backend)
- **External Secrets Operator** (syncs Vault secrets to K8s)
- ClusterSecretStore and ExternalSecret CRDs

### First-time setup

After Vault deploys, initialize and unseal it:

```bash
./vault-init.sh
```

This will:
1. Initialize Vault (generates unseal keys and root token — **save these securely**)
2. Unseal Vault
3. Seed required secrets (PostgreSQL, Redis, Neo4j, MinIO credentials)

### Verify

```bash
kubectl get pods -n isa-cloud-production -l app.kubernetes.io/name=vault
# All pods should be Running and Ready

kubectl get externalsecret -n isa-cloud-production
# All secrets should show status: SecretSynced
```

---

## Step 4: Deploy Infrastructure

```bash
./deploy.sh infrastructure --provider infotrend --nodes 3
```

This deploys in order:
1. **etcd** (3 replicas) — APISIX backend
2. **PostgreSQL HA** (2 replicas for 3-node, 3 for 5-node)
3. **Redis Cluster** (3 masters for 3-node, 6 for default)
4. **Neo4j Cluster** (3 replicas)
5. **MinIO Distributed** (4 replicas)
6. **NATS JetStream** (3 replicas)
7. **Qdrant Distributed** (3 replicas)
8. **EMQX Cluster** (3 replicas)
9. **Consul** (3 servers + clients)
10. **APISIX** (2 replicas)
11. **Consul-APISIX sync** CronJob

Each step requires manual confirmation.

### Verify

After deployment completes, the health check runs automatically. You can also run it manually:

```bash
./health-check.sh
```

Expected output: all components green, 16384 Redis slots covered, Consul services registered, APISIX routes synced.

---

## Step 5: Deploy Application Services

Application services are deployed via ArgoCD (GitOps):

```bash
./deploy.sh services
```

This syncs all production ArgoCD applications. Ensure ArgoCD is configured and logged in:

```bash
argocd login <argocd-server>
argocd app list | grep production
```

---

## Step 6: Deploy ML Platform (Optional)

```bash
./deploy.sh mlplatform --provider infotrend --nodes 3
```

Deploys:
- KubeRay Operator + Ray Cluster
- MLflow tracking server
- JupyterHub

---

## Step 7: Final Verification

Run the full health check:

```bash
./health-check.sh
```

Check all components:

```bash
./deploy.sh status
```

---

## Quick Reference

### Full deployment (one command)

```bash
./deploy.sh all --provider infotrend --nodes 3
```

### Check status

```bash
./deploy.sh status
```

### Rollback a component

```bash
./deploy.sh rollback postgresql
```

### Backup

```bash
./scripts/backup/backup.sh --provider infotrend
```

### Restore

```bash
./scripts/backup/restore.sh /path/to/backup/20260410-120000
```

---

## Troubleshooting

### PVC stuck in Pending

StorageClass doesn't exist or CSI driver isn't installed:

```bash
kubectl describe pvc <pvc-name> -n isa-cloud-production
# Check Events section for provisioner errors
```

### Pod stuck in CrashLoopBackOff

Check logs:

```bash
kubectl logs <pod-name> -n isa-cloud-production --previous
```

### Redis Cluster incomplete

Slots not fully covered — may need manual rebalancing:

```bash
kubectl exec -it redis-0 -n isa-cloud-production -- redis-cli --cluster fix redis-0:6379
```

### APISIX routes not syncing

Check Consul-APISIX sync CronJob:

```bash
kubectl get cronjob -n isa-cloud-production
kubectl logs job/<latest-sync-job> -n isa-cloud-production
```

### Vault sealed after restart

Vault does not auto-unseal by default:

```bash
kubectl exec -it vault-0 -n isa-cloud-production -- vault operator unseal <key>
```

---

## Adding a New Provider

1. Create `profiles/<provider>.yaml` with storage mappings
2. (Optional) Create `manifests/storage-classes/<provider>-storage-classes.yaml`
3. (Optional) Create `profiles/3-node/<component>.yaml` overrides if your nodes have different specs
4. Test: `./preflight.sh --provider <name> --nodes <count>`
5. Deploy: `./deploy.sh all --provider <name> --nodes <count>`
