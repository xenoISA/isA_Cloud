---
name: cluster-operations
description: Kubernetes cluster operations for isA_Cloud. Setup local/staging/production environments, backup/restore, recreate clusters, disaster recovery.
disable-model-invocation: true
---

# Cluster Operations for isA_Cloud

Comprehensive cluster operations including environment setup, backup, restore, and cluster management.

## Quick Start - Environment Setup

```bash
# Local development (Kind)
./scripts/setup-local.sh

# Staging (EKS/GKE)
./scripts/setup-staging.sh

# Production (with HA)
./scripts/setup-production.sh
```

## Available Scripts

| Script | Description |
|--------|-------------|
| `scripts/setup-local.sh` | Setup local Kind cluster with all infrastructure |
| `scripts/setup-staging.sh` | Setup staging on EKS/GKE with ArgoCD |
| `scripts/setup-production.sh` | Setup production with HA configurations |

## Available Operations

1. **Setup environment** - Deploy complete infrastructure (local/staging/production)
2. **Backup all data** - Backup all 8 data stores
3. **Restore all data** - Restore from backup
4. **Recreate cluster** - Tear down and recreate Kubernetes cluster
5. **Health check** - Verify cluster health after operations

## Operation 0: Environment Setup

### Local Development (Kind)

```bash
# Full setup with all infrastructure
./scripts/setup-local.sh

# Infrastructure only (skip applications)
./scripts/setup-local.sh --infra-only

# Rebuild cluster from scratch
./scripts/setup-local.sh --rebuild
```

**What gets deployed:**
- PostgreSQL (localhost:5432)
- Redis (localhost:6379)
- Qdrant (localhost:6333/6334)
- MinIO (localhost:9000/9001)
- Neo4j (localhost:7474/7687)
- NATS (localhost:4222)
- Consul (localhost:8500)
- APISIX (localhost:9080/9180)

### Staging Environment (EKS)

```bash
# Setup on existing cluster
./scripts/setup-staging.sh

# Create new EKS cluster + setup
./scripts/setup-staging.sh --create-cluster

# With custom region
AWS_REGION=eu-west-1 ./scripts/setup-staging.sh
```

### Production Environment (HA)

```bash
# Setup on existing cluster (requires confirmation)
./scripts/setup-production.sh

# Preview changes only
./scripts/setup-production.sh --dry-run

# Create new cluster + setup
./scripts/setup-production.sh --create-cluster
```

**Production deploys HA versions:**
- PostgreSQL HA (3 replicas + pgpool)
- Redis Cluster (6 nodes)
- Qdrant Distributed
- MinIO Distributed
- Neo4j Cluster
- NATS JetStream Cluster
- Consul HA (3 servers)
- APISIX HA (3 replicas)

## Operation 1: Backup All Data

### What Gets Backed Up

```
backups/cluster-backup-{timestamp}/
├── postgres/           # PostgreSQL dumps
├── redis/             # Redis RDB snapshots
├── neo4j/             # Neo4j graph database
├── minio/             # Object storage buckets
├── qdrant/            # Vector database snapshots
├── consul/            # Service registry KV store
└── metadata.json      # Backup metadata
```

### Backup Process

**Step 1: Create backup directory**
```bash
BACKUP_DIR="backups/cluster-backup-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
```

**Step 2: Use existing backup script**

The project already has a backup script at `scripts/backup-cluster-data.sh`. Review and use it:

```bash
# Review the script
cat scripts/backup-cluster-data.sh

# Execute backup
bash scripts/backup-cluster-data.sh
```

**Step 3: Verify backup**

```bash
# Check backup size
du -sh backups/cluster-backup-*/

# List backup contents
ls -la backups/cluster-backup-*/

# Verify metadata
cat backups/cluster-backup-*/metadata.json
```

**Step 4: Document backup**

