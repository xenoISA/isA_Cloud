#!/bin/bash
# =============================================================================
# ISA Platform — Portable Backup Script
# =============================================================================
# Backs up all stateful services to a configurable target.
# Backup target is read from the provider profile or overridden via --target.
#
# Usage:
#   ./backup.sh                          # Backup all services
#   ./backup.sh --component postgres     # Backup single component
#   ./backup.sh --target /mnt/backups    # Override backup target
#   ./backup.sh --provider infotrend     # Use provider-specific backup target
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NAMESPACE="isa-cloud-production"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_TARGET="${BACKUP_TARGET:-/tmp/isa-backups}"
COMPONENT=""
PROVIDER=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --component) COMPONENT="$2"; shift 2 ;;
        --target)    BACKUP_TARGET="$2"; shift 2 ;;
        --provider)  PROVIDER="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--component <name>] [--target <path>] [--provider <name>]"
            echo "Components: postgres, redis, minio, nats, neo4j, consul, etcd"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Resolve backup target from provider profile if set
if [[ -n "$PROVIDER" ]]; then
    PROFILE_FILE="${SCRIPT_DIR}/../../profiles/${PROVIDER}.yaml"
    if [[ -f "$PROFILE_FILE" ]]; then
        PROFILE_TARGET=$(grep "^  backup_target:" "$PROFILE_FILE" 2>/dev/null | sed 's/^.*: *//' | tr -d '"' | tr -d "'" || echo "")
        if [[ -n "$PROFILE_TARGET" ]]; then
            BACKUP_TARGET="$PROFILE_TARGET"
        fi
    fi
fi

BACKUP_DIR="${BACKUP_TARGET}/${TIMESTAMP}"
mkdir -p "${BACKUP_DIR}"

log_info "Backup started at ${TIMESTAMP}"
log_info "Target: ${BACKUP_DIR}"

should_backup() {
    [[ -z "$COMPONENT" ]] || [[ "$COMPONENT" == "$1" ]]
}

