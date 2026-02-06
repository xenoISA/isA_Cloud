# Operations

Scripts, monitoring, backup, and operational procedures.

## Overview

Operational tools include:

- **Backup/Restore** - Data protection
- **Port Forwarding** - Local access
- **Monitoring** - Grafana, Loki, Prometheus
- **Debugging** - Logs, traces, health checks

### Namespace Convention

Replace `isa-cloud-staging` in examples with your target environment:

| Environment | Namespace |
|-------------|-----------|
| Local | `isa-cloud-local` |
| Staging | `isa-cloud-staging` |
| Production | `isa-cloud-production` |

## Scripts

### Port Forwarding

```bash
# Forward all services
./scripts/port-forward.sh

# Infrastructure only
./scripts/port-forward-infra.sh
```

### Service Ports

| Service | Port |
|---------|------|
| APISIX Gateway | 9080 |
| APISIX Admin | 9180 |
| Consul | 8500 |
| PostgreSQL | 5432 |
| Redis | 6379 |
| Neo4j | 7474, 7687 |
| NATS | 4222 |
| MQTT | 1883 |
| MinIO | 9000, 9001 |
| Qdrant | 6333 |
| Grafana | 3000 |
| Loki | 3100 |

## Backup

### Cluster Backup

```bash
./scripts/backup-cluster-data.sh
```

Backs up:
- PostgreSQL databases
- Redis RDB snapshots
- MinIO buckets
- Neo4j databases
- Qdrant collections

### Backup Location

```
backups/
└── cluster-backup-YYYYMMDD-HHMMSS/
    ├── postgres/
    │   └── isa_db.sql.gz
    ├── redis/
    │   └── dump.rdb
    ├── minio/
    │   └── buckets.tar.gz
    ├── neo4j/
    │   └── neo4j.dump
    └── qdrant/
        └── collections.tar.gz
```

### Manual Backup

```bash
# PostgreSQL
kubectl exec -it postgres-0 -n isa-cloud-staging -- \
  pg_dump -U postgres isa_db | gzip > backup.sql.gz

# Redis
kubectl exec -it redis-master-0 -n isa-cloud-staging -- \
  redis-cli BGSAVE

# MinIO
mc mirror minio/bucket ./backup/bucket
```

## Restore

### Cluster Restore

```bash
./scripts/restore-cluster-data.sh backups/cluster-backup-20260114-120000
```

### Manual Restore

```bash
# PostgreSQL
gunzip -c backup.sql.gz | kubectl exec -i postgres-0 -n isa-cloud-staging -- \
  psql -U postgres isa_db

# Redis
kubectl cp dump.rdb redis-master-0:/data/dump.rdb -n isa-cloud-staging
kubectl exec -it redis-master-0 -n isa-cloud-staging -- redis-cli DEBUG RELOAD

# MinIO
mc mirror ./backup/bucket minio/bucket
```

## Monitoring

### Grafana Dashboards

Access at `http://localhost:3000`:

| Dashboard | Purpose |
|-----------|---------|
| **Infrastructure** | CPU, memory, disk usage |
| **Services** | Request rate, latency, errors |
| **Database** | Query performance, connections |
| **APISIX** | Gateway metrics, routes |

### Key Metrics

```promql
# Request rate
sum(rate(apisix_http_status[5m])) by (service)

# Error rate
sum(rate(apisix_http_status{code=~"5.."}[5m])) / sum(rate(apisix_http_status[5m]))

# Latency P99
histogram_quantile(0.99, sum(rate(apisix_http_latency_bucket[5m])) by (le, service))

# Memory usage
container_memory_usage_bytes{namespace="isa-cloud-staging"}
```

### Loki Log Queries

```logql
# Service errors
{namespace="isa-cloud-staging", app="auth-service"} |= "error"

# gRPC requests
{namespace="isa-cloud-staging"} | json | method=~".*"

# Slow requests
{namespace="isa-cloud-staging"} | json | duration > 1s
```

## Health Checks

### Service Health

```bash
# Check all pods
kubectl get pods -n isa-cloud-staging

# Check specific service
kubectl describe pod auth-service-xxx -n isa-cloud-staging

# View logs
kubectl logs -f auth-service-xxx -n isa-cloud-staging
```