Create a backup log:
```bash
cat > backups/cluster-backup-*/BACKUP_INFO.md << EOF
# Backup Information

**Timestamp**: $(date)
**Cluster**: ${CLUSTER_NAME}
**Namespace**: ${NAMESPACE}
**Backup Directory**: $(pwd)/backups/cluster-backup-*

## Services Backed Up
- PostgreSQL
- Redis
- Neo4j
- MinIO
- Qdrant
- Consul

## Backup Command
\`\`\`bash
bash scripts/backup-cluster-data.sh
\`\`\`

## Next Steps
To restore:
\`\`\`bash
bash scripts/restore-cluster-data.sh backups/cluster-backup-*/
\`\`\`
EOF
```

### Backup Script Reference

See the existing backup script: [scripts/backup-cluster-data.sh](../../../scripts/backup-cluster-data.sh)

## Operation 2: Restore All Data

### Prerequisites

- Valid backup directory exists
- Cluster is running
- All services are deployed

### Restore Process

**Step 1: List available backups**
```bash
ls -lth backups/
```

**Step 2: Use existing restore script**

```bash
# Review the script
cat scripts/restore-cluster-data.sh

# Execute restore
bash scripts/restore-cluster-data.sh backups/cluster-backup-YYYYMMDD_HHMMSS/
```

**Step 3: Verify restoration**

```bash
# Check pod status
kubectl get pods -n isa-cloud-staging

# Verify PostgreSQL data
kubectl exec -n isa-cloud-staging deploy/postgres -- psql -U postgres -c "SELECT count(*) FROM accounts;"

# Verify Redis data
kubectl exec -n isa-cloud-staging deploy/redis -- redis-cli DBSIZE

# Verify Consul services
kubectl exec -n isa-cloud-staging consul-0 -- consul catalog services

# Verify MinIO buckets
kubectl exec -n isa-cloud-staging deploy/minio -- mc ls local/
```

**Step 4: Health check**

Run comprehensive health checks after restore:
```bash
# Run tests
bash tests/test_auth_via_apisix.sh
bash tests/test_mcp_via_apisix.sh

# Check all service health
kubectl exec -n isa-cloud-staging deploy/apisix -- \
  curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq '.list | length'
```

### Restore Script Reference

See the existing restore script: [scripts/restore-cluster-data.sh](../../../scripts/restore-cluster-data.sh)

## Operation 3: Recreate Kubernetes Cluster

### When to Recreate

- Cluster corruption
- Major version upgrade
- Infrastructure migration
- Testing deployment from scratch

### Cluster Types

#### Local KIND Cluster

**Step 1: Backup current data** (if needed)
```bash
bash scripts/backup-cluster-data.sh
```

**Step 2: Delete existing cluster**
```bash
kind delete cluster --name isa-cloud
```

**Step 3: Create new cluster**
```bash
cd deployments/kubernetes/scripts

# Create cluster
./kind-setup.sh
```

**Step 4: Build and load images**
```bash
# Build gRPC services
./kind-build-load.sh
```

**Step 5: Deploy all services**
```bash
# Deploy infrastructure and services
./kind-deploy.sh
```

**Step 6: Verify deployment**
```bash
# Check all pods are running
kubectl get pods -n isa-cloud-staging

# Wait for all pods to be ready
kubectl wait --for=condition=ready pod --all -n isa-cloud-staging --timeout=300s

# Run health checks
./check-services.sh
```

**Step 7: Restore data** (if backed up)
```bash
cd ../../../
bash scripts/restore-cluster-data.sh backups/cluster-backup-YYYYMMDD_HHMMSS/
```

#### EKS Cluster (AWS)

**Step 1: Backup data and configs**
```bash
# Backup data
bash scripts/backup-cluster-data.sh

# Export current configs
kubectl get all -n isa-cloud-staging -o yaml > backup-k8s-configs.yaml
```

**Step 2: Delete existing cluster**
```bash
eksctl delete cluster --name isa-cloud-staging --region us-east-1
```

**Step 3: Create new cluster**
```bash
eksctl create cluster \
  --name isa-cloud-staging \
  --region us-east-1 \
  --nodegroup-name workers \
  --node-type m5.xlarge \
  --nodes 3 \
  --managed
```

