#!/bin/bash
# Production Infrastructure Backup Script
# Usage: ./backup.sh [all|component-name] [--restore backup-name]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="isa-cloud-production"
BACKUP_DIR="${BACKUP_DIR:-/tmp/isa-backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
S3_BUCKET="${S3_BUCKET:-isa-backups}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Create backup directory
mkdir -p "$BACKUP_DIR/$TIMESTAMP"

# Backup PostgreSQL
backup_postgresql() {
    log_info "Backing up PostgreSQL..."

    local backup_file="$BACKUP_DIR/$TIMESTAMP/postgresql_$TIMESTAMP.sql.gz"

    # Get primary pod
    local primary_pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=postgresql-ha,app.kubernetes.io/component=postgresql \
        -o jsonpath='{.items[0].metadata.name}')

    if [[ -z "$primary_pod" ]]; then
        log_error "PostgreSQL primary pod not found"
        return 1
    fi

    # Execute pg_dumpall
    kubectl exec -n "$NAMESPACE" "$primary_pod" -- \
        pg_dumpall -U postgres | gzip > "$backup_file"

    log_success "PostgreSQL backup: $backup_file"
}

# Backup Redis
backup_redis() {
    log_info "Backing up Redis (RDB snapshot)..."

    local backup_file="$BACKUP_DIR/$TIMESTAMP/redis_$TIMESTAMP.rdb"

    # Get any redis pod
    local redis_pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=redis-cluster \
        -o jsonpath='{.items[0].metadata.name}')

    if [[ -z "$redis_pod" ]]; then
        log_error "Redis pod not found"
        return 1
    fi

    # Trigger BGSAVE and copy RDB file
    kubectl exec -n "$NAMESPACE" "$redis_pod" -- redis-cli BGSAVE
    sleep 5
    kubectl cp "$NAMESPACE/$redis_pod:/data/dump.rdb" "$backup_file"

    log_success "Redis backup: $backup_file"
}

# Backup Qdrant
backup_qdrant() {
    log_info "Backing up Qdrant snapshots..."

    local backup_dir="$BACKUP_DIR/$TIMESTAMP/qdrant"
    mkdir -p "$backup_dir"

    # Get Qdrant pods
    local pods=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=qdrant \
        -o jsonpath='{.items[*].metadata.name}')

    for pod in $pods; do
        log_info "Creating snapshot on $pod..."

        # Trigger snapshot creation via API
        kubectl exec -n "$NAMESPACE" "$pod" -- \
            curl -s -X POST "http://localhost:6333/snapshots"

        sleep 3

        # List and copy snapshots
        kubectl exec -n "$NAMESPACE" "$pod" -- \
            ls /qdrant/snapshots/ 2>/dev/null | while read snapshot; do
            kubectl cp "$NAMESPACE/$pod:/qdrant/snapshots/$snapshot" "$backup_dir/${pod}_${snapshot}"
        done
    done

    log_success "Qdrant backup: $backup_dir"
}

# Backup Neo4j
backup_neo4j() {
    log_info "Backing up Neo4j..."

    local backup_file="$BACKUP_DIR/$TIMESTAMP/neo4j_$TIMESTAMP.dump"

    # Get Neo4j pod
    local neo4j_pod=$(kubectl get pods -n "$NAMESPACE" -l app=neo4j \
        -o jsonpath='{.items[0].metadata.name}')

    if [[ -z "$neo4j_pod" ]]; then
        log_error "Neo4j pod not found"
        return 1
    fi

    # Create backup using neo4j-admin
    kubectl exec -n "$NAMESPACE" "$neo4j_pod" -- \
        neo4j-admin database dump --to-path=/tmp neo4j

    kubectl cp "$NAMESPACE/$neo4j_pod:/tmp/neo4j.dump" "$backup_file"

    log_success "Neo4j backup: $backup_file"
}

