# ISA Cloud - Staging Kubernetes Deployment

Staging environment deployment for the ISA Cloud platform.

## Prerequisites

### Required Tools
- `kubectl` - Kubernetes CLI
- `helm` - Helm package manager (v3+)
- `argocd` - ArgoCD CLI (optional, for service deployment)

### Required Secrets

Before deploying, create the required secrets:

```bash
# Apply secrets template (edit with real values first!)
kubectl create namespace isa-cloud-staging
kubectl apply -f secrets/infrastructure-secrets.yaml
```

Required secrets:
- `postgresql-secret` - PostgreSQL credentials
- `redis-secret` - Redis password
- `neo4j-secret` - Neo4j credentials
- `minio-secret` - MinIO access keys

### Storage Classes

Ensure your cluster has a default storage class or configure specific classes in the values files.

## Deployment

### Quick Start

```bash
cd deployments/kubernetes/staging

# Interactive deployment
./scripts/deploy.sh

# Or deploy specific components
./scripts/deploy.sh infrastructure  # Deploy all infrastructure
./scripts/deploy.sh services        # Sync ArgoCD applications
./scripts/deploy.sh etcd            # Deploy etcd only
./scripts/deploy.sh status          # Check status
```

### Deployment Order

The deploy script follows this order:

1. Create namespace
2. Verify secrets
3. Setup Helm repositories
4. Deploy etcd (APISIX dependency)
5. Deploy databases (PostgreSQL, Redis, Neo4j)
6. Deploy object storage (MinIO)
7. Deploy messaging (NATS, EMQX)
8. Deploy vector database (Qdrant)
9. Deploy service discovery (Consul)
10. Deploy API gateway (APISIX)
11. Apply Consul-APISIX sync CronJob
12. Sync ArgoCD applications (services)

## Architecture

| Service | Type | Replicas | Purpose |
|---------|------|----------|---------|
| etcd | StatefulSet | 1 | APISIX configuration backend |
| PostgreSQL | Helm | 1 | Relational database |
| Redis | Helm | 1 master | Cache & session store |
| Neo4j | Helm | 1 | Graph database |
| MinIO | Helm | 1 | Object storage |
| NATS | Helm | 1 | Event messaging |
| EMQX | Helm | 1 | MQTT broker |
| Qdrant | Helm | 1 | Vector database |
| Consul | Helm | 1 | Service discovery |
| APISIX | Helm | 1 | API Gateway |

## Health Monitoring

```bash
# Run health check
./scripts/check-services.sh

# Manual checks
kubectl get pods -n isa-cloud-staging
kubectl get svc -n isa-cloud-staging
helm list -n isa-cloud-staging
```

## Port Forwarding

Access services locally:

```bash
# APISIX Gateway
kubectl port-forward -n isa-cloud-staging svc/apisix-gateway 8080:80

# APISIX Dashboard
kubectl port-forward -n isa-cloud-staging svc/apisix-dashboard 9000:80

# Consul UI
kubectl port-forward -n isa-cloud-staging svc/consul-server 8500:8500

# PostgreSQL
kubectl port-forward -n isa-cloud-staging svc/postgresql 5432:5432

# Redis
kubectl port-forward -n isa-cloud-staging svc/redis-master 6379:6379

# MinIO Console
kubectl port-forward -n isa-cloud-staging svc/minio-console 9001:9001

# Neo4j Browser
kubectl port-forward -n isa-cloud-staging svc/neo4j 7474:7474 7687:7687

# Qdrant Dashboard
kubectl port-forward -n isa-cloud-staging svc/qdrant 6333:6333
```

## Troubleshooting

### Pods Not Starting

```bash
# Check pod events
kubectl describe pod <pod-name> -n isa-cloud-staging

# Check logs
kubectl logs <pod-name> -n isa-cloud-staging

# Check PVC status
kubectl get pvc -n isa-cloud-staging
```

### etcd Issues

```bash
# Check etcd health
kubectl exec -n isa-cloud-staging etcd-0 -- etcdctl endpoint health

# Check etcd logs
kubectl logs -n isa-cloud-staging etcd-0
```

### APISIX Issues

```bash
# Check APISIX routes
kubectl exec -n isa-cloud-staging <apisix-pod> -- \
  curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1"

# Check APISIX logs
kubectl logs -n isa-cloud-staging -l app.kubernetes.io/name=apisix
```

### Consul Issues

```bash
# Check Consul members
kubectl exec -n isa-cloud-staging consul-server-0 -- consul members

# Check registered services
kubectl exec -n isa-cloud-staging consul-server-0 -- \
  curl -s http://localhost:8500/v1/catalog/services
```

## Helm Releases

View and manage Helm releases:

```bash
# List releases
helm list -n isa-cloud-staging

# Get release status
helm status <release-name> -n isa-cloud-staging

# View release values
helm get values <release-name> -n isa-cloud-staging

# Rollback release
helm rollback <release-name> -n isa-cloud-staging
```

## Configuration Files

```
staging/
├── manifests/
│   ├── etcd.yaml                 # etcd StatefulSet
│   └── consul-apisix-sync.yaml   # Route sync CronJob
├── values/
│   ├── apisix.yaml               # APISIX Helm values
│   ├── consul.yaml               # Consul Helm values
│   ├── emqx.yaml                 # EMQX Helm values
│   ├── etcd.yaml                 # etcd Helm values (alternative)
│   ├── minio.yaml                # MinIO Helm values
│   ├── nats.yaml                 # NATS Helm values
│   ├── neo4j.yaml                # Neo4j Helm values
│   ├── postgresql.yaml           # PostgreSQL Helm values
│   ├── qdrant.yaml               # Qdrant Helm values
│   └── redis.yaml                # Redis Helm values
├── secrets/
│   └── infrastructure-secrets.yaml   # Secret templates
└── scripts/
    ├── deploy.sh                 # Deployment script
    └── check-services.sh         # Health check script
```

## Differences from Production

| Aspect | Staging | Production |
|--------|---------|------------|
| Replicas | Single instances | HA clusters (3+ replicas) |
| Resources | Lower limits | Higher limits |
| Storage | Standard class | Fast SSD class |
| PDB | None | Configured |
| Auto-scaling | Disabled | HPA enabled |
| Backups | Manual | Automated |

## Related Documentation

- [Production Deployment](../production/README.md)
- [Local Development](../local/README.md)
- [ArgoCD Applications](../../argocd/)
- [Consul-APISIX Sync](../../../docs/apisix_route_consul_sync.md)