**Step 4: Configure kubectl**
```bash
aws eks update-kubeconfig --name isa-cloud-staging --region us-east-1
```

**Step 5: Install ArgoCD**
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f \
  https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

**Step 6: Deploy applications via ArgoCD**
```bash
# Apply ArgoCD application
kubectl apply -f deployments/argocd/apps/staging/

# Wait for sync
kubectl wait --for=condition=Synced app --all -n argocd --timeout=600s
```

**Step 7: Verify and restore**
```bash
# Check pod status
kubectl get pods -n isa-cloud-staging

# Restore data
bash scripts/restore-cluster-data.sh backups/cluster-backup-YYYYMMDD_HHMMSS/
```

## Operation 4: Disaster Recovery

### Full DR Workflow

**1. Assess damage**
```bash
# Check cluster status
kubectl cluster-info
kubectl get nodes
kubectl get pods --all-namespaces

# Check which services are down
kubectl get pods -n isa-cloud-staging | grep -v Running
```

**2. Identify latest backup**
```bash
# List backups by date
ls -lth backups/

# Check backup metadata
cat backups/cluster-backup-*/metadata.json | jq
```

**3. Decision tree**

```
Is cluster accessible?
├─ YES → Restore data only
│   └─ bash scripts/restore-cluster-data.sh <backup-dir>
│
└─ NO → Full cluster recreation
    ├─ Delete cluster
    ├─ Create new cluster
    ├─ Deploy services
    └─ Restore data
```

**4. Execute recovery**

Based on decision above, follow either:
- **Operation 2** (Restore data only) if cluster is healthy
- **Operation 3** (Recreate cluster) if cluster is damaged

**5. Verification checklist**

```bash
# Infrastructure health
kubectl get pods -n isa-cloud-staging
kubectl top nodes

# Service health
bash tests/test_auth_via_apisix.sh
bash tests/test_mcp_via_apisix.sh
bash tests/test_agent_via_apisix.sh

# Data integrity
# (Add specific data checks based on your services)

# Consul registration
kubectl exec -n isa-cloud-staging consul-0 -- consul catalog services

# APISIX routes
kubectl exec -n isa-cloud-staging deploy/apisix -- \
  curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq '.list | length'
```

## Quick Reference Commands

### Backup
```bash
# Full backup
bash scripts/backup-cluster-data.sh

# List backups
ls -lth backups/

# Check backup size
du -sh backups/cluster-backup-*/
```

### Restore
```bash
# Restore from backup
bash scripts/restore-cluster-data.sh backups/cluster-backup-YYYYMMDD_HHMMSS/

# Verify restoration
kubectl get pods -n isa-cloud-staging
```

### Cluster Lifecycle
```bash
# KIND: Delete and recreate
kind delete cluster --name isa-cloud
cd deployments/kubernetes/scripts
./kind-setup.sh
./kind-build-load.sh
./kind-deploy.sh

# EKS: Delete and recreate
eksctl delete cluster --name isa-cloud-staging --region us-east-1
eksctl create cluster --name isa-cloud-staging --region us-east-1 ...
```

### Health Checks
```bash
# Pod status
kubectl get pods -n isa-cloud-staging

# Service tests
bash tests/test_auth_via_apisix.sh
bash tests/test_mcp_via_apisix.sh

# Consul services
kubectl exec -n isa-cloud-staging consul-0 -- consul catalog services

# APISIX routes
kubectl exec -n isa-cloud-staging deploy/apisix -- \
  curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq
```

## Important Notes

### Safety First

1. **Always backup before major operations**
2. **Test restore procedures regularly**
3. **Keep multiple backup versions**
4. **Document cluster configuration changes**
5. **Have rollback plan ready**

### Backup Best Practices

- Schedule regular backups (daily/weekly)
- Store backups off-cluster (S3, GCS, etc.)
- Test restoration process monthly
- Keep backups for 30 days minimum
- Document backup and restore procedures

### Cluster Recreation Considerations

