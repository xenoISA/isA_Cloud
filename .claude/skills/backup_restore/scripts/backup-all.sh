#!/bin/bash
# =============================================================================
# Complete Backup Script for isA Cloud Infrastructure
# =============================================================================
# Backs up all critical data stores:
#   - PostgreSQL, Redis, Qdrant, Neo4j, MinIO, Consul, NATS, APISIX
#
# Usage:
#   ./backup-all.sh                    # Auto-detect environment
#   ./backup-all.sh local              # Backup local environment
#   ./backup-all.sh staging            # Backup staging environment
#   ./backup-all.sh production         # Backup production environment
#   ./backup-all.sh local /custom/path # Custom backup location
# =============================================================================

set -e

# Load environment configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(cd "$SCRIPT_DIR/../../config" && pwd)"
source "$CONFIG_DIR/environments.sh"

# Parse arguments
ENV_ARG="${1:-}"
BACKUP_PATH="${2:-}"

# Load environment (auto-detect if not specified)
if [ -n "$ENV_ARG" ] && [[ "$ENV_ARG" =~ ^(local|staging|production)$ ]]; then
    load_environment "$ENV_ARG"
    BACKUP_PATH="${2:-}"
else
    load_environment
    BACKUP_PATH="${1:-}"
fi

# Verify connection
if ! verify_connection; then
    exit 1
fi

# Set backup directory
# isA_Cloud directory (4 levels up from scripts: scripts -> data-backup -> skills -> .claude -> isA_Cloud)
ISA_CLOUD_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
DEFAULT_BACKUP_DIR="$ISA_CLOUD_DIR/backups/${ISA_ENV}-backup-$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${BACKUP_PATH:-$DEFAULT_BACKUP_DIR}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=============================================="
echo "ISA Cloud Complete Backup"
echo "=============================================="
echo -e "${NC}"
echo "Environment:      $ISA_ENV"
echo "Cluster:          $CLUSTER_NAME"
echo "Namespace:        $NAMESPACE"
echo "Backup directory: $BACKUP_DIR"
echo ""

# Create backup directories
mkdir -p "$BACKUP_DIR"/{postgres,redis,qdrant,neo4j,minio,consul,nats,apisix}

# =============================================================================
# 1. PostgreSQL Backup
# =============================================================================
echo -e "${YELLOW}[1/8] Backing up PostgreSQL...${NC}"
PG_POD=$(get_pod postgresql)

if [ -n "$PG_POD" ] && kubectl get pod -n "$NAMESPACE" "$PG_POD" &>/dev/null; then
    # Get PostgreSQL password from secret
    PG_PASS=$(kubectl get secret -n "$NAMESPACE" postgresql -o jsonpath='{.data.postgres-password}' 2>/dev/null | base64 -d || \
              kubectl get secret -n "$NAMESPACE" postgresql -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo "")

    # Full dump with password
    kubectl exec -n "$NAMESPACE" "$PG_POD" -- bash -c "PGPASSWORD='$PG_PASS' pg_dumpall -U postgres" > "$BACKUP_DIR/postgres/full_backup.sql" 2>/dev/null && \
        echo -e "  ${GREEN}✓ PostgreSQL full backup ($(du -h "$BACKUP_DIR/postgres/full_backup.sql" | cut -f1))${NC}" || \
        echo -e "  ${RED}✗ PostgreSQL backup failed${NC}"

    # Individual databases
    for db in $(kubectl exec -n "$NAMESPACE" "$PG_POD" -- bash -c "PGPASSWORD='$PG_PASS' psql -U postgres -t -c \"SELECT datname FROM pg_database WHERE datistemplate = false AND datname != 'postgres';\"" 2>/dev/null | tr -d ' '); do
        if [ -n "$db" ]; then
            kubectl exec -n "$NAMESPACE" "$PG_POD" -- bash -c "PGPASSWORD='$PG_PASS' pg_dump -U postgres -Fc '$db'" > "$BACKUP_DIR/postgres/${db}.dump" 2>/dev/null && \
                echo -e "  ${GREEN}✓ Database '$db' backed up${NC}" || true
        fi
    done
else
    echo -e "  ${YELLOW}⚠ PostgreSQL pod not found${NC}"
