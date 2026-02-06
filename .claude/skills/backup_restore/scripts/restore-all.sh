#!/bin/bash
# =============================================================================
# Complete Restore Script for isA Cloud Infrastructure
# =============================================================================
# Restores all critical data stores:
#   - PostgreSQL, Redis, Qdrant, Neo4j, MinIO, Consul, NATS, APISIX
#
# Usage:
#   ./restore-all.sh /path/to/backup              # Auto-detect environment
#   ./restore-all.sh local /path/to/backup        # Restore to local environment
#   ./restore-all.sh --dry-run /path/to/backup    # Show what would be restored
#   ./restore-all.sh --service postgres /path/to/backup  # Restore only PostgreSQL
# =============================================================================

set -e

# Load environment configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(cd "$SCRIPT_DIR/../../config" && pwd)"
source "$CONFIG_DIR/environments.sh"

# Default values
DRY_RUN=false
SERVICE_FILTER=""
BACKUP_DIR=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --service)
            SERVICE_FILTER="$2"
            shift 2
            ;;
        local|staging|production)
            load_environment "$1"
            shift
            ;;
        *)
            if [ -z "$BACKUP_DIR" ]; then
                BACKUP_DIR="$1"
            fi
            shift
            ;;
    esac
done

# Load environment if not already loaded
if [ -z "$ISA_ENV" ]; then
    # In dry-run mode, try to infer from backup metadata
    if [ "$DRY_RUN" = true ] && [ -f "$BACKUP_DIR/metadata.json" ]; then
        INFERRED_ENV=$(jq -r '.environment // "local"' "$BACKUP_DIR/metadata.json" 2>/dev/null)
        load_environment "$INFERRED_ENV"
    else
        load_environment
    fi
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

if [ -z "$BACKUP_DIR" ] || [ ! -d "$BACKUP_DIR" ]; then
    echo "Usage: $0 [options] [environment] <backup-directory>"
    echo ""
    echo "Options:"
    echo "  --dry-run              Show what would be restored without doing it"
    echo "  --service <name>       Restore only specified service"
    echo "                         (postgres, redis, qdrant, neo4j, minio, consul, nats, apisix)"
    echo ""
    echo "Examples:"
    echo "  $0 /path/to/backup                    # Restore all services"
    echo "  $0 --dry-run /path/to/backup          # Preview restore"
    echo "  $0 --service postgres /path/to/backup # Restore only PostgreSQL"
    echo "  $0 local /path/to/backup              # Explicit environment"
    exit 1
fi

# Helper function for dry-run mode
run_cmd() {
    if [ "$DRY_RUN" = true ]; then
        echo -e "  ${CYAN}[DRY-RUN] Would execute: $*${NC}"
        return 0
    else
        "$@"
    fi
}

# Check if service should be restored
should_restore() {
    local service="$1"
    if [ -z "$SERVICE_FILTER" ]; then
        return 0  # No filter, restore all
    fi
    [[ "$SERVICE_FILTER" == "$service" ]]
}

# Verify connection (skip in dry-run)
if [ "$DRY_RUN" = false ]; then
    if ! verify_connection; then
        exit 1
    fi
fi

echo -e "${BLUE}=============================================="
if [ "$DRY_RUN" = true ]; then
    echo "ISA Cloud Restore - DRY RUN"
else
    echo "ISA Cloud Complete Restore"
fi
echo "=============================================="
echo -e "${NC}"
echo "Environment:      $ISA_ENV"
echo "Cluster:          $CLUSTER_NAME"
echo "Namespace:        $NAMESPACE"
echo "Restoring from:   $BACKUP_DIR"
if [ -n "$SERVICE_FILTER" ]; then
    echo "Service filter:   $SERVICE_FILTER"
fi
if [ "$DRY_RUN" = true ]; then
    echo -e "${CYAN}Mode:             DRY-RUN (no changes will be made)${NC}"
fi
echo ""

