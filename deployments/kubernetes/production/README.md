# ISA Cloud - Production Kubernetes Deployment

Production environment deployment for the ISA Cloud platform with High Availability configuration.

## Prerequisites

### Required Tools
- `kubectl` - Kubernetes CLI
- `helm` - Helm package manager (v3+)
- `argocd` - ArgoCD CLI (for service deployment)

### Required Secrets

**CRITICAL:** Never commit real secrets to version control.

```bash
# Create namespace
kubectl create namespace isa-cloud-production

# Apply secrets (edit template with real values first!)
kubectl apply -f secrets/infrastructure-secrets.yaml
```

Required secrets:
- `postgresql-secret` - PostgreSQL credentials
- `redis-secret` - Redis password
- `neo4j-secret` - Neo4j credentials
- `minio-secret` - MinIO access keys

### Storage Classes

Production requires fast SSD storage. Ensure these storage classes exist:
- `infotrend-block` - Standard block storage
- `infotrend-block-fast` - Fast SSD storage (for etcd, databases)

## Deployment

### Safety First

Production deployments include safety gates:
- Confirmation prompts before destructive operations
- kubectl context verification
- Secret existence checks
- Dry-run previews for ArgoCD syncs

### Commands

```bash
cd deployments/kubernetes/production

# Check current status
./scripts/deploy.sh status

# Deploy HA infrastructure
./scripts/deploy.sh infrastructure

# Deploy ML platform (Ray, MLflow, JupyterHub)
./scripts/deploy.sh mlplatform

# Sync ArgoCD applications (with confirmation)
./scripts/deploy.sh services

# Deploy etcd only
./scripts/deploy.sh etcd

# Rollback a Helm release
./scripts/deploy.sh rollback <release-name>

# Health check with HA status
./scripts/check-services.sh
```

### Deployment Order

1. Create namespace and secrets
2. Deploy etcd cluster (APISIX dependency)
3. Deploy databases (PostgreSQL HA, Redis Cluster, Neo4j)
4. Deploy storage (MinIO Distributed)
5. Deploy messaging (NATS JetStream, EMQX Cluster)
6. Deploy vector database (Qdrant Distributed)
7. Deploy service discovery (Consul Cluster)
8. Deploy API gateway (APISIX)
9. Apply Consul-APISIX sync CronJob
10. Deploy ML platform (optional)
11. Sync ArgoCD applications

## Architecture

### Infrastructure Services (HA)

| Service | Replicas | HA Configuration | Storage |
|---------|----------|------------------|---------|
| etcd | 3 | Raft consensus | 20Gi fast SSD |
| PostgreSQL | 3 | Primary + 2 standby (Pgpool) | 100Gi |
| Redis | 6 | Cluster mode (3 masters + 3 replicas) | 20Gi |
| Neo4j | 3 | Causal cluster | 50Gi |
| MinIO | 4 | Distributed mode | 100Gi |
| NATS | 3 | JetStream cluster | 10Gi |
| Qdrant | 3 | Distributed sharding | 50Gi |
| EMQX | 3 | Cluster mode | - |
| Consul | 3 | Server cluster | 10Gi |
| APISIX | 2 | Active-active | - |

### ML Platform

| Service | Replicas | Purpose |
|---------|----------|---------|
| KubeRay Operator | 1 | Ray cluster management |
| Ray Head | 1 | Cluster coordinator |
| Ray Workers | 2+ | Distributed compute |
| MLflow | 2 | Experiment tracking |
| JupyterHub | 1 | Notebook environment |

### Pod Disruption Budgets

All critical services have PDBs configured:
- etcd: minAvailable 2
- PostgreSQL: minAvailable 2
- Redis: minAvailable 4
- Consul: minAvailable 2

### Resource Requirements

Minimum cluster resources for production:
- **Nodes:** 5+ worker nodes
- **CPU:** 32+ cores total
- **Memory:** 128GB+ total
- **Storage:** 500GB+ fast SSD

## Health Monitoring

```bash
# Full HA-aware health check
./scripts/check-services.sh

# Quick status
./scripts/deploy.sh status

# Pod status
kubectl get pods -n isa-cloud-production -o wide

# Check PDBs
kubectl get pdb -n isa-cloud-production

# Check HPAs
kubectl get hpa -n isa-cloud-production
```

## Troubleshooting

### etcd Cluster Issues

```bash
# Check cluster health
kubectl exec -n isa-cloud-production etcd-0 -- etcdctl endpoint health --cluster

# Check member list
kubectl exec -n isa-cloud-production etcd-0 -- etcdctl member list

# Check leader
kubectl exec -n isa-cloud-production etcd-0 -- etcdctl endpoint status --cluster
```

