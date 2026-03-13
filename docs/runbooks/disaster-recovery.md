# Runbook: Disaster Recovery (DR)

## Scope

Full recovery procedure for the isA platform when multiple services or the entire cluster is lost. Covers all data stores: PostgreSQL, Redis, Neo4j, MinIO, Qdrant, Consul, NATS.

## Prerequisites

- Access to backup storage (location where `backup-cluster-data.sh` writes)
- `kubectl` configured with cluster access
- Helm installed
- `scripts/backup-cluster-data.sh` and `scripts/restore-cluster-data.sh` available

## Quick Assessment

```bash
# Check cluster health
kubectl get nodes
kubectl get pods -n isa-cloud-local --no-headers | awk '{print $3}' | sort | uniq -c | sort -rn

# Count healthy vs unhealthy pods
echo "Running: $(kubectl get pods -n isa-cloud-local --field-selector=status.phase=Running --no-headers | wc -l)"
echo "Failed:  $(kubectl get pods -n isa-cloud-local --field-selector=status.phase=Failed --no-headers | wc -l)"
echo "Pending: $(kubectl get pods -n isa-cloud-local --field-selector=status.phase=Pending --no-headers | wc -l)"

# Check PVCs (data durability)
kubectl get pvc -n isa-cloud-local
```

## DR Scenarios

### Scenario 1: Single Service Failure

**Impact**: One data store or application pod is down.

**Recovery**:
1. Check pod status and events:
   ```bash
   kubectl describe pod -n isa-cloud-local <pod-name>
   ```
2. Try restart first:
   ```bash
   kubectl rollout restart deploy/<service-name> -n isa-cloud-local
   ```
3. If data is corrupted, restore from backup:
   ```bash
   ./scripts/restore-cluster-data.sh --service <service> --backup-dir ./backups/latest
   ```
4. Refer to the service-specific runbook (postgresql-failover.md, redis-recovery.md)

### Scenario 2: Namespace Wipe (All Pods Lost, PVCs Intact)

**Impact**: All pods deleted but PVCs still have data.

**Recovery**:
1. Verify PVCs are intact:
   ```bash
   kubectl get pvc -n isa-cloud-local
   ```
2. Re-deploy all services via Helm:
   ```bash
   # Re-install infrastructure
   helm upgrade --install postgresql bitnami/postgresql -n isa-cloud-local -f deployments/values/postgresql-values.yaml
   helm upgrade --install redis bitnami/redis -n isa-cloud-local -f deployments/values/redis-values.yaml
   helm upgrade --install neo4j neo4j/neo4j -n isa-cloud-local -f deployments/values/neo4j-values.yaml
   helm upgrade --install qdrant qdrant/qdrant -n isa-cloud-local -f deployments/values/qdrant-values.yaml
   helm upgrade --install minio minio/minio -n isa-cloud-local -f deployments/values/minio-values.yaml
   helm upgrade --install consul hashicorp/consul -n isa-cloud-local -f deployments/values/consul-values.yaml
   helm upgrade --install nats nats/nats -n isa-cloud-local -f deployments/values/nats-values.yaml
   helm upgrade --install apisix apisix/apisix -n isa-cloud-local -f deployments/values/apisix-values.yaml

   # Re-install application services
   helm upgrade --install isa-services deployments/charts/isa-service/ -n isa-cloud-local
   ```
3. Data should be picked up from existing PVCs
4. Verify each service health (see Quick Assessment above)

### Scenario 3: Full Cluster Loss (PVCs and Pods Lost)

**Impact**: Complete data loss — requires restore from external backup.

**Recovery**:

#### Step 1: Provision New Cluster
```bash
# For local dev (KIND)
kind create cluster --name isa-cloud-local
kubectl create namespace isa-cloud-local

# For cloud (adjust for your provider)
# Follow the original cluster provisioning docs
```