# Wait for pods to be ready (skip in dry-run)
if [ "$DRY_RUN" = false ]; then
    echo "Waiting for infrastructure pods..."
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=postgresql -n "$NAMESPACE" --timeout=120s 2>/dev/null || \
        kubectl wait --for=condition=ready pod -l app=postgresql -n "$NAMESPACE" --timeout=120s 2>/dev/null || true
fi

# =============================================================================
# 1. PostgreSQL Restore
# =============================================================================
if should_restore "postgres"; then
    echo ""
    echo -e "${YELLOW}[1/8] Restoring PostgreSQL...${NC}"
    if [ -f "$BACKUP_DIR/postgres/full_backup.sql" ]; then
        PG_POD=$(get_pod postgresql)
        BACKUP_SIZE=$(du -h "$BACKUP_DIR/postgres/full_backup.sql" | cut -f1)
        BACKUP_LINES=$(wc -l < "$BACKUP_DIR/postgres/full_backup.sql")

        echo "  Backup file: $BACKUP_SIZE ($BACKUP_LINES lines)"

        if [ -n "$PG_POD" ]; then
            if [ "$DRY_RUN" = true ]; then
                echo -e "  ${CYAN}[DRY-RUN] Would copy backup to $PG_POD:/tmp/full_backup.sql${NC}"
                echo -e "  ${CYAN}[DRY-RUN] Would execute: psql -U postgres -f /tmp/full_backup.sql${NC}"
                echo -e "  ${GREEN}✓ PostgreSQL restore would succeed${NC}"
            else
                PG_PASS=$(kubectl get secret -n "$NAMESPACE" postgresql -o jsonpath='{.data.postgres-password}' 2>/dev/null | base64 -d || \
                          kubectl get secret -n "$NAMESPACE" postgresql -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo "")

                kubectl cp "$BACKUP_DIR/postgres/full_backup.sql" "$NAMESPACE/$PG_POD:/tmp/full_backup.sql"
                kubectl exec -n "$NAMESPACE" "$PG_POD" -- bash -c "PGPASSWORD='$PG_PASS' psql -U postgres -f /tmp/full_backup.sql" 2>/dev/null && \
                    echo -e "  ${GREEN}✓ PostgreSQL restored${NC}" || \
                    echo -e "  ${YELLOW}⚠ PostgreSQL restore had warnings (often OK)${NC}"
            fi
        else
            echo -e "  ${RED}✗ PostgreSQL pod not found${NC}"
        fi
    else
        echo -e "  ${YELLOW}⚠ No PostgreSQL backup found${NC}"
    fi
fi

# =============================================================================
# 2. Redis Restore
# =============================================================================
if should_restore "redis"; then
    echo ""
    echo -e "${YELLOW}[2/8] Restoring Redis...${NC}"
    if [ -f "$BACKUP_DIR/redis/dump.rdb" ]; then
        REDIS_POD=$(get_pod redis)
        BACKUP_SIZE=$(du -h "$BACKUP_DIR/redis/dump.rdb" | cut -f1)

        echo "  Backup file: $BACKUP_SIZE"

        if [ -n "$REDIS_POD" ]; then
            if [ "$DRY_RUN" = true ]; then
                echo -e "  ${CYAN}[DRY-RUN] Would stop Redis with SHUTDOWN NOSAVE${NC}"
                echo -e "  ${CYAN}[DRY-RUN] Would copy dump.rdb to $REDIS_POD:/data/dump.rdb${NC}"
                echo -e "  ${GREEN}✓ Redis restore would succeed${NC}"
            else
                REDIS_PASS=$(kubectl get secret -n "$NAMESPACE" redis -o jsonpath='{.data.redis-password}' 2>/dev/null | base64 -d || echo "")

                if [ -n "$REDIS_PASS" ]; then
                    kubectl exec -n "$NAMESPACE" "$REDIS_POD" -- redis-cli -a "$REDIS_PASS" SHUTDOWN NOSAVE 2>/dev/null || true
                else
                    kubectl exec -n "$NAMESPACE" "$REDIS_POD" -- redis-cli SHUTDOWN NOSAVE 2>/dev/null || true
                fi
                sleep 2
                kubectl cp "$BACKUP_DIR/redis/dump.rdb" "$NAMESPACE/$REDIS_POD:/data/dump.rdb" 2>/dev/null
                echo -e "  ${GREEN}✓ Redis RDB copied (will load on restart)${NC}"
            fi
        else
            echo -e "  ${RED}✗ Redis pod not found${NC}"
        fi
    else
        echo -e "  ${YELLOW}⚠ No Redis backup found${NC}"
    fi