# --- PostgreSQL ---
backup_postgres() {
    log_step "Backing up PostgreSQL..."

    local pg_pod=$(kubectl get pods -n ${NAMESPACE} \
        -l app.kubernetes.io/name=postgresql-ha,app.kubernetes.io/component=postgresql \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [[ -z "$pg_pod" ]]; then
        log_warn "PostgreSQL pod not found, skipping"
        return 0
    fi

    local dump_file="${BACKUP_DIR}/postgresql-${TIMESTAMP}.sql.gz"

    kubectl exec -n ${NAMESPACE} ${pg_pod} -- \
        pg_dumpall -U postgres 2>/dev/null | gzip > "${dump_file}"

    if [[ -s "$dump_file" ]]; then
        log_info "PostgreSQL backup: ${dump_file} ($(du -h "$dump_file" | cut -f1))"
    else
        log_error "PostgreSQL backup failed (empty dump)"
        rm -f "$dump_file"
        return 1
    fi
}

# --- Redis ---
backup_redis() {
    log_step "Backing up Redis..."

    local redis_pod=$(kubectl get pods -n ${NAMESPACE} \
        -l app.kubernetes.io/name=redis-cluster \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [[ -z "$redis_pod" ]]; then
        log_warn "Redis pod not found, skipping"
        return 0
    fi

    # Trigger BGSAVE and copy RDB
    kubectl exec -n ${NAMESPACE} ${redis_pod} -- redis-cli BGSAVE 2>/dev/null || true
    sleep 5  # Wait for BGSAVE to complete

    local rdb_file="${BACKUP_DIR}/redis-${TIMESTAMP}.rdb"
    kubectl cp "${NAMESPACE}/${redis_pod}:/data/dump.rdb" "${rdb_file}" 2>/dev/null || {
        log_warn "Redis RDB copy failed (AOF-only mode?)"
        return 0
    }

    if [[ -s "$rdb_file" ]]; then
        log_info "Redis backup: ${rdb_file} ($(du -h "$rdb_file" | cut -f1))"
    else
        log_warn "Redis backup empty"
        rm -f "$rdb_file"
    fi
}

# --- MinIO ---
backup_minio() {
    log_step "Backing up MinIO..."

    if ! command -v mc &>/dev/null; then
        log_warn "MinIO client (mc) not found, skipping MinIO backup"
        log_warn "Install: brew install minio/stable/mc"
        return 0
    fi

    local minio_dir="${BACKUP_DIR}/minio"
    mkdir -p "${minio_dir}"

    # Configure mc alias if not exists
    local minio_svc="http://localhost:9000"
    log_info "Ensure port-forward to MinIO is active (kubectl port-forward svc/minio 9000:9000 -n ${NAMESPACE})"

    # Mirror all buckets
    for bucket in isa-data isa-backups isa-logs isa-models; do
        mc mirror "isa-prod/${bucket}" "${minio_dir}/${bucket}" 2>/dev/null && \
            log_info "MinIO bucket '${bucket}' backed up" || \
            log_warn "MinIO bucket '${bucket}' backup failed (may not exist)"
    done
}

# --- NATS JetStream ---
backup_nats() {
    log_step "Backing up NATS JetStream..."

    local nats_pod=$(kubectl get pods -n ${NAMESPACE} \
        -l app.kubernetes.io/name=nats \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [[ -z "$nats_pod" ]]; then
        log_warn "NATS pod not found, skipping"
        return 0
    fi

    local nats_dir="${BACKUP_DIR}/nats"
    mkdir -p "${nats_dir}"

    # Export stream configs
    kubectl exec -n ${NAMESPACE} ${nats_pod} -- \
        nats stream ls --json 2>/dev/null > "${nats_dir}/streams.json" || {
        log_warn "NATS stream list failed"
        return 0
    }

    # Export consumer configs per stream
    for stream in $(kubectl exec -n ${NAMESPACE} ${nats_pod} -- nats stream ls --names 2>/dev/null); do
        kubectl exec -n ${NAMESPACE} ${nats_pod} -- \
            nats stream info "${stream}" --json 2>/dev/null > "${nats_dir}/stream-${stream}.json" || true
        kubectl exec -n ${NAMESPACE} ${nats_pod} -- \
            nats consumer ls "${stream}" --json 2>/dev/null > "${nats_dir}/consumers-${stream}.json" || true
    done

    log_info "NATS JetStream config backed up to ${nats_dir}"
}

# --- Neo4j ---
backup_neo4j() {
    log_step "Backing up Neo4j..."

    local neo4j_pod=$(kubectl get pods -n ${NAMESPACE} \
        -l app=neo4j \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [[ -z "$neo4j_pod" ]]; then
        log_warn "Neo4j pod not found, skipping"
        return 0
    fi

    local dump_file="${BACKUP_DIR}/neo4j-${TIMESTAMP}.dump"

    kubectl exec -n ${NAMESPACE} ${neo4j_pod} -- \
        neo4j-admin database dump --to-path=/tmp neo4j 2>/dev/null && \
    kubectl cp "${NAMESPACE}/${neo4j_pod}:/tmp/neo4j.dump" "${dump_file}" 2>/dev/null || {
        log_warn "Neo4j dump failed (may require stopping the database)"
        return 0
    }

    if [[ -s "$dump_file" ]]; then
        log_info "Neo4j backup: ${dump_file} ($(du -h "$dump_file" | cut -f1))"
    else
        log_warn "Neo4j backup empty"
        rm -f "$dump_file"
    fi
}

# --- Consul ---
backup_consul() {
    log_step "Backing up Consul..."

    local consul_pod=$(kubectl get pods -n ${NAMESPACE} \
        -l app=consul,component=server \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [[ -z "$consul_pod" ]]; then
        log_warn "Consul pod not found, skipping"
        return 0
    fi

    local snap_file="${BACKUP_DIR}/consul-${TIMESTAMP}.snap"

    kubectl exec -n ${NAMESPACE} ${consul_pod} -- \
        consul snapshot save /tmp/consul-backup.snap 2>/dev/null && \
    kubectl cp "${NAMESPACE}/${consul_pod}:/tmp/consul-backup.snap" "${snap_file}" 2>/dev/null || {
        log_warn "Consul snapshot failed"
        return 0
    }

    if [[ -s "$snap_file" ]]; then
        log_info "Consul backup: ${snap_file} ($(du -h "$snap_file" | cut -f1))"
    else
        log_warn "Consul backup empty"
        rm -f "$snap_file"
    fi
}

# --- etcd ---
backup_etcd() {
    log_step "Backing up etcd..."

    local etcd_pod=$(kubectl get pods -n ${NAMESPACE} \
        -l app=etcd \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [[ -z "$etcd_pod" ]]; then
        log_warn "etcd pod not found, skipping"
        return 0
    fi

    local snap_file="${BACKUP_DIR}/etcd-${TIMESTAMP}.snap"

    kubectl exec -n ${NAMESPACE} ${etcd_pod} -- \
        etcdctl snapshot save /tmp/etcd-backup.snap 2>/dev/null && \
    kubectl cp "${NAMESPACE}/${etcd_pod}:/tmp/etcd-backup.snap" "${snap_file}" 2>/dev/null || {
        log_warn "etcd snapshot failed"
        return 0
    }

    if [[ -s "$snap_file" ]]; then
        log_info "etcd backup: ${snap_file} ($(du -h "$snap_file" | cut -f1))"
    else
        log_warn "etcd backup empty"
        rm -f "$snap_file"
    fi
}

# --- Run backups ---
should_backup "postgres" && backup_postgres
should_backup "redis"    && backup_redis
should_backup "minio"    && backup_minio
should_backup "nats"     && backup_nats
should_backup "neo4j"    && backup_neo4j
should_backup "consul"   && backup_consul
should_backup "etcd"     && backup_etcd

# --- Summary ---
echo ""
log_info "=============================================="
log_info " Backup complete: ${BACKUP_DIR}"
log_info " Total size: $(du -sh "${BACKUP_DIR}" | cut -f1)"
log_info "=============================================="

# Write manifest
cat > "${BACKUP_DIR}/MANIFEST.txt" <<MANIFEST
ISA Platform Backup
Timestamp: ${TIMESTAMP}
Provider: ${PROVIDER:-generic}
Namespace: ${NAMESPACE}

Contents:
$(ls -la "${BACKUP_DIR}/" | tail -n +2)
MANIFEST

log_info "Manifest written to ${BACKUP_DIR}/MANIFEST.txt"