#### Step 2: Install Infrastructure
```bash
# Add Helm repos
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add neo4j https://helm.neo4j.com/neo4j
helm repo add qdrant https://qdrant.github.io/qdrant-helm
helm repo add minio https://charts.min.io/
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo add nats https://nats-io.github.io/k8s/helm/charts/
helm repo add apisix https://charts.apiseven.com
helm repo update

# Install all data stores (in dependency order)
helm install postgresql bitnami/postgresql -n isa-cloud-local -f deployments/values/postgresql-values.yaml
helm install redis bitnami/redis -n isa-cloud-local -f deployments/values/redis-values.yaml
helm install consul hashicorp/consul -n isa-cloud-local -f deployments/values/consul-values.yaml
helm install nats nats/nats -n isa-cloud-local -f deployments/values/nats-values.yaml
helm install neo4j neo4j/neo4j -n isa-cloud-local -f deployments/values/neo4j-values.yaml
helm install qdrant qdrant/qdrant -n isa-cloud-local -f deployments/values/qdrant-values.yaml
helm install minio minio/minio -n isa-cloud-local -f deployments/values/minio-values.yaml
helm install apisix apisix/apisix -n isa-cloud-local -f deployments/values/apisix-values.yaml
```

#### Step 3: Wait for All Pods Ready
```bash
kubectl wait --for=condition=Ready pods --all -n isa-cloud-local --timeout=300s
```

#### Step 4: Restore Data from Backup
```bash
# Restore all services from the most recent backup
./scripts/restore-cluster-data.sh --backup-dir ./backups/latest

# Or restore individual services
./scripts/restore-cluster-data.sh --service postgresql --backup-dir ./backups/latest
./scripts/restore-cluster-data.sh --service redis --backup-dir ./backups/latest
./scripts/restore-cluster-data.sh --service neo4j --backup-dir ./backups/latest
./scripts/restore-cluster-data.sh --service minio --backup-dir ./backups/latest
./scripts/restore-cluster-data.sh --service qdrant --backup-dir ./backups/latest
./scripts/restore-cluster-data.sh --service consul --backup-dir ./backups/latest
./scripts/restore-cluster-data.sh --service nats --backup-dir ./backups/latest
```

#### Step 5: Deploy Application Services
```bash
helm install isa-services deployments/charts/isa-service/ -n isa-cloud-local
```

#### Step 6: Re-register Services with Consul
```bash
# Services auto-register on startup via consul_lifespan()
# Verify registrations
curl -s http://localhost:8500/v1/catalog/services | jq 'keys[]'
```

#### Step 7: Restore APISIX Routes
```bash
./scripts/restore-cluster-data.sh --service apisix --backup-dir ./backups/latest

# Verify routes
curl -s http://localhost:9180/apisix/admin/routes -H "X-API-KEY: ${APISIX_ADMIN_KEY}" | jq '.list[].value.uri'
```

#### Step 8: Full Verification
```bash
# Check all pods running
kubectl get pods -n isa-cloud-local

# Check all data stores healthy
kubectl exec -n isa-cloud-local deploy/postgresql -- pg_isready -U postgres
kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli PING
curl -s http://localhost:6333/collections | jq '.status'
curl -s http://localhost:8500/v1/status/leader
```

## Backup Strategy

### Automated Backups
```bash
# Create a full backup (all services)
./scripts/backup-cluster-data.sh

# Schedule via cron (example: daily at 2am)
# 0 2 * * * cd /path/to/isA_Cloud && ./scripts/backup-cluster-data.sh >> /var/log/isa-backup.log 2>&1
```

### Backup Verification
```bash
# List available backups
ls -lt backups/

# Verify backup integrity (check file sizes are non-zero)
find backups/latest -type f -empty -print
```

### Backup Retention
- **Local dev**: Keep last 3 backups
- **Staging**: Keep last 7 daily + 4 weekly
- **Production**: Keep last 30 daily + 12 weekly + 12 monthly

## Recovery Time Objectives

| Scenario | RTO (target) | Steps |
|----------|-------------|-------|
| Single service failure | < 5 min | Restart pod |
| Single service data loss | < 15 min | Restore from backup |
| Namespace wipe (PVCs intact) | < 30 min | Re-deploy via Helm |
| Full cluster loss | < 2 hours | New cluster + full restore |

## Post-Recovery Checklist

- [ ] All pods in `Running` state
- [ ] All PVCs bound
- [ ] PostgreSQL: tables exist, row counts match expected
- [ ] Redis: key count non-zero, pub/sub channels active
- [ ] Consul: all services registered
- [ ] NATS: streams and consumers recreated
- [ ] APISIX: routes responding
- [ ] Neo4j: node/relationship counts match expected
- [ ] Qdrant: collections exist with expected point counts
- [ ] MinIO: buckets exist with expected object counts
- [ ] Application health endpoints all return healthy
- [ ] Smoke tests pass