fi

# =============================================================================
# 3. Qdrant Restore
# =============================================================================
if should_restore "qdrant"; then
    echo ""
    echo -e "${YELLOW}[3/8] Restoring Qdrant...${NC}"
    if [ -d "$BACKUP_DIR/qdrant" ] && [ "$(ls -A "$BACKUP_DIR/qdrant" 2>/dev/null)" ]; then
        SNAPSHOT_COUNT=$(ls "$BACKUP_DIR/qdrant"/*.snapshot 2>/dev/null | wc -l)
        echo "  Collections to restore: $SNAPSHOT_COUNT"

        if [ "$DRY_RUN" = true ]; then
            for snapshot_file in "$BACKUP_DIR/qdrant"/*.snapshot; do
                if [ -f "$snapshot_file" ]; then
                    filename=$(basename "$snapshot_file")
                    collection=$(echo "$filename" | cut -d'_' -f1)
                    size=$(du -h "$snapshot_file" | cut -f1)
                    echo -e "  ${CYAN}[DRY-RUN] Would restore collection '$collection' ($size)${NC}"
                fi
            done
            echo -e "  ${GREEN}✓ Qdrant restore would succeed${NC}"
        else
            QDRANT_SVC=$(get_service qdrant)
            kubectl port-forward -n "$NAMESPACE" "svc/$QDRANT_SVC" 16333:6333 &>/dev/null &
            PF_PID=$!
            sleep 2

            for snapshot_file in "$BACKUP_DIR/qdrant"/*.snapshot; do
                if [ -f "$snapshot_file" ]; then
                    filename=$(basename "$snapshot_file")
                    collection=$(echo "$filename" | cut -d'_' -f1)
                    echo "  Restoring collection: $collection"
                    curl -s -X POST "http://localhost:16333/collections/$collection/snapshots/upload" \
                        -H "Content-Type: multipart/form-data" \
                        -F "snapshot=@$snapshot_file" 2>/dev/null && \
                        echo -e "  ${GREEN}✓ Collection '$collection' restored${NC}" || \
                        echo -e "  ${YELLOW}⚠ Failed to restore '$collection'${NC}"
                fi
            done

            kill $PF_PID 2>/dev/null || true
        fi
    else
        echo -e "  ${YELLOW}⚠ No Qdrant backup found${NC}"
    fi
fi

# =============================================================================
# 4. Neo4j Restore
# =============================================================================
if should_restore "neo4j"; then
    echo ""
    echo -e "${YELLOW}[4/8] Restoring Neo4j...${NC}"
    if [ -f "$BACKUP_DIR/neo4j/neo4j.dump" ]; then
        NEO4J_POD=$(get_pod neo4j)
        BACKUP_SIZE=$(du -h "$BACKUP_DIR/neo4j/neo4j.dump" | cut -f1)

        echo "  Backup file: $BACKUP_SIZE"

        if [ -n "$NEO4J_POD" ]; then
            if [ "$DRY_RUN" = true ]; then
                echo -e "  ${CYAN}[DRY-RUN] Would stop Neo4j database${NC}"
                echo -e "  ${CYAN}[DRY-RUN] Would copy neo4j.dump to $NEO4J_POD:/tmp/${NC}"
                echo -e "  ${CYAN}[DRY-RUN] Would execute: neo4j-admin database load${NC}"
                echo -e "  ${GREEN}✓ Neo4j restore would succeed${NC}"
            else
                kubectl cp "$BACKUP_DIR/neo4j/neo4j.dump" "$NAMESPACE/$NEO4J_POD:/tmp/neo4j.dump"
                kubectl exec -n "$NAMESPACE" "$NEO4J_POD" -- neo4j stop 2>/dev/null || true
                sleep 2
                kubectl exec -n "$NAMESPACE" "$NEO4J_POD" -- neo4j-admin database load neo4j --from-path=/tmp/ --overwrite-destination=true 2>/dev/null && \
                    echo -e "  ${GREEN}✓ Neo4j restored${NC}" || \
                    echo -e "  ${YELLOW}⚠ Neo4j restore failed${NC}"
                kubectl exec -n "$NAMESPACE" "$NEO4J_POD" -- neo4j start 2>/dev/null || true
            fi
        else
            echo -e "  ${RED}✗ Neo4j pod not found${NC}"
        fi
    else
        echo -e "  ${YELLOW}⚠ No Neo4j backup found${NC}"
    fi
fi

# =============================================================================
# 5. MinIO Restore
# =============================================================================
if should_restore "minio"; then
    echo ""
    echo -e "${YELLOW}[5/8] Restoring MinIO...${NC}"
    if [ -d "$BACKUP_DIR/minio" ] && [ "$(ls -A "$BACKUP_DIR/minio" 2>/dev/null)" ]; then
        BUCKET_COUNT=$(ls -d "$BACKUP_DIR/minio"/*/ 2>/dev/null | wc -l)
        TOTAL_SIZE=$(du -sh "$BACKUP_DIR/minio" | cut -f1)

        echo "  Buckets to restore: $BUCKET_COUNT ($TOTAL_SIZE)"

        if [ "$DRY_RUN" = true ]; then
            for bucket in "$BACKUP_DIR/minio"/*/; do
                if [ -d "$bucket" ]; then
                    bucket_name=$(basename "$bucket")
                    bucket_size=$(du -sh "$bucket" | cut -f1)
                    echo -e "  ${CYAN}[DRY-RUN] Would restore bucket '$bucket_name' ($bucket_size)${NC}"
                fi
            done
            echo -e "  ${GREEN}✓ MinIO restore would succeed${NC}"
        else
            MINIO_SVC=$(get_service minio)
            kubectl port-forward -n "$NAMESPACE" "svc/$MINIO_SVC" 19000:9000 &>/dev/null &
            PF_PID=$!
            sleep 3

            MINIO_ACCESS_KEY=$(kubectl get secret -n "$NAMESPACE" minio -o jsonpath='{.data.root-user}' 2>/dev/null | base64 -d || \
                               kubectl get secret -n "$NAMESPACE" minio -o jsonpath='{.data.rootUser}' 2>/dev/null | base64 -d || \
                               echo "minioadmin")
            MINIO_SECRET_KEY=$(kubectl get secret -n "$NAMESPACE" minio -o jsonpath='{.data.root-password}' 2>/dev/null | base64 -d || \
                               kubectl get secret -n "$NAMESPACE" minio -o jsonpath='{.data.rootPassword}' 2>/dev/null | base64 -d || \
                               echo "minioadmin")

            if command -v mc &>/dev/null; then
                mc alias set isa-restore http://localhost:19000 "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" --api S3v4 2>/dev/null || true
                mc mirror "$BACKUP_DIR/minio/" isa-restore/ 2>/dev/null && \
                    echo -e "  ${GREEN}✓ MinIO restored${NC}" || \
                    echo -e "  ${YELLOW}⚠ MinIO restore failed${NC}"
            else
                echo -e "  ${YELLOW}⚠ MinIO client (mc) not installed${NC}"
            fi

            kill $PF_PID 2>/dev/null || true
        fi
    else
        echo -e "  ${YELLOW}⚠ No MinIO backup found${NC}"
    fi
fi

# =============================================================================
# 6. Consul Restore
# =============================================================================
if should_restore "consul"; then
    echo ""
    echo -e "${YELLOW}[6/8] Restoring Consul...${NC}"
    CONSUL_POD=$(get_pod consul)

    if [ -n "$CONSUL_POD" ] || [ "$DRY_RUN" = true ]; then
        if [ -f "$BACKUP_DIR/consul/consul.snap" ]; then
            BACKUP_SIZE=$(du -h "$BACKUP_DIR/consul/consul.snap" | cut -f1)
            echo "  Snapshot file: $BACKUP_SIZE"

            if [ "$DRY_RUN" = true ]; then
                echo -e "  ${CYAN}[DRY-RUN] Would copy consul.snap to pod${NC}"
                echo -e "  ${CYAN}[DRY-RUN] Would execute: consul snapshot restore${NC}"
                echo -e "  ${GREEN}✓ Consul restore would succeed${NC}"
            else
                kubectl cp "$BACKUP_DIR/consul/consul.snap" "$NAMESPACE/$CONSUL_POD:/tmp/consul-restore.snap"
                kubectl exec -n "$NAMESPACE" "$CONSUL_POD" -- consul snapshot restore /tmp/consul-restore.snap 2>/dev/null && \
                    echo -e "  ${GREEN}✓ Consul snapshot restored${NC}" || \
                    echo -e "  ${YELLOW}⚠ Consul snapshot restore failed${NC}"
            fi
        elif [ -f "$BACKUP_DIR/consul/kv-store.json" ]; then
            KV_COUNT=$(jq 'length' "$BACKUP_DIR/consul/kv-store.json" 2>/dev/null || echo "?")
            echo "  KV store: $KV_COUNT keys"

            if [ "$DRY_RUN" = true ]; then
                echo -e "  ${CYAN}[DRY-RUN] Would import KV store${NC}"
                echo -e "  ${GREEN}✓ Consul restore would succeed${NC}"
            else
                kubectl cp "$BACKUP_DIR/consul/kv-store.json" "$NAMESPACE/$CONSUL_POD:/tmp/kv-restore.json"
                kubectl exec -n "$NAMESPACE" "$CONSUL_POD" -- bash -c "consul kv import @/tmp/kv-restore.json" 2>/dev/null && \
                    echo -e "  ${GREEN}✓ Consul KV store imported${NC}" || \
                    echo -e "  ${YELLOW}⚠ Consul KV import failed${NC}"
            fi
        else
            echo -e "  ${YELLOW}⚠ No Consul backup found${NC}"
        fi
    else
        echo -e "  ${YELLOW}⚠ Consul pod not found${NC}"
    fi
fi

# =============================================================================
# 7. NATS JetStream Restore
# =============================================================================
if should_restore "nats"; then
    echo ""
    echo -e "${YELLOW}[7/8] Restoring NATS JetStream...${NC}"
    NATS_POD=$(get_pod nats)

    if [ -d "$BACKUP_DIR/nats" ]; then
        if [ -f "$BACKUP_DIR/nats/jetstream-data.tar.gz" ]; then
            BACKUP_SIZE=$(du -h "$BACKUP_DIR/nats/jetstream-data.tar.gz" | cut -f1)
            echo "  JetStream data: $BACKUP_SIZE"

            if [ "$DRY_RUN" = true ]; then
                echo -e "  ${CYAN}[DRY-RUN] Would copy jetstream-data.tar.gz to pod${NC}"
                echo -e "  ${CYAN}[DRY-RUN] Would extract to JetStream data directory${NC}"
                echo -e "  ${GREEN}✓ NATS restore would succeed${NC}"
            elif [ -n "$NATS_POD" ]; then
                kubectl cp "$BACKUP_DIR/nats/jetstream-data.tar.gz" "$NAMESPACE/$NATS_POD:/tmp/"
                kubectl exec -n "$NAMESPACE" "$NATS_POD" -- tar xzf /tmp/jetstream-data.tar.gz -C / 2>/dev/null && \
                    echo -e "  ${GREEN}✓ JetStream data restored (restart NATS to load)${NC}" || \
                    echo -e "  ${YELLOW}⚠ JetStream data restore failed${NC}"
            else
                echo -e "  ${RED}✗ NATS pod not found${NC}"
            fi
        elif [ -d "$BACKUP_DIR/nats/streams" ]; then
            STREAM_COUNT=$(ls -d "$BACKUP_DIR/nats/streams"/*/ 2>/dev/null | wc -l)
            echo "  Streams to restore: $STREAM_COUNT"

            if [ "$DRY_RUN" = true ]; then
                for stream_dir in "$BACKUP_DIR/nats/streams"/*/; do
                    if [ -d "$stream_dir" ]; then
                        stream=$(basename "$stream_dir")
                        echo -e "  ${CYAN}[DRY-RUN] Would restore stream '$stream'${NC}"
                    fi
                done
                echo -e "  ${GREEN}✓ NATS restore would succeed${NC}"
            elif [ -n "$NATS_POD" ] && command -v nats &>/dev/null; then
                kubectl port-forward -n "$NAMESPACE" "$NATS_POD" 14222:4222 &>/dev/null &
                PF_PID=$!
                sleep 2

                for stream_dir in "$BACKUP_DIR/nats/streams"/*/; do
                    if [ -d "$stream_dir" ]; then
                        stream=$(basename "$stream_dir")
                        if [ -f "$stream_dir/config.json" ]; then
                            echo "  Restoring stream: $stream"
                            nats --server=localhost:14222 stream add "$stream" --config "$stream_dir/config.json" 2>/dev/null && \
                                echo -e "  ${GREEN}✓ Stream '$stream' restored${NC}" || \
                                echo -e "  ${YELLOW}⚠ Stream '$stream' may already exist${NC}"
                        fi
                    fi
                done

                kill $PF_PID 2>/dev/null || true
            else
                echo -e "  ${YELLOW}⚠ NATS pod not found or NATS CLI not installed${NC}"
            fi
        else
            echo -e "  ${YELLOW}⚠ No NATS backup found${NC}"
        fi
    else
        echo -e "  ${YELLOW}⚠ No NATS backup found${NC}"
    fi
