---
name: data-backup
description: Backup and restore all data stores (PostgreSQL, Redis, Neo4j, MinIO, Qdrant, Consul, NATS, APISIX). Complete scripts in scripts/ folder.
---

# Data Backup Operations

Complete backup and restore operations for ALL data stores in isA_Cloud.

## Quick Start

```bash
# Full backup of all services
./scripts/backup-all.sh

# Full restore from backup
./scripts/restore-all.sh /path/to/backup
```

## Supported Data Stores

1. **PostgreSQL** - Relational database (accounts, organizations, etc.)
2. **Redis** - Cache and session store
3. **Neo4j** - Graph database (relationships)
4. **MinIO** - Object storage (files, media)
5. **Qdrant** - Vector database (embeddings)
6. **Consul** - Service registry and KV store
7. **NATS** - Message streaming (JetStream)
8. **APISIX** - API Gateway (routes, upstreams, consumers)

## Operation Patterns

### Pattern 1: Individual Service Backup

```bash
# Backup PostgreSQL only
kubectl exec -n isa-cloud-staging deploy/postgres -- \
  pg_dumpall -U postgres | gzip > postgres-backup-$(date +%Y%m%d).sql.gz

# Backup Redis only
kubectl exec -n isa-cloud-staging deploy/redis -- \
  redis-cli SAVE

kubectl cp isa-cloud-staging/redis-0:/data/dump.rdb \
  ./redis-backup-$(date +%Y%m%d).rdb
```

### Pattern 2: Testing Backup Procedures

Before running full cluster backup, test individual services:

```bash
# Test PostgreSQL backup
kubectl exec -n isa-cloud-staging deploy/postgres -- \
  pg_dumpall -U postgres > /tmp/test-backup.sql

# Verify backup file
kubectl exec -n isa-cloud-staging deploy/postgres -- \
  ls -lh /tmp/test-backup.sql
```

### Pattern 3: Selective Restore

Restore specific databases without affecting others:

```bash
# Restore only PostgreSQL
kubectl cp postgres-backup.sql isa-cloud-staging/postgres-0:/tmp/
kubectl exec -n isa-cloud-staging deploy/postgres -- \
  psql -U postgres < /tmp/postgres-backup.sql
```

## PostgreSQL Backup/Restore

### Backup PostgreSQL

**Full backup (all databases):**
```bash
kubectl exec -n isa-cloud-staging deploy/postgres -- \
  pg_dumpall -U postgres | gzip > postgres-full-$(date +%Y%m%d).sql.gz
```

**Single database backup:**
```bash
kubectl exec -n isa-cloud-staging deploy/postgres -- \
  pg_dump -U postgres -d accounts | gzip > accounts-db-$(date +%Y%m%d).sql.gz
```

**Specific table backup:**
```bash
kubectl exec -n isa-cloud-staging deploy/postgres -- \
  pg_dump -U postgres -d accounts -t users | gzip > users-table-$(date +%Y%m%d).sql.gz
```

### Restore PostgreSQL

**Full restore:**
```bash
# Copy backup to pod
kubectl cp postgres-full-20260204.sql.gz isa-cloud-staging/postgres-0:/tmp/

# Restore
kubectl exec -n isa-cloud-staging deploy/postgres -- bash -c \
  "gunzip -c /tmp/postgres-full-20260204.sql.gz | psql -U postgres"
```

**Single database restore:**
```bash
kubectl cp accounts-db-20260204.sql.gz isa-cloud-staging/postgres-0:/tmp/

kubectl exec -n isa-cloud-staging deploy/postgres -- bash -c \
  "gunzip -c /tmp/accounts-db-20260204.sql.gz | psql -U postgres -d accounts"
```

### Verify PostgreSQL

```bash
# List databases
kubectl exec -n isa-cloud-staging deploy/postgres -- \
  psql -U postgres -c "\l"

# Check table counts
kubectl exec -n isa-cloud-staging deploy/postgres -- \
  psql -U postgres -d accounts -c "SELECT count(*) FROM users;"
```

## Redis Backup/Restore

### Backup Redis

**Trigger save:**
```bash
kubectl exec -n isa-cloud-staging deploy/redis -- redis-cli SAVE
```