### Consul Health

```bash
# All services
curl http://localhost:8500/v1/catalog/services | jq

# Service health
curl http://localhost:8500/v1/health/service/auth_service | jq

# Critical services
curl http://localhost:8500/v1/health/state/critical | jq
```

### gRPC Health

```bash
# Check gRPC service
grpcurl -plaintext localhost:50061 grpc.health.v1.Health/Check
```

## Debugging

### View Logs

```bash
# Pod logs
kubectl logs -f <pod-name> -n isa-cloud-staging

# Previous container logs
kubectl logs -f <pod-name> -n isa-cloud-staging --previous

# All containers in pod
kubectl logs -f <pod-name> -n isa-cloud-staging --all-containers

# Stream from Loki
logcli query '{namespace="isa-cloud-staging"}'
```

### Exec into Pod

```bash
kubectl exec -it <pod-name> -n isa-cloud-staging -- /bin/sh
```

### Port Forward to Pod

```bash
kubectl port-forward <pod-name> 8080:8080 -n isa-cloud-staging
```

### Debug Network

```bash
# DNS resolution
kubectl run debug --rm -it --image=busybox -- nslookup auth-service

# Connectivity test
kubectl run debug --rm -it --image=curlimages/curl -- curl http://auth-service:8201/health
```

## Scaling

### Manual Scaling

```bash
kubectl scale deployment auth-service --replicas=5 -n isa-cloud-staging
```

### HPA Status

```bash
kubectl get hpa -n isa-cloud-staging
kubectl describe hpa auth-service -n isa-cloud-staging
```

## Troubleshooting

### Pod Not Starting

```bash
# Check events
kubectl get events -n isa-cloud-staging --sort-by='.lastTimestamp'

# Describe pod
kubectl describe pod <pod-name> -n isa-cloud-staging

# Check resource limits
kubectl top pods -n isa-cloud-staging
```

### Service Not Reachable

```bash
# Check service exists
kubectl get svc -n isa-cloud-staging

# Check endpoints
kubectl get endpoints <service-name> -n isa-cloud-staging

# Test DNS
kubectl run debug --rm -it --image=busybox -- nslookup <service-name>
```

### Database Connection Issues

```bash
# Check PostgreSQL
kubectl exec -it postgres-0 -n isa-cloud-staging -- psql -U postgres -c "SELECT 1"

# Check Redis
kubectl exec -it redis-master-0 -n isa-cloud-staging -- redis-cli ping

# Check Neo4j
curl http://localhost:7474/db/neo4j/cluster/available
```

### APISIX Issues

```bash
# Check routes
curl http://localhost:9180/apisix/admin/routes -H "X-API-KEY: admin-key"

# Check upstreams
curl http://localhost:9180/apisix/admin/upstreams -H "X-API-KEY: admin-key"

# Check logs
kubectl logs -f -l app=apisix -n isa-cloud-staging
```

## Runbooks

### Service Restart

```bash
# Restart deployment
kubectl rollout restart deployment/<service-name> -n isa-cloud-staging

# Watch rollout
kubectl rollout status deployment/<service-name> -n isa-cloud-staging
```

### Clear Redis Cache

```bash
kubectl exec -it redis-master-0 -n isa-cloud-staging -- redis-cli FLUSHDB
```

### Rotate Secrets

```bash
# Generate new secret
openssl rand -base64 32

# Update Kubernetes secret
kubectl create secret generic database-secrets \
  --from-literal=password=<new-password> \
  -n isa-cloud-staging \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart dependent services
kubectl rollout restart deployment/auth-service -n isa-cloud-staging
```

## Alerting

### Common Alerts

| Alert | Condition | Action |
|-------|-----------|--------|
| ServiceDown | Pod not ready > 5m | Check pod logs, restart |
| HighErrorRate | Error rate > 5% | Check service logs |
| HighLatency | P99 > 1s | Check database, scale |
| DiskFull | Usage > 90% | Cleanup or expand |
| HighMemory | Usage > 85% | Scale or optimize |

## Next Steps

- [Deployment](./deployment) - ArgoCD setup
- [CI/CD](./cicd) - Automated pipelines
- [Testing](./testing) - Test strategies