- **Network policies** may need reconfiguration
- **Persistent volumes** will be lost (backup data first!)
- **Load balancers** may get new IPs
- **DNS records** may need updates
- **Secrets** need to be recreated or restored

## Troubleshooting

### Backup Issues

**Problem**: Script fails with permission errors
```bash
# Solution: Check namespace and permissions
kubectl auth can-i get pods -n isa-cloud-staging
kubectl get serviceaccounts -n isa-cloud-staging
```

**Problem**: Backup directory full
```bash
# Solution: Clean old backups
ls -lt backups/ | tail -n +10 | awk '{print $9}' | xargs rm -rf
```

### Restore Issues

**Problem**: Services fail to start after restore
```bash
# Solution: Check pod logs
kubectl logs -n isa-cloud-staging <pod-name>
kubectl describe pod -n isa-cloud-staging <pod-name>
```

**Problem**: Data partially restored
```bash
# Solution: Check restore logs and retry specific services
# Re-run restore script with verbose output
bash -x scripts/restore-cluster-data.sh backups/cluster-backup-*/
```

### Cluster Recreation Issues

**Problem**: KIND cluster creation fails
```bash
# Solution: Clean Docker and retry
docker system prune -a
kind delete cluster --name isa-cloud
./kind-setup.sh
```

**Problem**: Pods stuck in Pending state
```bash
# Solution: Check resources and node capacity
kubectl describe nodes
kubectl top nodes
kubectl describe pod <pod-name> -n isa-cloud-staging
```

### Port Binding Issues (KIND)

**Problem**: After Docker restart, some port mappings are missing or not working

This is a known Docker/KIND issue where port bindings are configured in the container but fail to establish after Docker restarts.

**Symptoms**:
- Services like PostgreSQL (5432), NATS (4222), etc. are not accessible from localhost
- `docker port isa-cloud-local-control-plane` shows fewer ports than expected
- `nc -zv localhost <port>` fails with "Connection refused"

**Diagnosis**:
```bash
# Check configured vs actual port bindings
# Configured (should have all ports):
docker inspect isa-cloud-local-control-plane --format '{{json .HostConfig.PortBindings}}' | python3 -m json.tool | wc -l

# Actually bound (may be fewer after Docker restart):
docker port isa-cloud-local-control-plane | wc -l

# Test specific ports
nc -zv localhost 5432  # PostgreSQL
nc -zv localhost 4222  # NATS
nc -zv localhost 6379  # Redis
```

**Solution**: Restart the KIND control-plane container to re-establish port bindings
```bash
# Restart the control-plane container
docker restart isa-cloud-local-control-plane

# Wait for it to be ready
sleep 10

# Verify port bindings are restored
docker port isa-cloud-local-control-plane | wc -l

# Test connectivity
nc -zv localhost 5432  # PostgreSQL
nc -zv localhost 4222  # NATS
```

**Root Cause**: Docker sometimes fails to properly bind ports when containers restart, even though the port configuration exists. This is a race condition or Docker networking state issue.

**Prevention**: After restarting Docker Desktop or the Docker daemon, always verify port bindings and restart the KIND control-plane if needed.

## Related Documentation

- [README.md](../../../README.md) - Main project documentation
- [scripts/backup-cluster-data.sh](../../../scripts/backup-cluster-data.sh) - Backup script
- [scripts/restore-cluster-data.sh](../../../scripts/restore-cluster-data.sh) - Restore script
- [deployments/kubernetes/scripts/](../../../deployments/kubernetes/scripts/) - Deployment scripts

## Usage Examples

### Example 1: Scheduled Backup

```bash
# Run backup
/cluster-operations

# Then say: "Perform a full backup of all cluster data"
```

### Example 2: Disaster Recovery

```bash
/cluster-operations

# Then say: "The cluster is corrupted. Recreate the KIND cluster and restore from the latest backup"
```

### Example 3: Migration

```bash
/cluster-operations

# Then say: "Backup current cluster, create a new EKS cluster, and restore data"
```