**Copy RDB file:**
```bash
kubectl cp isa-cloud-staging/redis-0:/data/dump.rdb \
  ./redis-backup-$(date +%Y%m%d).rdb
```

**Backup with keys list:**
```bash
# Export all keys
kubectl exec -n isa-cloud-staging deploy/redis -- redis-cli KEYS '*' > redis-keys.txt

# Export sample keys and values (for verification)
kubectl exec -n isa-cloud-staging deploy/redis -- redis-cli --scan | \
  head -100 | xargs -I {} kubectl exec -n isa-cloud-staging deploy/redis -- redis-cli GET {}
```

### Restore Redis

**Copy RDB file to pod:**
```bash
kubectl cp redis-backup-20260204.rdb isa-cloud-staging/redis-0:/data/dump.rdb
```

**Restart Redis to load backup:**
```bash
kubectl rollout restart deployment/redis -n isa-cloud-staging
kubectl wait --for=condition=ready pod -l app=redis -n isa-cloud-staging
```

### Verify Redis

```bash
# Check number of keys
kubectl exec -n isa-cloud-staging deploy/redis -- redis-cli DBSIZE

# Check memory usage
kubectl exec -n isa-cloud-staging deploy/redis -- redis-cli INFO memory

# Sample some keys
kubectl exec -n isa-cloud-staging deploy/redis -- redis-cli --scan | head -10
```

## Neo4j Backup/Restore

### Backup Neo4j

**Export cypher dump:**
```bash
kubectl exec -n isa-cloud-staging deploy/neo4j -- \
  cypher-shell -u neo4j -p password \
  "CALL apoc.export.cypher.all('/tmp/neo4j-backup.cypher', {})"

kubectl cp isa-cloud-staging/neo4j-0:/tmp/neo4j-backup.cypher \
  ./neo4j-backup-$(date +%Y%m%d).cypher
```

**Database dump (if available):**
```bash
kubectl exec -n isa-cloud-staging deploy/neo4j -- \
  neo4j-admin dump --database=neo4j --to=/tmp/neo4j-backup.dump

kubectl cp isa-cloud-staging/neo4j-0:/tmp/neo4j-backup.dump \
  ./neo4j-backup-$(date +%Y%m%d).dump
```

### Restore Neo4j

**Load from cypher:**
```bash
kubectl cp neo4j-backup-20260204.cypher isa-cloud-staging/neo4j-0:/tmp/

kubectl exec -n isa-cloud-staging deploy/neo4j -- \
  cypher-shell -u neo4j -p password < /tmp/neo4j-backup-20260204.cypher
```

**Load from dump:**
```bash
kubectl cp neo4j-backup-20260204.dump isa-cloud-staging/neo4j-0:/tmp/

kubectl exec -n isa-cloud-staging deploy/neo4j -- \
  neo4j-admin load --database=neo4j --from=/tmp/neo4j-backup-20260204.dump --force
```

### Verify Neo4j

```bash
# Count nodes
kubectl exec -n isa-cloud-staging deploy/neo4j -- \
  cypher-shell -u neo4j -p password "MATCH (n) RETURN count(n)"

# Count relationships
kubectl exec -n isa-cloud-staging deploy/neo4j -- \
  cypher-shell -u neo4j -p password "MATCH ()-[r]->() RETURN count(r)"

# List node labels
kubectl exec -n isa-cloud-staging deploy/neo4j -- \
  cypher-shell -u neo4j -p password "CALL db.labels()"
```

## MinIO Backup/Restore

### Backup MinIO

**List buckets:**
```bash
kubectl exec -n isa-cloud-staging deploy/minio -- mc ls local/
```

**Mirror bucket to local:**
```bash
# Create backup directory
mkdir -p minio-backup-$(date +%Y%m%d)

# For each bucket, mirror to local
kubectl exec -n isa-cloud-staging deploy/minio -- \
  mc mirror --preserve local/my-bucket /tmp/my-bucket

kubectl cp isa-cloud-staging/minio-0:/tmp/my-bucket \
  ./minio-backup-$(date +%Y%m%d)/my-bucket
```

**Export bucket policy:**
```bash
kubectl exec -n isa-cloud-staging deploy/minio -- \
  mc policy get-json local/my-bucket > bucket-policy.json
```

### Restore MinIO

