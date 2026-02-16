#!/bin/bash
# =============================================================================
# Restore Script for Kind Cluster Data
# =============================================================================
# This script restores data after cluster recreation
# Run this AFTER creating the new Kind cluster and deploying infrastructure
#
# Usage:
#   ./restore-cluster-data.sh /path/to/backup
#   ./restore-cluster-data.sh backups/cluster-backup-20260114_211236
# =============================================================================

set -e

BACKUP_DIR="${1:-}"
NAMESPACE="${NAMESPACE:-isa-cloud-staging}"

if [ -z "$BACKUP_DIR" ] || [ ! -d "$BACKUP_DIR" ]; then
    echo "Usage: $0 <backup-directory>"
    echo "Example: $0 ~/isa-cluster-backup-20240115_120000"
    exit 1
fi

echo "=============================================="
echo "ISA Cloud Cluster Restore"
echo "=============================================="
echo "Restoring from: $BACKUP_DIR"
echo ""

# Check cluster connectivity
if ! kubectl cluster-info &>/dev/null; then
    echo "ERROR: Cannot connect to Kubernetes cluster"
    exit 1
fi

# Wait for pods to be ready
echo "Waiting for infrastructure pods to be ready..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=postgresql -n $NAMESPACE --timeout=120s 2>/dev/null || \
    kubectl wait --for=condition=ready pod -l app=postgresql -n $NAMESPACE --timeout=120s 2>/dev/null || \
    echo "Postgres not ready yet"
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=redis -n $NAMESPACE --timeout=120s 2>/dev/null || \
    kubectl wait --for=condition=ready pod -l app=redis -n $NAMESPACE --timeout=120s 2>/dev/null || \
    echo "Redis not ready yet"

echo ""
echo "[1/5] Restoring PostgreSQL..."
if [ -f "$BACKUP_DIR/postgres/full_backup.sql" ]; then
    PG_POD=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
             kubectl get pods -n $NAMESPACE -l app=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
             echo "postgresql-0")

    # Copy and restore
    kubectl cp "$BACKUP_DIR/postgres/full_backup.sql" $NAMESPACE/$PG_POD:/tmp/full_backup.sql
    kubectl exec -n $NAMESPACE $PG_POD -- psql -U postgres -f /tmp/full_backup.sql 2>/dev/null && \
        echo "  ✓ PostgreSQL restored" || \
        echo "  ⚠ PostgreSQL restore had warnings (this is often OK)"
else
    echo "  ⚠ No PostgreSQL backup found"
fi

echo ""
echo "[2/5] Restoring MinIO..."
if [ -d "$BACKUP_DIR/minio" ] && [ "$(ls -A "$BACKUP_DIR/minio" 2>/dev/null)" ]; then
    # Setup port-forward for MinIO
    MINIO_SVC=$(kubectl get svc -n $NAMESPACE -l app.kubernetes.io/name=minio -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
                kubectl get svc -n $NAMESPACE -l app=minio -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
                echo "minio")
    kubectl port-forward -n $NAMESPACE svc/$MINIO_SVC 9000:9000 &>/dev/null &
    PF_PID=$!
    sleep 3

    MINIO_ACCESS_KEY=$(kubectl get secret -n $NAMESPACE minio -o jsonpath='{.data.rootUser}' 2>/dev/null | base64 -d || \
                       kubectl get secret -n $NAMESPACE minio-secret -o jsonpath='{.data.MINIO_ACCESS_KEY}' 2>/dev/null | base64 -d || \
                       echo "minioadmin")
    MINIO_SECRET_KEY=$(kubectl get secret -n $NAMESPACE minio -o jsonpath='{.data.rootPassword}' 2>/dev/null | base64 -d || \
                       kubectl get secret -n $NAMESPACE minio-secret -o jsonpath='{.data.MINIO_SECRET_KEY}' 2>/dev/null | base64 -d || \
                       echo "staging_minio_2024")

    if command -v mc &>/dev/null; then
        mc alias set isa-restore http://localhost:9000 "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" --api S3v4 2>/dev/null || true
        mc mirror "$BACKUP_DIR/minio/" isa-restore/ 2>/dev/null && \
            echo "  ✓ MinIO restored" || \
            echo "  ⚠ MinIO restore failed"
    else
        echo "  ⚠ MinIO client (mc) not installed"
    fi

    kill $PF_PID 2>/dev/null || true