### PostgreSQL HA Issues

```bash
# Check replication status
kubectl exec -n isa-cloud-production postgresql-postgresql-ha-0 -- \
  psql -U postgres -c "SELECT * FROM pg_stat_replication;"

# Check Pgpool status
kubectl exec -n isa-cloud-production postgresql-postgresql-ha-pgpool-0 -- \
  pgpool -n show pool_nodes
```

### Redis Cluster Issues

```bash
# Check cluster state
kubectl exec -n isa-cloud-production redis-redis-cluster-0 -- redis-cli cluster info

# Check nodes
kubectl exec -n isa-cloud-production redis-redis-cluster-0 -- redis-cli cluster nodes
```

### Consul Cluster Issues

```bash
# Check cluster members
kubectl exec -n isa-cloud-production consul-server-0 -- consul members

# Check leader
kubectl exec -n isa-cloud-production consul-server-0 -- consul operator raft list-peers
```

### APISIX Issues

```bash
# Check routes
kubectl exec -n isa-cloud-production <apisix-pod> -- \
  curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1"

# Check upstreams
kubectl exec -n isa-cloud-production <apisix-pod> -- \
  curl -s http://localhost:9180/apisix/admin/upstreams \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1"
```

## Emergency Procedures

### Service Rollback

```bash
# Rollback Helm release
./scripts/deploy.sh rollback postgresql

# Or manually
helm rollback postgresql -n isa-cloud-production
```

### etcd Recovery

If etcd cluster loses quorum:

```bash
# Check which members are healthy
kubectl exec -n isa-cloud-production etcd-0 -- etcdctl member list

# Remove failed member
kubectl exec -n isa-cloud-production etcd-0 -- \
  etcdctl member remove <member-id>

# Delete failed pod's PVC and let StatefulSet recreate
kubectl delete pvc etcd-data-etcd-2 -n isa-cloud-production
kubectl delete pod etcd-2 -n isa-cloud-production

# Add new member
kubectl exec -n isa-cloud-production etcd-0 -- \
  etcdctl member add etcd-2 --peer-urls=http://etcd-2.etcd-headless.isa-cloud-production.svc.cluster.local:2380
```

### PostgreSQL Failover

```bash
# Trigger manual failover via Pgpool
kubectl exec -n isa-cloud-production postgresql-postgresql-ha-pgpool-0 -- \
  pgpool -n follow primary
```

### Full Disaster Recovery

```bash
# Restore from backup
./scripts/backup.sh restore <backup-date>
```

## Port Forwarding

For debugging (not recommended for regular access):

```bash
# APISIX Gateway
kubectl port-forward -n isa-cloud-production svc/apisix-gateway 8080:80

# Consul UI
kubectl port-forward -n isa-cloud-production svc/consul-server 8500:8500

# Grafana (if deployed)
kubectl port-forward -n isa-cloud-production svc/grafana 3000:3000
```

## Configuration Files

```
production/
├── manifests/
│   ├── etcd.yaml                     # HA etcd StatefulSet
│   └── consul-apisix-sync.yaml       # Route sync CronJob
├── values/
│   ├── apisix.yaml                   # APISIX HA values
│   ├── consul.yaml                   # Consul cluster values
│   ├── emqx-cluster.yaml             # EMQX cluster values
│   ├── jupyterhub.yaml               # JupyterHub values
│   ├── kuberay-operator.yaml         # KubeRay values
│   ├── minio-distributed.yaml        # MinIO distributed values
│   ├── mlflow.yaml                   # MLflow values
│   ├── nats-jetstream.yaml           # NATS JetStream values
│   ├── neo4j-cluster.yaml            # Neo4j cluster values
│   ├── postgresql-ha.yaml            # PostgreSQL HA values
│   ├── qdrant-distributed.yaml       # Qdrant distributed values
│   ├── ray-cluster.yaml              # Ray cluster values
│   └── redis-cluster.yaml            # Redis cluster values
├── secrets/
│   └── infrastructure-secrets.yaml   # Secret templates
└── scripts/
    ├── backup.sh                     # Backup/restore script
    ├── check-services.sh             # HA health check
    └── deploy.sh                     # Deployment script
```

## Related Documentation

- [Staging Deployment](../staging/README.md)
- [Local Development](../local/README.md)
- [ArgoCD Applications](../../argocd/)
- [Consul-APISIX Sync](../../../docs/apisix_route_consul_sync.md)
- [Backup Procedures](./scripts/backup.sh)