fi

# =============================================================================
# 2. Redis Backup
# =============================================================================
echo ""
echo -e "${YELLOW}[2/8] Backing up Redis...${NC}"
REDIS_POD=$(get_pod redis)

if [ -n "$REDIS_POD" ] && kubectl get pod -n "$NAMESPACE" "$REDIS_POD" &>/dev/null; then
    REDIS_PASS=$(kubectl get secret -n "$NAMESPACE" redis -o jsonpath='{.data.redis-password}' 2>/dev/null | base64 -d || echo "")

    # Trigger save
    if [ -n "$REDIS_PASS" ]; then
        kubectl exec -n "$NAMESPACE" "$REDIS_POD" -- redis-cli -a "$REDIS_PASS" BGSAVE 2>/dev/null || true
    else
        kubectl exec -n "$NAMESPACE" "$REDIS_POD" -- redis-cli BGSAVE 2>/dev/null || true
    fi
    sleep 2

    # Copy RDB file
    kubectl cp "$NAMESPACE/$REDIS_POD:/data/dump.rdb" "$BACKUP_DIR/redis/dump.rdb" 2>/dev/null && \
        echo -e "  ${GREEN}✓ Redis backup complete ($(du -h "$BACKUP_DIR/redis/dump.rdb" 2>/dev/null | cut -f1))${NC}" || \
        echo -e "  ${RED}✗ Redis backup failed${NC}"
else
    echo -e "  ${YELLOW}⚠ Redis pod not found${NC}"
fi

# =============================================================================
# 3. Qdrant Backup
# =============================================================================
echo ""
echo -e "${YELLOW}[3/8] Backing up Qdrant...${NC}"
QDRANT_SVC=$(get_service qdrant)

# Port forward
kubectl port-forward -n "$NAMESPACE" "svc/$QDRANT_SVC" 16333:6333 &>/dev/null &
PF_PID=$!
sleep 2

