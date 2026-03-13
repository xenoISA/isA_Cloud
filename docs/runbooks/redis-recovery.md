# Runbook: Redis Recovery

## Symptoms

- Application errors: `ConnectionError`, `TimeoutError`, or `CLUSTERDOWN` from Redis
- Health checks return `{"healthy": false}` for Redis-dependent services
- Session/cache misses spiking
- Pub/sub messages not delivered

## Quick Health Check

```bash
# Check Redis pod status
kubectl get pods -n isa-cloud-local -l app.kubernetes.io/name=redis

# Ping Redis
kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli PING

# Check memory usage
kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli INFO memory | grep -E "used_memory_human|maxmemory_human|mem_fragmentation_ratio"

# Check connected clients
kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli INFO clients | grep connected_clients

# Check key count per database
kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli INFO keyspace
```

## Common Failure Modes

### 1. Pod crash / OOMKilled

**Symptoms**: Redis pod in `CrashLoopBackOff` or `OOMKilled`.

**Diagnosis**:
```bash
kubectl describe pod -n isa-cloud-local -l app.kubernetes.io/name=redis | grep -A 5 "Events:"
kubectl top pod -n isa-cloud-local -l app.kubernetes.io/name=redis
kubectl logs -n isa-cloud-local deploy/redis-master --tail=50
```

**Resolution**:
1. If OOMKilled, increase memory limits:
   ```bash
   helm upgrade redis bitnami/redis -n isa-cloud-local \
     --set master.resources.limits.memory=1Gi \
     --set master.persistence.size=8Gi
   ```
2. Check if `maxmemory` is set correctly:
   ```bash
   kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli CONFIG GET maxmemory
   ```
3. Set eviction policy if not configured:
   ```bash
   kubectl exec -n isa-cloud-local deploy/redis-master -- \
     redis-cli CONFIG SET maxmemory-policy allkeys-lru
   ```

### 2. Memory full / eviction pressure

**Symptoms**: `OOM command not allowed when used memory > 'maxmemory'`, unexpected cache misses.

**Diagnosis**:
```bash
# Check memory stats
kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli INFO memory

# Check eviction stats
kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli INFO stats | grep evicted_keys

# Find large keys
kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli --bigkeys
```

**Resolution**:
1. Flush non-critical caches:
   ```bash
   kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli KEYS "cache:*" | head -100 | \
     xargs -I {} kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli DEL {}
   ```
2. Increase `maxmemory` if under-provisioned
3. Review TTLs — ensure all cache keys have expiration set

### 3. Persistence failure (RDB/AOF)

**Symptoms**: `MISCONF Redis is configured to save RDB snapshots, but is currently unable to persist`.

**Diagnosis**:
```bash
kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli INFO persistence
kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli LASTSAVE
```

**Resolution**:
1. Check disk space on PVC:
   ```bash
   kubectl exec -n isa-cloud-local deploy/redis-master -- df -h /data
   ```
2. If disk full, expand PVC or disable RDB saves temporarily:
   ```bash
   kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli CONFIG SET stop-writes-on-bgsave-error no
   ```
3. Trigger manual save after fixing disk:
   ```bash
   kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli BGSAVE
   ```

### 4. Slow commands / blocking operations

**Symptoms**: High latency, `slowlog` entries, client timeouts.

**Diagnosis**:
```bash
# Check slow log
kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli SLOWLOG GET 10

# Check blocked clients
kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli INFO clients | grep blocked_clients

# Check latency
kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli --latency-history
```

**Resolution**:
1. Identify and fix `KEYS *` usage in application code (use `SCAN` instead)
2. Break up large sets/lists causing O(N) operations
3. If `KEYS` is needed for debugging, use `SCAN` with a cursor

## Backup & Restore

```bash
# Create backup (uses backup-cluster-data.sh)
./scripts/backup-cluster-data.sh

# Restore all services (Redis included) from backup
./scripts/restore-cluster-data.sh ./backups/cluster-backup-YYYYMMDD_HHMMSS

# Manual RDB backup
kubectl exec -n isa-cloud-local deploy/redis-master -- redis-cli BGSAVE
kubectl cp isa-cloud-local/$(kubectl get pod -n isa-cloud-local -l app.kubernetes.io/name=redis,app.kubernetes.io/component=master -o jsonpath='{.items[0].metadata.name}'):/data/dump.rdb ./redis-backup.rdb

# Manual restore
kubectl cp ./redis-backup.rdb isa-cloud-local/$(kubectl get pod -n isa-cloud-local -l app.kubernetes.io/name=redis,app.kubernetes.io/component=master -o jsonpath='{.items[0].metadata.name}'):/data/dump.rdb
kubectl rollout restart deploy/redis-master -n isa-cloud-local
```

## Preventive Monitoring

### Alerts to set up
- `used_memory` > 80% of `maxmemory`
- `evicted_keys` increasing > 100/minute
- `connected_clients` > 80% of `maxclients`
- `rdb_last_bgsave_status` != `ok`

### Periodic checks
- Weekly: review `SLOWLOG` for patterns
- After deployments: verify pub/sub consumers reconnect
- Monthly: run `--bigkeys` to find oversized keys