else
    echo "  ⚠ No MinIO backup found"
fi

echo ""
echo "[3/5] Restoring Qdrant..."
if [ -d "$BACKUP_DIR/qdrant" ] && [ "$(ls -A "$BACKUP_DIR/qdrant" 2>/dev/null)" ]; then
    QDRANT_SVC=$(kubectl get svc -n $NAMESPACE -l app.kubernetes.io/name=qdrant -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
                 kubectl get svc -n $NAMESPACE -l app=qdrant -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
                 echo "qdrant")
    kubectl port-forward -n $NAMESPACE svc/$QDRANT_SVC 6333:6333 &>/dev/null &
    PF_PID=$!
    sleep 2

    for snapshot_file in "$BACKUP_DIR/qdrant"/*.snapshot; do
        if [ -f "$snapshot_file" ]; then
            filename=$(basename "$snapshot_file")
            collection=$(echo "$filename" | cut -d'_' -f1)
            echo "  Restoring collection: $collection"
            curl -s -X POST "http://localhost:6333/collections/$collection/snapshots/upload" \
                -H "Content-Type: multipart/form-data" \
                -F "snapshot=@$snapshot_file" 2>/dev/null && \
                echo "  ✓ Collection '$collection' restored" || \
                echo "  ⚠ Failed to restore '$collection'"
        fi
    done

    kill $PF_PID 2>/dev/null || true
else
    echo "  ⚠ No Qdrant backup found"
fi

echo ""
echo "[4/5] Restoring Neo4j..."
if [ -f "$BACKUP_DIR/neo4j/neo4j.dump" ]; then
    NEO4J_POD=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=neo4j -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
                kubectl get pods -n $NAMESPACE -l app=neo4j -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
                echo "neo4j-0")

    kubectl cp "$BACKUP_DIR/neo4j/neo4j.dump" $NAMESPACE/$NEO4J_POD:/tmp/neo4j.dump

    # Stop neo4j, restore, start
    kubectl exec -n $NAMESPACE $NEO4J_POD -- neo4j stop 2>/dev/null || true
    sleep 2
    kubectl exec -n $NAMESPACE $NEO4J_POD -- neo4j-admin database load neo4j --from-path=/tmp/ --overwrite-destination=true 2>/dev/null && \
        echo "  ✓ Neo4j restored" || \
        echo "  ⚠ Neo4j restore failed"
    kubectl exec -n $NAMESPACE $NEO4J_POD -- neo4j start 2>/dev/null || true
else
    echo "  ⚠ No Neo4j backup found"
fi

echo ""
echo "[5/5] Restoring Redis..."
if [ -f "$BACKUP_DIR/redis/dump.rdb" ]; then
    REDIS_POD=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
                kubectl get pods -n $NAMESPACE -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
                echo "redis-master-0")

    # Get Redis password for auth
    REDIS_PASS=$(kubectl get secret -n $NAMESPACE redis -o jsonpath='{.data.redis-password}' 2>/dev/null | base64 -d || echo "staging_redis_2024")

    # Stop redis, copy RDB, restart
    kubectl exec -n $NAMESPACE $REDIS_POD -- redis-cli -a "$REDIS_PASS" SHUTDOWN NOSAVE 2>/dev/null || true
    sleep 2
    kubectl cp "$BACKUP_DIR/redis/dump.rdb" $NAMESPACE/$REDIS_POD:/data/dump.rdb 2>/dev/null
    # Redis will auto-restart via K8s
    echo "  ✓ Redis RDB copied (will load on restart)"
else
    echo "  ⚠ No Redis backup found"
fi

echo ""
echo "=============================================="
echo "Restore Complete"
echo "=============================================="
echo "Please verify your data and restart any affected services:"
echo "  kubectl rollout restart deployment -n $NAMESPACE"
echo "=============================================="
