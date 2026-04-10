# ISA Cloud — Rollback Procedures

> Recovery procedures for failed deployments, ordered by component.
> Always rollback in **reverse deployment order** (gateway → messaging → databases → secrets).

## Decision Tree: Rollback vs Fix Forward

```
Deployment failed
  │
  ├─ Pod CrashLoopBackOff (config error)?
  │   └─ Fix forward: edit values, helm upgrade again
  │
  ├─ PVC stuck Pending (storage issue)?
  │   └─ Fix forward: create StorageClass, PVC will auto-bind
  │
  ├─ Data corruption / wrong version?
  │   └─ Rollback: helm rollback + restore from backup
  │
  ├─ Partial deployment (some components up, some failed)?
  │   └─ Rollback failed components only, leave working ones
  │
  └─ Full deployment broken?
      └─ Rollback all in reverse order (see below)
```

## Rollback Order (Reverse of Deployment)

When rolling back the full stack, follow this order:

1. APISIX + Consul-APISIX sync
2. Consul
3. EMQX
4. Qdrant
5. NATS JetStream
6. MinIO
7. Neo4j
8. Redis Cluster
9. PostgreSQL HA
10. etcd
11. External Secrets Operator
12. Vault

## Per-Component Rollback

### General Helm Rollback

For any Helm-managed component:

```bash
# View release history
helm history <release> -n isa-cloud-production

# Rollback to previous revision
helm rollback <release> -n isa-cloud-production

# Rollback to specific revision
helm rollback <release> <revision> -n isa-cloud-production
```

Or use the deploy.sh wrapper:

```bash
./deploy.sh rollback <release>
```

### APISIX

```bash
helm rollback apisix -n isa-cloud-production

# If routes are stale, re-sync from Consul:
kubectl delete job -n isa-cloud-production -l app=consul-apisix-sync
kubectl create job --from=cronjob/consul-apisix-sync manual-sync -n isa-cloud-production
```

### Consul

```bash
helm rollback consul -n isa-cloud-production

# If Consul data is corrupted, restore from snapshot:
./scripts/backup/restore.sh /path/to/backup --component consul
```

### EMQX

```bash
helm rollback emqx -n isa-cloud-production
# EMQX cluster will auto-reform after restart
```

### Qdrant

```bash
helm rollback qdrant -n isa-cloud-production

# If data is corrupted, restore from snapshot:
# 1. Stop Qdrant: kubectl scale statefulset qdrant --replicas=0 -n isa-cloud-production
# 2. Restore snapshots to PVs
# 3. Restart: kubectl scale statefulset qdrant --replicas=3 -n isa-cloud-production
```

### NATS JetStream

```bash
helm rollback nats -n isa-cloud-production

# If streams are lost, recreate from backup:
# Stream configs are in backup/nats/stream-*.json
# nats stream add <name> --config <file>
```

### MinIO

```bash
helm rollback minio -n isa-cloud-production

# If data is lost, restore from backup:
# mc mirror /backup/minio/isa-data isa-prod/isa-data
```

### Neo4j

```bash
helm rollback neo4j -n isa-cloud-production

# If data is corrupted:
# 1. Stop Neo4j
# 2. Restore dump: neo4j-admin database load --from-path=/backup neo4j
# 3. Restart
```

### Redis Cluster

```bash
helm rollback redis -n isa-cloud-production

# After rollback, check cluster health:
kubectl exec -it redis-redis-cluster-0 -n isa-cloud-production -- redis-cli cluster info

# If slots are missing, fix:
kubectl exec -it redis-redis-cluster-0 -n isa-cloud-production -- redis-cli --cluster fix redis-redis-cluster-0:6379

# If data restore is needed:
./scripts/backup/restore.sh /path/to/backup --component redis
```

### PostgreSQL HA

```bash
helm rollback postgresql -n isa-cloud-production

# After rollback, verify replication:
kubectl exec -it postgresql-postgresql-ha-postgresql-0 -n isa-cloud-production -- \
    psql -U postgres -c "SELECT * FROM pg_stat_replication;"

# If data restore is needed:
./scripts/backup/restore.sh /path/to/backup --component postgres
```

**WARNING**: PostgreSQL rollback may cause data loss if the schema changed between versions. Always backup before upgrading.

### etcd

```bash
# etcd is deployed via raw manifests, not Helm. To rollback:

# 1. Stop the cluster
kubectl scale statefulset etcd --replicas=0 -n isa-cloud-production

# 2. Restore from snapshot (on each node)
kubectl exec -it etcd-0 -n isa-cloud-production -- \
    etcdctl snapshot restore /tmp/etcd-backup.snap --data-dir=/etcd-data

# 3. Restart
kubectl scale statefulset etcd --replicas=3 -n isa-cloud-production
```

### Vault

```bash
helm rollback vault -n isa-cloud-production

# After rollback, Vault may be sealed. Unseal:
kubectl exec -it vault-0 -n isa-cloud-production -- vault operator unseal <key>

# Check secret sync status:
kubectl get externalsecret -n isa-cloud-production
```

### External Secrets Operator

```bash
helm rollback external-secrets -n external-secrets
```

## Emergency: Full Stack Rollback

If the entire deployment needs to be rolled back:

```bash
# 1. Backup current state first
./scripts/backup/backup.sh

# 2. Rollback gateway layer
helm rollback apisix -n isa-cloud-production
helm rollback consul -n isa-cloud-production

# 3. Rollback messaging
helm rollback emqx -n isa-cloud-production
helm rollback nats -n isa-cloud-production

# 4. Rollback databases
helm rollback qdrant -n isa-cloud-production
helm rollback minio -n isa-cloud-production
helm rollback neo4j -n isa-cloud-production
helm rollback redis -n isa-cloud-production
helm rollback postgresql -n isa-cloud-production

# 5. Rollback etcd
kubectl apply -f manifests/etcd.yaml  # Re-apply previous version

# 6. Rollback secrets (only if needed)
helm rollback vault -n isa-cloud-production
helm rollback external-secrets -n external-secrets

# 7. Verify
./health-check.sh
```

## Post-Rollback Verification

After any rollback:

```bash
# 1. Run health check
./health-check.sh

# 2. Check for data consistency
./deploy.sh status

# 3. Verify ArgoCD apps are in sync
argocd app list | grep production
```
