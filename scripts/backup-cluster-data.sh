#!/bin/bash
# =============================================================================
# Backup Script for Kind Cluster Data
# =============================================================================
# This script backs up all critical data before cluster recreation
# Run this BEFORE deleting the Kind cluster
#
# Usage:
#   ./backup-cluster-data.sh                    # Backup to default location
#   ./backup-cluster-data.sh /path/to/backup    # Backup to custom location
#   KIND_CLUSTER=isa-cloud-staging ./backup-cluster-data.sh  # Specify cluster
# =============================================================================

set -e

# Default backup location: isA_Cloud/backups/cluster-backup-TIMESTAMP
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISA_CLOUD_DIR="$(dirname "$SCRIPT_DIR")"
DEFAULT_BACKUP_DIR="$ISA_CLOUD_DIR/backups/cluster-backup-$(date +%Y%m%d_%H%M%S)"

BACKUP_DIR="${1:-$DEFAULT_BACKUP_DIR}"
NAMESPACE="${NAMESPACE:-isa-cloud-staging}"
CLUSTER_NAME="${KIND_CLUSTER:-isa-cloud-local}"

echo "=============================================="
echo "ISA Cloud Cluster Backup"
echo "=============================================="
echo "Backup directory: $BACKUP_DIR"
echo ""

mkdir -p "$BACKUP_DIR"/{postgres,minio,qdrant,neo4j,redis}

# Check cluster connectivity
if ! kubectl cluster-info &>/dev/null; then
    echo "ERROR: Cannot connect to Kubernetes cluster"
    exit 1
fi

echo "[1/5] Backing up PostgreSQL..."
# Get postgres pod (supports both Bitnami helm chart and custom deployments)
PG_POD=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
         kubectl get pods -n $NAMESPACE -l app=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
         kubectl get pods -n $NAMESPACE -l app=postgres -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
         echo "postgresql-0")

if kubectl get pod -n $NAMESPACE $PG_POD &>/dev/null; then
    # Dump all databases
    kubectl exec -n $NAMESPACE $PG_POD -- pg_dumpall -U postgres > "$BACKUP_DIR/postgres/full_backup.sql" 2>/dev/null && \
        echo "  ✓ PostgreSQL backup complete ($(du -h "$BACKUP_DIR/postgres/full_backup.sql" | cut -f1))" || \
        echo "  ✗ PostgreSQL backup failed"

    # Also dump individual databases for easier selective restore
    for db in $(kubectl exec -n $NAMESPACE $PG_POD -- psql -U postgres -t -c "SELECT datname FROM pg_database WHERE datistemplate = false AND datname != 'postgres';" 2>/dev/null | tr -d ' '); do
        if [ -n "$db" ]; then
            kubectl exec -n $NAMESPACE $PG_POD -- pg_dump -U postgres -Fc "$db" > "$BACKUP_DIR/postgres/${db}.dump" 2>/dev/null && \
                echo "  ✓ Database '$db' backed up" || true
        fi
    done
else
    echo "  ⚠ PostgreSQL pod not found"
fi

echo ""
echo "[2/5] Backing up MinIO..."
# Setup port-forward for MinIO (try different service names)
MINIO_SVC=$(kubectl get svc -n $NAMESPACE -l app.kubernetes.io/name=minio -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
            kubectl get svc -n $NAMESPACE -l app=minio -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
            echo "minio")
kubectl port-forward -n $NAMESPACE svc/$MINIO_SVC 9000:9000 &>/dev/null &
PF_PID=$!
sleep 2

# Get MinIO credentials (try different secret naming conventions)
MINIO_ACCESS_KEY=$(kubectl get secret -n $NAMESPACE minio -o jsonpath='{.data.rootUser}' 2>/dev/null | base64 -d || \
                   kubectl get secret -n $NAMESPACE minio-secret -o jsonpath='{.data.MINIO_ACCESS_KEY}' 2>/dev/null | base64 -d || \
                   echo "minioadmin")
MINIO_SECRET_KEY=$(kubectl get secret -n $NAMESPACE minio -o jsonpath='{.data.rootPassword}' 2>/dev/null | base64 -d || \
                   kubectl get secret -n $NAMESPACE minio-secret -o jsonpath='{.data.MINIO_SECRET_KEY}' 2>/dev/null | base64 -d || \
                   echo "staging_minio_2024")

# Use mc (MinIO client) if available
if command -v mc &>/dev/null; then
    mc alias set isa-backup http://localhost:9000 "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" --api S3v4 2>/dev/null || true
    mc mirror isa-backup/ "$BACKUP_DIR/minio/" 2>/dev/null && \
        echo "  ✓ MinIO backup complete" || \
        echo "  ⚠ MinIO backup failed (mc mirror)"