# Backup NATS JetStream
backup_nats() {
    log_info "Backing up NATS JetStream streams..."

    local backup_dir="$BACKUP_DIR/$TIMESTAMP/nats"
    mkdir -p "$backup_dir"

    # Get NATS box pod for admin commands
    local nats_box=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=nats-box \
        -o jsonpath='{.items[0].metadata.name}')

    if [[ -z "$nats_box" ]]; then
        log_warn "NATS box not found, skipping stream backup"
        return 0
    fi

    # Export stream configurations
    kubectl exec -n "$NAMESPACE" "$nats_box" -- \
        nats stream ls -j > "$backup_dir/streams.json"

    # Export consumer configurations
    kubectl exec -n "$NAMESPACE" "$nats_box" -- \
        nats consumer ls -j '*' > "$backup_dir/consumers.json"

    log_success "NATS backup: $backup_dir"
}

# Backup MinIO (list buckets and policies)
backup_minio() {
    log_info "Backing up MinIO metadata..."

    local backup_dir="$BACKUP_DIR/$TIMESTAMP/minio"
    mkdir -p "$backup_dir"

    # Get MinIO pod
    local minio_pod=$(kubectl get pods -n "$NAMESPACE" -l app=minio \
        -o jsonpath='{.items[0].metadata.name}')

    if [[ -z "$minio_pod" ]]; then
        log_error "MinIO pod not found"
        return 1
    fi

    # Export bucket list and policies
    kubectl exec -n "$NAMESPACE" "$minio_pod" -- \
        mc alias set local http://localhost:9000 \$MINIO_ROOT_USER \$MINIO_ROOT_PASSWORD

    kubectl exec -n "$NAMESPACE" "$minio_pod" -- \
        mc ls local --json > "$backup_dir/buckets.json"

    log_success "MinIO metadata backup: $backup_dir"
    log_warn "For full MinIO data backup, use mc mirror to external storage"
}

# Upload backups to S3/MinIO
upload_backups() {
    log_info "Uploading backups to $S3_BUCKET..."

    if command -v aws &> /dev/null; then
        aws s3 sync "$BACKUP_DIR/$TIMESTAMP" "s3://$S3_BUCKET/$TIMESTAMP/" \
            --endpoint-url "$MINIO_ENDPOINT"
        log_success "Backups uploaded to s3://$S3_BUCKET/$TIMESTAMP/"
    else
        log_warn "AWS CLI not found, skipping S3 upload"
    fi
}

# Backup all components
backup_all() {
    log_info "Starting full backup at $TIMESTAMP"

    backup_postgresql || log_warn "PostgreSQL backup failed"
    backup_redis || log_warn "Redis backup failed"
    backup_qdrant || log_warn "Qdrant backup failed"
    backup_neo4j || log_warn "Neo4j backup failed"
    backup_nats || log_warn "NATS backup failed"
    backup_minio || log_warn "MinIO backup failed"

    # Create manifest
    cat > "$BACKUP_DIR/$TIMESTAMP/manifest.json" << EOF
{
    "timestamp": "$TIMESTAMP",
    "namespace": "$NAMESPACE",
    "components": ["postgresql", "redis", "qdrant", "neo4j", "nats", "minio"],
    "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

    upload_backups

    log_success "Full backup completed: $BACKUP_DIR/$TIMESTAMP"
}

# List available backups
list_backups() {
    log_info "Available backups in $BACKUP_DIR:"
    ls -la "$BACKUP_DIR"
}

# Main entry point
main() {
    COMPONENT="${1:-all}"

    case "$COMPONENT" in
        all)
            backup_all
            ;;
        postgresql|postgres|pg)
            backup_postgresql
            ;;
        redis)
            backup_redis
            ;;
        qdrant)
            backup_qdrant
            ;;
        neo4j)
            backup_neo4j
            ;;
        nats)
            backup_nats
            ;;
        minio)
            backup_minio
            ;;
        list)
            list_backups
            ;;
        *)
            log_error "Unknown component: $COMPONENT"
            echo "Usage: $0 [all|postgresql|redis|qdrant|neo4j|nats|minio|list]"
            exit 1
            ;;
    esac
}

main "$@"