**Create bucket if not exists:**
```bash
kubectl exec -n isa-cloud-staging deploy/minio -- \
  mc mb local/my-bucket --ignore-existing
```

**Copy data to pod:**
```bash
kubectl cp minio-backup-20260204/my-bucket isa-cloud-staging/minio-0:/tmp/
```

**Mirror from pod to bucket:**
```bash
kubectl exec -n isa-cloud-staging deploy/minio -- \
  mc mirror --preserve /tmp/my-bucket local/my-bucket
```

**Restore bucket policy:**
```bash
kubectl exec -n isa-cloud-staging deploy/minio -- \
  mc policy set-json bucket-policy.json local/my-bucket
```

### Verify MinIO

```bash
# List objects
kubectl exec -n isa-cloud-staging deploy/minio -- \
  mc ls --recursive local/my-bucket

# Get bucket size
kubectl exec -n isa-cloud-staging deploy/minio -- \
  mc du local/my-bucket

# Check bucket policy
kubectl exec -n isa-cloud-staging deploy/minio -- \
  mc policy get local/my-bucket
```

## Qdrant Backup/Restore

### Backup Qdrant

**Create snapshot via API:**
```bash
kubectl exec -n isa-cloud-staging deploy/qdrant -- \
  curl -X POST http://localhost:6333/snapshots
```

**List snapshots:**
```bash
kubectl exec -n isa-cloud-staging deploy/qdrant -- \
  curl http://localhost:6333/snapshots
```

**Download snapshot:**
```bash
# Get snapshot name from list
SNAPSHOT_NAME="snapshot-2026-02-04.snapshot"

kubectl cp isa-cloud-staging/qdrant-0:/qdrant/snapshots/$SNAPSHOT_NAME \
  ./qdrant-backup-$(date +%Y%m%d).snapshot
```

### Restore Qdrant

**Upload snapshot:**
```bash
kubectl cp qdrant-backup-20260204.snapshot \
  isa-cloud-staging/qdrant-0:/qdrant/snapshots/
```

**Restore via API:**
```bash
kubectl exec -n isa-cloud-staging deploy/qdrant -- \
  curl -X PUT "http://localhost:6333/collections/my_collection/snapshots/restore" \
  -H "Content-Type: application/json" \
  -d '{"snapshot":"qdrant-backup-20260204.snapshot"}'
```

### Verify Qdrant

```bash
# List collections
kubectl exec -n isa-cloud-staging deploy/qdrant -- \
  curl http://localhost:6333/collections

# Get collection info
kubectl exec -n isa-cloud-staging deploy/qdrant -- \
  curl http://localhost:6333/collections/my_collection

# Count vectors
kubectl exec -n isa-cloud-staging deploy/qdrant -- \
  curl http://localhost:6333/collections/my_collection | jq '.result.vectors_count'
```

## Consul Backup/Restore

### Backup Consul

**Snapshot entire cluster:**
```bash
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul snapshot save /tmp/consul-backup.snap

kubectl cp isa-cloud-staging/consul-0:/tmp/consul-backup.snap \
  ./consul-backup-$(date +%Y%m%d).snap
```

**Export KV store:**
```bash
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul kv export > consul-kv-$(date +%Y%m%d).json
```

### Restore Consul

**Restore from snapshot:**
```bash
kubectl cp consul-backup-20260204.snap isa-cloud-staging/consul-0:/tmp/

kubectl exec -n isa-cloud-staging consul-0 -- \
  consul snapshot restore /tmp/consul-backup-20260204.snap
```

**Import KV store:**
```bash
kubectl cp consul-kv-20260204.json isa-cloud-staging/consul-0:/tmp/

kubectl exec -n isa-cloud-staging consul-0 -- bash -c \
  "consul kv import @/tmp/consul-kv-20260204.json"
```

### Verify Consul

```bash
# List registered services
kubectl exec -n isa-cloud-staging consul-0 -- consul catalog services

# Check KV entries
kubectl exec -n isa-cloud-staging consul-0 -- consul kv get -recurse

# Verify cluster health
kubectl exec -n isa-cloud-staging consul-0 -- consul members
```

## Automation Scripts

### Quick Backup All Script

Create a script to backup all services quickly:

```bash
#!/bin/bash
# quick-backup.sh

BACKUP_DIR="backups/quick-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# PostgreSQL
kubectl exec -n isa-cloud-staging deploy/postgres -- \
  pg_dumpall -U postgres | gzip > "$BACKUP_DIR/postgres.sql.gz"

# Redis
kubectl exec -n isa-cloud-staging deploy/redis -- redis-cli SAVE
kubectl cp isa-cloud-staging/redis-0:/data/dump.rdb "$BACKUP_DIR/redis.rdb"

# Consul
kubectl exec -n isa-cloud-staging consul-0 -- \
  consul snapshot save /tmp/consul.snap
kubectl cp isa-cloud-staging/consul-0:/tmp/consul.snap "$BACKUP_DIR/consul.snap"

# MinIO (list only, manual backup needed)
kubectl exec -n isa-cloud-staging deploy/minio -- mc ls local/ > "$BACKUP_DIR/minio-buckets.txt"

# Qdrant (trigger snapshot)
kubectl exec -n isa-cloud-staging deploy/qdrant -- \
  curl -X POST http://localhost:6333/snapshots

echo "Backup completed: $BACKUP_DIR"
ls -lh "$BACKUP_DIR"
```

### Verify All Script

```bash
#!/bin/bash
# verify-data.sh

echo "=== PostgreSQL ==="
kubectl exec -n isa-cloud-staging deploy/postgres -- \
  psql -U postgres -c "SELECT count(*) FROM accounts;"

echo "=== Redis ==="
kubectl exec -n isa-cloud-staging deploy/redis -- redis-cli DBSIZE

echo "=== Neo4j ==="
kubectl exec -n isa-cloud-staging deploy/neo4j -- \
  cypher-shell -u neo4j -p password "MATCH (n) RETURN count(n)"

echo "=== MinIO ==="
kubectl exec -n isa-cloud-staging deploy/minio -- mc ls local/

echo "=== Qdrant ==="
kubectl exec -n isa-cloud-staging deploy/qdrant -- \
  curl -s http://localhost:6333/collections | jq

echo "=== Consul ==="
kubectl exec -n isa-cloud-staging consul-0 -- consul catalog services
```

## Best Practices

### Regular Testing

1. **Test backup procedures weekly**
2. **Verify restore on non-production cluster monthly**
3. **Document backup sizes and times**
4. **Automate verification checks**

### Backup Schedule Recommendations

```
Daily:
  - PostgreSQL incremental
  - Redis RDB
  - Consul snapshot

Weekly:
  - PostgreSQL full dump
  - Neo4j full export
  - MinIO bucket snapshots
  - Qdrant snapshots

Monthly:
  - Full cluster backup
  - Test full restore procedure
  - Backup retention review
```

### Monitoring Backup Health

```bash
# Check backup ages
find backups/ -type f -mtime +7 -ls

# Check backup sizes
du -sh backups/*

# Verify backup integrity
for backup in backups/*/postgres.sql.gz; do
    echo "Testing: $backup"
    gunzip -t "$backup" && echo "✓ OK" || echo "✗ CORRUPT"
done
```

## Troubleshooting

### PostgreSQL Issues

**Problem**: pg_dump fails with "permission denied"
```bash
# Solution: Check permissions
kubectl exec -n isa-cloud-staging deploy/postgres -- \
  psql -U postgres -c "SELECT * FROM pg_roles WHERE rolname='postgres';"
```

**Problem**: Restore fails with "database already exists"
```bash
# Solution: Drop and recreate
kubectl exec -n isa-cloud-staging deploy/postgres -- \
  psql -U postgres -c "DROP DATABASE accounts;"
# Then restore
```

### Redis Issues

**Problem**: dump.rdb file not found
```bash
# Solution: Check Redis data directory
kubectl exec -n isa-cloud-staging deploy/redis -- ls -la /data/
```

### MinIO Issues

**Problem**: mc command not found
```bash
# Solution: Use different MinIO client or install mc
kubectl exec -n isa-cloud-staging deploy/minio -- which mc
# Or use API directly
kubectl exec -n isa-cloud-staging deploy/minio -- \
  curl http://localhost:9000/minio/health/live
```

## NATS JetStream Backup/Restore

### Backup NATS

