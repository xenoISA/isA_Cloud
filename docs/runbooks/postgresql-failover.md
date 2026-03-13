# Runbook: PostgreSQL Failover & Recovery

## Symptoms

- Application errors: `connection refused` or `connection timed out` to PostgreSQL
- Logs show `asyncpg.PostgresError` or `psycopg2.OperationalError`
- Health checks return `{"healthy": false}` for PostgreSQL-dependent services
- Queries hanging or timing out

## Quick Health Check

```bash
# Check PostgreSQL pod status
kubectl get pods -n isa-cloud-local -l app.kubernetes.io/name=postgresql

# Check if PostgreSQL is accepting connections
kubectl exec -n isa-cloud-local deploy/postgresql -- \
  pg_isready -U postgres

# Check replication status (if replica exists)
kubectl exec -n isa-cloud-local deploy/postgresql -- \
  psql -U postgres -c "SELECT * FROM pg_stat_replication;"

# Check active connections
kubectl exec -n isa-cloud-local deploy/postgresql -- \
  psql -U postgres -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# Check database sizes
kubectl exec -n isa-cloud-local deploy/postgresql -- \
  psql -U postgres -c "SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database WHERE datistemplate = false;"
```

## Common Failure Modes

### 1. Pod crash / OOMKilled

**Symptoms**: Pod in `CrashLoopBackOff` or `OOMKilled` status.

**Diagnosis**:
```bash
# Check pod events
kubectl describe pod -n isa-cloud-local -l app.kubernetes.io/name=postgresql | grep -A 5 "Events:"

# Check resource usage
kubectl top pod -n isa-cloud-local -l app.kubernetes.io/name=postgresql

# Check logs
kubectl logs -n isa-cloud-local deploy/postgresql --tail=50
```

**Resolution**:
1. If OOMKilled, increase memory limits in Helm values:
   ```bash
   helm upgrade postgresql bitnami/postgresql -n isa-cloud-local \
     --set resources.limits.memory=2Gi \
     --set resources.requests.memory=1Gi
   ```
2. If crash loop, check logs for WAL corruption or disk full
3. If disk full, expand PVC or clean up WAL files (see section below)

### 2. Disk full / WAL accumulation

**Symptoms**: Write failures, `PANIC: could not write to file`, `No space left on device`.

**Diagnosis**:
```bash
# Check PVC usage
kubectl exec -n isa-cloud-local deploy/postgresql -- df -h /bitnami/postgresql

# Check WAL size
kubectl exec -n isa-cloud-local deploy/postgresql -- \
  psql -U postgres -c "SELECT pg_size_pretty(sum(size)) FROM pg_ls_waldir();"
```

**Resolution**:
1. Force a checkpoint to flush WAL:
   ```bash
   kubectl exec -n isa-cloud-local deploy/postgresql -- \
     psql -U postgres -c "CHECKPOINT;"
   ```
2. If replication slot is blocking WAL cleanup:
   ```bash
   kubectl exec -n isa-cloud-local deploy/postgresql -- \
     psql -U postgres -c "SELECT slot_name, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) FROM pg_replication_slots;"
   ```
3. Drop inactive replication slots if safe:
   ```bash
   kubectl exec -n isa-cloud-local deploy/postgresql -- \
     psql -U postgres -c "SELECT pg_drop_replication_slot('slot_name');"
   ```

### 3. Connection exhaustion

**Symptoms**: `too many connections for role "postgres"`, new connections refused.

**Diagnosis**:
```bash
kubectl exec -n isa-cloud-local deploy/postgresql -- \
  psql -U postgres -c "
    SELECT count(*) as total, max_conn
    FROM pg_stat_activity, (SELECT setting::int AS max_conn FROM pg_settings WHERE name='max_connections') mc
    GROUP BY max_conn;
  "
```

**Resolution**:
1. Terminate idle connections:
   ```bash
   kubectl exec -n isa-cloud-local deploy/postgresql -- \
     psql -U postgres -c "
       SELECT pg_terminate_backend(pid)
       FROM pg_stat_activity
       WHERE state = 'idle' AND query_start < now() - interval '10 minutes';
     "
   ```
2. If persistent, increase `max_connections` or fix connection pool leaks in application code

### 4. Corrupted data / table

**Symptoms**: `ERROR: could not read block`, `invalid page in block`.

**Diagnosis**:
```bash
kubectl exec -n isa-cloud-local deploy/postgresql -- \
  psql -U postgres -d isa_db -c "SELECT relname FROM pg_class WHERE relkind='r';" | \
  while read table; do
    echo "Checking $table..."
    kubectl exec -n isa-cloud-local deploy/postgresql -- \
      psql -U postgres -d isa_db -c "SELECT count(*) FROM \"$table\";" 2>&1 | grep -i error
  done
```

**Resolution**:
1. Try `REINDEX`:
   ```bash
   kubectl exec -n isa-cloud-local deploy/postgresql -- \
     psql -U postgres -d isa_db -c "REINDEX DATABASE isa_db;"
   ```
2. If corruption is severe, restore from backup:
   ```bash
   # Restore all services (PostgreSQL included) from backup
   ./scripts/restore-cluster-data.sh /path/to/backup
   ```

## Backup & Restore

```bash
# Create backup
./scripts/backup-cluster-data.sh

# Restore PostgreSQL only
./scripts/restore-cluster-data.sh --service postgresql --backup-dir ./backups/latest

# Manual pg_dump
kubectl exec -n isa-cloud-local deploy/postgresql -- \
  pg_dump -U postgres isa_db > isa_db_backup.sql

# Manual restore
cat isa_db_backup.sql | kubectl exec -i -n isa-cloud-local deploy/postgresql -- \
  psql -U postgres isa_db
```

## Preventive Monitoring

### Alerts to set up
- `pg_stat_activity` connection count > 80% of `max_connections`
- PVC usage > 80%
- WAL size > 1GB
- Replication lag > 30 seconds (if replicas configured)

### Periodic checks
- Weekly: review slow query log (`pg_stat_statements`)
- After deployments: verify migrations ran successfully
- Monthly: check table bloat and run `VACUUM ANALYZE`