else
    echo "  ⚠ MinIO client (mc) not installed. Skipping MinIO backup."
    echo "    Install with: brew install minio/stable/mc"
fi

kill $PF_PID 2>/dev/null || true

echo ""
echo "[3/5] Backing up Qdrant..."
# Setup port-forward for Qdrant
QDRANT_SVC=$(kubectl get svc -n $NAMESPACE -l app.kubernetes.io/name=qdrant -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
             kubectl get svc -n $NAMESPACE -l app=qdrant -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
             echo "qdrant")
kubectl port-forward -n $NAMESPACE svc/$QDRANT_SVC 6333:6333 &>/dev/null &
PF_PID=$!
sleep 2

# Create snapshots for all collections
COLLECTIONS=$(curl -s http://localhost:6333/collections 2>/dev/null | jq -r '.result.collections[].name' 2>/dev/null || echo "")
if [ -n "$COLLECTIONS" ]; then
    for collection in $COLLECTIONS; do
        echo "  Creating snapshot for collection: $collection"
        SNAPSHOT=$(curl -s -X POST "http://localhost:6333/collections/$collection/snapshots" 2>/dev/null | jq -r '.result.name' 2>/dev/null || echo "")
        if [ -n "$SNAPSHOT" ] && [ "$SNAPSHOT" != "null" ]; then
            curl -s "http://localhost:6333/collections/$collection/snapshots/$SNAPSHOT" -o "$BACKUP_DIR/qdrant/${collection}_${SNAPSHOT}.snapshot" 2>/dev/null && \
                echo "  ✓ Collection '$collection' backed up" || true
        fi
    done
else
    echo "  ⚠ No Qdrant collections found or Qdrant not accessible"
fi

kill $PF_PID 2>/dev/null || true

echo ""
echo "[4/5] Backing up Neo4j..."
NEO4J_POD=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=neo4j -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
            kubectl get pods -n $NAMESPACE -l app=neo4j -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
            echo "neo4j-0")

if kubectl get pod -n $NAMESPACE $NEO4J_POD &>/dev/null; then
    # Create Neo4j dump
    kubectl exec -n $NAMESPACE $NEO4J_POD -- neo4j-admin database dump neo4j --to-path=/tmp/ 2>/dev/null && \
        kubectl cp $NAMESPACE/$NEO4J_POD:/tmp/neo4j.dump "$BACKUP_DIR/neo4j/neo4j.dump" 2>/dev/null && \
        echo "  ✓ Neo4j backup complete" || \
        echo "  ⚠ Neo4j backup failed (may need to stop database first)"
else
    echo "  ⚠ Neo4j pod not found"
fi

echo ""
echo "[5/5] Backing up Redis (RDB snapshot)..."
REDIS_POD=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
            kubectl get pods -n $NAMESPACE -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || \
            echo "redis-master-0")

if kubectl get pod -n $NAMESPACE $REDIS_POD &>/dev/null; then
    # Get Redis password for auth
    REDIS_PASS=$(kubectl get secret -n $NAMESPACE redis -o jsonpath='{.data.redis-password}' 2>/dev/null | base64 -d || echo "staging_redis_2024")

    # Trigger BGSAVE and copy RDB file
    kubectl exec -n $NAMESPACE $REDIS_POD -- redis-cli -a "$REDIS_PASS" BGSAVE 2>/dev/null || true
    sleep 2
    kubectl cp $NAMESPACE/$REDIS_POD:/data/dump.rdb "$BACKUP_DIR/redis/dump.rdb" 2>/dev/null && \
        echo "  ✓ Redis backup complete" || \
        echo "  ⚠ Redis backup failed"
else
    echo "  ⚠ Redis pod not found"
fi

echo ""
echo "=============================================="
echo "Backup Summary"
echo "=============================================="
echo "Location: $BACKUP_DIR"
echo ""
du -sh "$BACKUP_DIR"/* 2>/dev/null || true
echo ""
echo "Total size: $(du -sh "$BACKUP_DIR" | cut -f1)"
echo ""
echo "Next steps:"
echo "  1. Verify backups are complete"
echo "  2. Delete Kind cluster: kind delete cluster --name $CLUSTER_NAME"
echo "  3. Recreate cluster: kind create cluster --config deployments/kubernetes/local/kind-config.yaml"
echo "  4. Deploy infrastructure with local values (see deployments/README.md)"
echo "  5. Restore data: ./scripts/restore-cluster-data.sh $BACKUP_DIR"
echo "=============================================="