COLLECTIONS=$(curl -s http://localhost:16333/collections 2>/dev/null | jq -r '.result.collections[].name' 2>/dev/null || echo "")
if [ -n "$COLLECTIONS" ]; then
    for collection in $COLLECTIONS; do
        echo "  Creating snapshot for collection: $collection"
        SNAPSHOT=$(curl -s -X POST "http://localhost:16333/collections/$collection/snapshots" 2>/dev/null | jq -r '.result.name' 2>/dev/null || echo "")
        if [ -n "$SNAPSHOT" ] && [ "$SNAPSHOT" != "null" ]; then
            curl -s "http://localhost:16333/collections/$collection/snapshots/$SNAPSHOT" -o "$BACKUP_DIR/qdrant/${collection}_${SNAPSHOT}.snapshot" 2>/dev/null && \
                echo -e "  ${GREEN}✓ Collection '$collection' backed up${NC}" || true
        fi
    done
else
    echo -e "  ${YELLOW}⚠ No Qdrant collections found${NC}"
fi

kill $PF_PID 2>/dev/null || true

# =============================================================================
# 4. Neo4j Backup
# =============================================================================
echo ""
echo -e "${YELLOW}[4/8] Backing up Neo4j...${NC}"
NEO4J_POD=$(get_pod neo4j)

if [ -n "$NEO4J_POD" ] && kubectl get pod -n "$NAMESPACE" "$NEO4J_POD" &>/dev/null; then
    # Get Neo4j password
    NEO4J_PASS=$(kubectl get secret -n "$NAMESPACE" neo4j -o jsonpath='{.data.neo4j-password}' 2>/dev/null | base64 -d || \
                 kubectl get secret -n "$NAMESPACE" neo4j -o jsonpath='{.data.NEO4J_AUTH}' 2>/dev/null | base64 -d | cut -d'/' -f2 || echo "neo4j")

    # Try online backup first (works with running database)
    if kubectl exec -n "$NAMESPACE" "$NEO4J_POD" -- neo4j-admin database backup neo4j --to-path=/tmp/backup --include-metadata=all 2>/dev/null; then
        kubectl exec -n "$NAMESPACE" "$NEO4J_POD" -- tar czf /tmp/neo4j-backup.tar.gz -C /tmp/backup . 2>/dev/null
        kubectl cp "$NAMESPACE/$NEO4J_POD:/tmp/neo4j-backup.tar.gz" "$BACKUP_DIR/neo4j/neo4j-backup.tar.gz" 2>/dev/null && \
            echo -e "  ${GREEN}✓ Neo4j online backup complete${NC}"
    # Fallback: Export data using cypher-shell
    elif kubectl exec -n "$NAMESPACE" "$NEO4J_POD" -- cypher-shell -u neo4j -p "$NEO4J_PASS" "CALL apoc.export.cypher.all('/tmp/neo4j-export.cypher', {})" 2>/dev/null; then
        kubectl cp "$NAMESPACE/$NEO4J_POD:/tmp/neo4j-export.cypher" "$BACKUP_DIR/neo4j/neo4j-export.cypher" 2>/dev/null && \
            echo -e "  ${GREEN}✓ Neo4j data exported via cypher${NC}"
    # Last resort: offline dump
    else
        kubectl exec -n "$NAMESPACE" "$NEO4J_POD" -- neo4j-admin database dump neo4j --to-path=/tmp/ 2>/dev/null && \
            kubectl cp "$NAMESPACE/$NEO4J_POD:/tmp/neo4j.dump" "$BACKUP_DIR/neo4j/neo4j.dump" 2>/dev/null && \
            echo -e "  ${GREEN}✓ Neo4j backup complete${NC}" || \
            echo -e "  ${YELLOW}⚠ Neo4j backup failed (database may need to be stopped for offline backup)${NC}"
    fi
else
    echo -e "  ${YELLOW}⚠ Neo4j pod not found${NC}"
fi

# =============================================================================
# 5. MinIO Backup
# =============================================================================
echo ""
echo -e "${YELLOW}[5/8] Backing up MinIO...${NC}"
MINIO_SVC=$(get_service minio)

kubectl port-forward -n "$NAMESPACE" "svc/$MINIO_SVC" 19000:9000 &>/dev/null &
PF_PID=$!
sleep 2

MINIO_ACCESS_KEY=$(kubectl get secret -n "$NAMESPACE" minio -o jsonpath='{.data.root-user}' 2>/dev/null | base64 -d || \
                   kubectl get secret -n "$NAMESPACE" minio -o jsonpath='{.data.rootUser}' 2>/dev/null | base64 -d || \
                   echo "minioadmin")
MINIO_SECRET_KEY=$(kubectl get secret -n "$NAMESPACE" minio -o jsonpath='{.data.root-password}' 2>/dev/null | base64 -d || \
                   kubectl get secret -n "$NAMESPACE" minio -o jsonpath='{.data.rootPassword}' 2>/dev/null | base64 -d || \
                   echo "minioadmin")

if command -v mc &>/dev/null; then
    mc alias set isa-backup http://localhost:19000 "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" --api S3v4 2>/dev/null || true
    mc mirror isa-backup/ "$BACKUP_DIR/minio/" 2>/dev/null && \
        echo -e "  ${GREEN}✓ MinIO backup complete${NC}" || \
        echo -e "  ${YELLOW}⚠ MinIO backup failed${NC}"
else
    echo -e "  ${YELLOW}⚠ MinIO client (mc) not installed. Skipping.${NC}"
fi

kill $PF_PID 2>/dev/null || true

# =============================================================================
# 6. Consul Backup
# =============================================================================
echo ""
echo -e "${YELLOW}[6/8] Backing up Consul...${NC}"
CONSUL_POD=$(get_pod consul)

if [ -n "$CONSUL_POD" ] && kubectl get pod -n "$NAMESPACE" "$CONSUL_POD" &>/dev/null; then
    # Snapshot entire cluster state
    kubectl exec -n "$NAMESPACE" "$CONSUL_POD" -- consul snapshot save /tmp/consul-backup.snap 2>/dev/null && \
        kubectl cp "$NAMESPACE/$CONSUL_POD:/tmp/consul-backup.snap" "$BACKUP_DIR/consul/consul.snap" 2>/dev/null && \
        echo -e "  ${GREEN}✓ Consul snapshot saved${NC}" || \
        echo -e "  ${RED}✗ Consul snapshot failed${NC}"

    # Export KV store as JSON
    kubectl exec -n "$NAMESPACE" "$CONSUL_POD" -- consul kv export > "$BACKUP_DIR/consul/kv-store.json" 2>/dev/null && \
        echo -e "  ${GREEN}✓ Consul KV store exported${NC}" || true

    # Export service catalog
    kubectl exec -n "$NAMESPACE" "$CONSUL_POD" -- consul catalog services -detailed > "$BACKUP_DIR/consul/services.txt" 2>/dev/null && \
        echo -e "  ${GREEN}✓ Consul service catalog exported${NC}" || true
else
    echo -e "  ${YELLOW}⚠ Consul pod not found${NC}"
fi

# =============================================================================
# 7. NATS JetStream Backup
# =============================================================================
echo ""
echo -e "${YELLOW}[7/8] Backing up NATS JetStream...${NC}"
NATS_POD=$(get_pod nats)

if [ -n "$NATS_POD" ] && kubectl get pod -n "$NAMESPACE" "$NATS_POD" &>/dev/null; then
    kubectl port-forward -n "$NAMESPACE" "$NATS_POD" 14222:4222 &>/dev/null &
    PF_PID=$!
    sleep 2

    if command -v nats &>/dev/null; then
        # Export stream configurations
        nats --server=localhost:14222 stream ls -j > "$BACKUP_DIR/nats/streams.json" 2>/dev/null && \
            echo -e "  ${GREEN}✓ Stream list exported${NC}" || true

        # Backup each stream configuration
        for stream in $(nats --server=localhost:14222 stream ls 2>/dev/null | grep -v "^Streams:" | tr -d ' '); do
            if [ -n "$stream" ]; then
                mkdir -p "$BACKUP_DIR/nats/streams/$stream"
                nats --server=localhost:14222 stream info "$stream" -j > "$BACKUP_DIR/nats/streams/$stream/config.json" 2>/dev/null && \
                    echo -e "  ${GREEN}✓ Stream '$stream' config backed up${NC}" || true
                nats --server=localhost:14222 consumer ls "$stream" -j > "$BACKUP_DIR/nats/streams/$stream/consumers.json" 2>/dev/null || true
            fi
        done

        nats --server=localhost:14222 account info -j > "$BACKUP_DIR/nats/account.json" 2>/dev/null || true
    else
        echo -e "  ${YELLOW}⚠ NATS CLI not installed. Using kubectl fallback.${NC}"
        kubectl exec -n "$NAMESPACE" "$NATS_POD" -c nats -- tar czf /tmp/jetstream-backup.tar.gz /data/jetstream 2>/dev/null && \
            kubectl cp "$NAMESPACE/$NATS_POD:/tmp/jetstream-backup.tar.gz" "$BACKUP_DIR/nats/jetstream-data.tar.gz" 2>/dev/null && \
            echo -e "  ${GREEN}✓ JetStream data directory backed up${NC}" || \
            echo -e "  ${YELLOW}⚠ JetStream backup failed${NC}"
    fi

    kill $PF_PID 2>/dev/null || true
else
    echo -e "  ${YELLOW}⚠ NATS pod not found${NC}"
fi

# =============================================================================
# 8. APISIX Backup (via Admin API)
# =============================================================================
echo ""
echo -e "${YELLOW}[8/8] Backing up APISIX...${NC}"
APISIX_SVC=$(get_service apisix)

kubectl port-forward -n "$NAMESPACE" "svc/$APISIX_SVC" 19180:9180 &>/dev/null &
PF_PID=$!
sleep 2

ADMIN_KEY="${APISIX_ADMIN_KEY:-edd1c9f034335f136f87ad84b625c8f1}"

# Export routes
curl -s http://localhost:19180/apisix/admin/routes -H "X-API-KEY: $ADMIN_KEY" 2>/dev/null | jq . > "$BACKUP_DIR/apisix/routes.json" && \
    echo -e "  ${GREEN}✓ APISIX routes exported ($(jq '.total // (.list | length)' "$BACKUP_DIR/apisix/routes.json" 2>/dev/null) routes)${NC}" || true

# Export upstreams
curl -s http://localhost:19180/apisix/admin/upstreams -H "X-API-KEY: $ADMIN_KEY" 2>/dev/null | jq . > "$BACKUP_DIR/apisix/upstreams.json" && \
    echo -e "  ${GREEN}✓ APISIX upstreams exported${NC}" || true

# Export services
curl -s http://localhost:19180/apisix/admin/services -H "X-API-KEY: $ADMIN_KEY" 2>/dev/null | jq . > "$BACKUP_DIR/apisix/services.json" && \
    echo -e "  ${GREEN}✓ APISIX services exported${NC}" || true

# Export plugins, global rules, consumers
curl -s http://localhost:19180/apisix/admin/plugins/list -H "X-API-KEY: $ADMIN_KEY" 2>/dev/null | jq . > "$BACKUP_DIR/apisix/plugins.json" 2>/dev/null || true
curl -s http://localhost:19180/apisix/admin/global_rules -H "X-API-KEY: $ADMIN_KEY" 2>/dev/null | jq . > "$BACKUP_DIR/apisix/global_rules.json" 2>/dev/null || true
curl -s http://localhost:19180/apisix/admin/consumers -H "X-API-KEY: $ADMIN_KEY" 2>/dev/null | jq . > "$BACKUP_DIR/apisix/consumers.json" 2>/dev/null || true
curl -s http://localhost:19180/apisix/admin/ssls -H "X-API-KEY: $ADMIN_KEY" 2>/dev/null | jq . > "$BACKUP_DIR/apisix/ssl.json" 2>/dev/null || true

kill $PF_PID 2>/dev/null || true

# Backup etcd directly if available
ETCD_POD=$(get_pod etcd)
if [ -n "$ETCD_POD" ] && kubectl get pod -n "$NAMESPACE" "$ETCD_POD" &>/dev/null; then
    kubectl exec -n "$NAMESPACE" "$ETCD_POD" -- etcdctl snapshot save /tmp/etcd-backup.db 2>/dev/null && \
        kubectl cp "$NAMESPACE/$ETCD_POD:/tmp/etcd-backup.db" "$BACKUP_DIR/apisix/etcd-snapshot.db" 2>/dev/null && \
        echo -e "  ${GREEN}✓ etcd snapshot saved${NC}" || true
fi

# =============================================================================
# Create Backup Metadata
# =============================================================================
echo ""
echo "Creating backup metadata..."

cat > "$BACKUP_DIR/metadata.json" << EOF
{
    "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "environment": "$ISA_ENV",
    "cluster": "$CLUSTER_NAME",
    "namespace": "$NAMESPACE",
    "backup_dir": "$BACKUP_DIR",
    "services_backed_up": {
        "postgresql": $([ -f "$BACKUP_DIR/postgres/full_backup.sql" ] && echo "true" || echo "false"),
        "redis": $([ -f "$BACKUP_DIR/redis/dump.rdb" ] && echo "true" || echo "false"),
        "qdrant": $([ "$(ls -A "$BACKUP_DIR/qdrant" 2>/dev/null)" ] && echo "true" || echo "false"),
        "neo4j": $([ -f "$BACKUP_DIR/neo4j/neo4j.dump" ] && echo "true" || echo "false"),
        "minio": $([ "$(ls -A "$BACKUP_DIR/minio" 2>/dev/null)" ] && echo "true" || echo "false"),
        "consul": $([ -f "$BACKUP_DIR/consul/consul.snap" ] && echo "true" || echo "false"),
        "nats": $([ "$(ls -A "$BACKUP_DIR/nats" 2>/dev/null)" ] && echo "true" || echo "false"),
        "apisix": $([ -f "$BACKUP_DIR/apisix/routes.json" ] && echo "true" || echo "false")
    }
}
EOF

# =============================================================================
# Summary
# =============================================================================
echo ""
echo -e "${BLUE}=============================================="
echo "Backup Summary"
echo "=============================================="
echo -e "${NC}"
echo "Environment: $ISA_ENV"
echo "Location: $BACKUP_DIR"
echo ""
du -sh "$BACKUP_DIR"/* 2>/dev/null || true
echo ""
echo "Total size: $(du -sh "$BACKUP_DIR" | cut -f1)"
echo ""
echo "To restore:"
echo "  ./restore-all.sh $ISA_ENV $BACKUP_DIR"
echo "=============================================="