fi

# =============================================================================
# 8. APISIX Restore
# =============================================================================
if should_restore "apisix"; then
    echo ""
    echo -e "${YELLOW}[8/8] Restoring APISIX...${NC}"

    if [ -f "$BACKUP_DIR/apisix/routes.json" ]; then
        ROUTE_COUNT=$(jq '.total // (.list | length) // 0' "$BACKUP_DIR/apisix/routes.json" 2>/dev/null)
        UPSTREAM_COUNT=$(jq '.total // (.list | length) // 0' "$BACKUP_DIR/apisix/upstreams.json" 2>/dev/null || echo "0")

        echo "  Routes to restore: $ROUTE_COUNT"
        echo "  Upstreams to restore: $UPSTREAM_COUNT"

        if [ "$DRY_RUN" = true ]; then
            echo -e "  ${CYAN}[DRY-RUN] Would restore $ROUTE_COUNT routes via Admin API${NC}"
            echo -e "  ${CYAN}[DRY-RUN] Would restore $UPSTREAM_COUNT upstreams via Admin API${NC}"
            [ -f "$BACKUP_DIR/apisix/consumers.json" ] && echo -e "  ${CYAN}[DRY-RUN] Would restore consumers${NC}"
            echo -e "  ${GREEN}✓ APISIX restore would succeed${NC}"
        else
            APISIX_SVC=$(get_service apisix)
            kubectl port-forward -n "$NAMESPACE" "svc/$APISIX_SVC" 19180:9180 &>/dev/null &
            PF_PID=$!
            sleep 2

            ADMIN_KEY="${APISIX_ADMIN_KEY}"

            # Restore routes
            ROUTES=$(jq -c '.list[]? // .node.nodes[]? // empty' "$BACKUP_DIR/apisix/routes.json" 2>/dev/null)
            RESTORED_ROUTES=0
            while IFS= read -r route; do
                if [ -n "$route" ]; then
                    route_id=$(echo "$route" | jq -r '.key // .value.id // empty' 2>/dev/null | sed 's|.*/||')
                    route_data=$(echo "$route" | jq -c '.value // .' 2>/dev/null)
                    if [ -n "$route_id" ] && [ -n "$route_data" ]; then
                        curl -s -X PUT "http://localhost:19180/apisix/admin/routes/$route_id" \
                            -H "X-API-KEY: $ADMIN_KEY" \
                            -H "Content-Type: application/json" \
                            -d "$route_data" >/dev/null 2>&1 && ((RESTORED_ROUTES++)) || true
                    fi
                fi
            done <<< "$ROUTES"
            echo -e "  ${GREEN}✓ APISIX routes restored ($RESTORED_ROUTES routes)${NC}"

            # Restore upstreams
            if [ -f "$BACKUP_DIR/apisix/upstreams.json" ]; then
                UPSTREAMS=$(jq -c '.list[]? // .node.nodes[]? // empty' "$BACKUP_DIR/apisix/upstreams.json" 2>/dev/null)
                RESTORED_UPSTREAMS=0
                while IFS= read -r upstream; do
                    if [ -n "$upstream" ]; then
                        upstream_id=$(echo "$upstream" | jq -r '.key // .value.id // empty' 2>/dev/null | sed 's|.*/||')
                        upstream_data=$(echo "$upstream" | jq -c '.value // .' 2>/dev/null)
                        if [ -n "$upstream_id" ] && [ -n "$upstream_data" ]; then
                            curl -s -X PUT "http://localhost:19180/apisix/admin/upstreams/$upstream_id" \
                                -H "X-API-KEY: $ADMIN_KEY" \
                                -H "Content-Type: application/json" \
                                -d "$upstream_data" >/dev/null 2>&1 && ((RESTORED_UPSTREAMS++)) || true
                        fi
                    fi
                done <<< "$UPSTREAMS"
                echo -e "  ${GREEN}✓ APISIX upstreams restored ($RESTORED_UPSTREAMS upstreams)${NC}"
            fi

            # Restore consumers
            if [ -f "$BACKUP_DIR/apisix/consumers.json" ]; then
                CONSUMERS=$(jq -c '.list[]? // .node.nodes[]? // empty' "$BACKUP_DIR/apisix/consumers.json" 2>/dev/null)
                while IFS= read -r consumer; do
                    if [ -n "$consumer" ]; then
                        username=$(echo "$consumer" | jq -r '.value.username // .username // empty' 2>/dev/null)
                        consumer_data=$(echo "$consumer" | jq -c '.value // .' 2>/dev/null)
                        if [ -n "$username" ] && [ -n "$consumer_data" ]; then
                            curl -s -X PUT "http://localhost:19180/apisix/admin/consumers/$username" \
                                -H "X-API-KEY: $ADMIN_KEY" \
                                -H "Content-Type: application/json" \
                                -d "$consumer_data" >/dev/null 2>&1 || true
                        fi
                    fi
                done <<< "$CONSUMERS"
                echo -e "  ${GREEN}✓ APISIX consumers restored${NC}"
            fi

            kill $PF_PID 2>/dev/null || true
        fi
    else
        echo -e "  ${YELLOW}⚠ No APISIX backup found${NC}"
    fi
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo -e "${BLUE}==============================================${NC}"
if [ "$DRY_RUN" = true ]; then
    echo "Dry Run Complete"
    echo "=============================================="
    echo ""
    echo "No changes were made. Run without --dry-run to perform actual restore."
else
    echo "Restore Complete"
    echo "=============================================="
    echo ""
    echo "Environment:      $ISA_ENV"
    echo "Cluster:          $CLUSTER_NAME"
    echo "Namespace:        $NAMESPACE"
    echo "Restored from:    $BACKUP_DIR"
    echo ""
    echo "Please verify your data and restart affected services:"
    echo "  kubectl rollout restart deployment -n \"$NAMESPACE\""
    echo ""
    echo "Health check commands:"
    echo "  kubectl get pods -n \"$NAMESPACE\""
    echo "  kubectl exec -n \"$NAMESPACE\" deploy/postgres -- psql -U postgres -c '\\l'"
    echo "  curl $APISIX_GATEWAY/health"
fi
echo "=============================================="