**Using NATS CLI:**
```bash
# List streams
nats stream ls

# Export stream config
nats stream info STREAM_NAME -j > stream-config.json

# Backup all stream configs
for stream in $(nats stream ls 2>/dev/null | grep -v "^Streams:"); do
    nats stream info "$stream" -j > "nats-backup/${stream}.json"
done
```

**Backup JetStream data directory:**
```bash
kubectl exec -n isa-cloud-staging deploy/nats -- \
  tar czf /tmp/jetstream.tar.gz /data/jetstream

kubectl cp isa-cloud-staging/nats-0:/tmp/jetstream.tar.gz \
  ./nats-backup-$(date +%Y%m%d).tar.gz
```

### Restore NATS

**Restore stream configs:**
```bash
nats stream add STREAM_NAME --config stream-config.json
```

**Restore from data backup:**
```bash
kubectl cp nats-backup.tar.gz isa-cloud-staging/nats-0:/tmp/
kubectl exec -n isa-cloud-staging deploy/nats -- \
  tar xzf /tmp/nats-backup.tar.gz -C /
kubectl rollout restart statefulset/nats -n isa-cloud-staging
```

### Verify NATS

```bash
# List streams
nats stream ls

# Check stream info
nats stream info STREAM_NAME

# Check consumers
nats consumer ls STREAM_NAME
```

## APISIX Backup/Restore

### Backup APISIX

**Export via Admin API:**
```bash
ADMIN_KEY="edd1c9f034335f136f87ad84b625c8f1"

# Export routes
curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: $ADMIN_KEY" | jq . > apisix-routes.json

# Export upstreams
curl -s http://localhost:9180/apisix/admin/upstreams \
  -H "X-API-KEY: $ADMIN_KEY" | jq . > apisix-upstreams.json

# Export services
curl -s http://localhost:9180/apisix/admin/services \
  -H "X-API-KEY: $ADMIN_KEY" | jq . > apisix-services.json

# Export consumers
curl -s http://localhost:9180/apisix/admin/consumers \
  -H "X-API-KEY: $ADMIN_KEY" | jq . > apisix-consumers.json

# Export global rules
curl -s http://localhost:9180/apisix/admin/global_rules \
  -H "X-API-KEY: $ADMIN_KEY" | jq . > apisix-global-rules.json
```

**Backup etcd directly:**
```bash
kubectl exec -n isa-cloud-staging deploy/apisix-etcd -- \
  etcdctl snapshot save /tmp/etcd-backup.db

kubectl cp isa-cloud-staging/apisix-etcd-0:/tmp/etcd-backup.db \
  ./apisix-etcd-$(date +%Y%m%d).db
```

### Restore APISIX

**Restore via Admin API:**
```bash
ADMIN_KEY="edd1c9f034335f136f87ad84b625c8f1"

# Restore routes
for route in $(jq -c '.list[]' apisix-routes.json); do
    route_id=$(echo $route | jq -r '.value.id')
    route_data=$(echo $route | jq -c '.value')
    curl -X PUT "http://localhost:9180/apisix/admin/routes/$route_id" \
      -H "X-API-KEY: $ADMIN_KEY" \
      -H "Content-Type: application/json" \
      -d "$route_data"
done

# Restore upstreams (similar pattern)
# Restore consumers (similar pattern)
```

### Verify APISIX

```bash
# List routes
curl -s http://localhost:9180/apisix/admin/routes \
  -H "X-API-KEY: $ADMIN_KEY" | jq '.total'

# Test gateway
curl -s http://localhost:9080/health
```

## Automation Scripts

The `scripts/` folder contains complete automation:

| Script | Description |
|--------|-------------|
| `backup-all.sh` | Full backup of ALL 8 services |
| `restore-all.sh` | Full restore from backup |

### Usage

```bash
# Full backup
./scripts/backup-all.sh

# Backup to custom location
./scripts/backup-all.sh /path/to/backup

# Full restore
./scripts/restore-all.sh /path/to/backup

# With custom namespace
NAMESPACE=isa-cloud-prod ./scripts/backup-all.sh
```

## Related Documentation

- [cluster-operations](../cluster-operations/SKILL.md) - Full cluster operations
- [api-service-operations](../api-service-operations/SKILL.md) - APISIX + Consul management
