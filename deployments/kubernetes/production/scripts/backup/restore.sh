#!/bin/bash
# =============================================================================
# ISA Platform — Portable Restore Script
# =============================================================================
# Restores stateful services from a backup directory.
#
# Usage:
#   ./restore.sh /path/to/backup/20260410-120000
#   ./restore.sh /path/to/backup/20260410-120000 --component postgres
#   ./restore.sh /path/to/backup/20260410-120000 --dry-run
# =============================================================================

set -e

NAMESPACE="isa-cloud-production"
BACKUP_DIR="${1:-}"
COMPONENT=""
DRY_RUN=false

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

if [[ -z "$BACKUP_DIR" ]]; then
    echo "Usage: $0 <backup-directory> [--component <name>] [--dry-run]"
    exit 1
fi

if [[ ! -d "$BACKUP_DIR" ]]; then
    log_error "Backup directory not found: ${BACKUP_DIR}"
    exit 1
fi

shift  # Remove backup dir from args
while [[ $# -gt 0 ]]; do
    case $1 in
        --component) COMPONENT="$2"; shift 2 ;;
        --dry-run)   DRY_RUN=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

log_info "Restore from: ${BACKUP_DIR}"
log_info "Dry run: ${DRY_RUN}"

if [[ -f "${BACKUP_DIR}/MANIFEST.txt" ]]; then
    echo ""
    cat "${BACKUP_DIR}/MANIFEST.txt"
    echo ""
fi

should_restore() {
    [[ -z "$COMPONENT" ]] || [[ "$COMPONENT" == "$1" ]]
}

confirm() {
    if [[ "$DRY_RUN" == true ]]; then
        log_info "[DRY RUN] Would: $1"
        return 1
    fi
    echo -e "${YELLOW}[CONFIRM]${NC} $1"
    read -p "Type 'yes' to continue: " response
    [[ "$response" == "yes" ]]
}

# --- PostgreSQL ---
restore_postgres() {
    local dump_file=$(ls "${BACKUP_DIR}"/postgresql-*.sql.gz 2>/dev/null | head -1)
    if [[ -z "$dump_file" ]]; then
        log_warn "No PostgreSQL backup found, skipping"
        return 0
    fi

    log_step "Restoring PostgreSQL from ${dump_file}..."
    confirm "This will overwrite the PostgreSQL database. Continue?" || return 0

    local pg_pod=$(kubectl get pods -n ${NAMESPACE} \
        -l app.kubernetes.io/name=postgresql-ha,app.kubernetes.io/component=postgresql \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [[ -z "$pg_pod" ]]; then
        log_error "PostgreSQL pod not found"
        return 1
    fi

    gunzip -c "${dump_file}" | kubectl exec -i -n ${NAMESPACE} ${pg_pod} -- \
        psql -U postgres 2>/dev/null

    log_info "PostgreSQL restored"
}

# --- Redis ---
restore_redis() {
    local rdb_file=$(ls "${BACKUP_DIR}"/redis-*.rdb 2>/dev/null | head -1)
    if [[ -z "$rdb_file" ]]; then
        log_warn "No Redis backup found, skipping"
        return 0
    fi

    log_step "Restoring Redis from ${rdb_file}..."
    confirm "This will stop Redis, replace the RDB file, and restart. Continue?" || return 0

    local redis_pod=$(kubectl get pods -n ${NAMESPACE} \
        -l app.kubernetes.io/name=redis-cluster \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [[ -z "$redis_pod" ]]; then
        log_error "Redis pod not found"
        return 1
    fi

    kubectl cp "${rdb_file}" "${NAMESPACE}/${redis_pod}:/data/dump.rdb" 2>/dev/null
    kubectl exec -n ${NAMESPACE} ${redis_pod} -- redis-cli DEBUG RELOAD 2>/dev/null || {
        log_warn "Redis DEBUG RELOAD failed — may need pod restart"
    }

    log_info "Redis restored"
}

# --- Consul ---
restore_consul() {
    local snap_file=$(ls "${BACKUP_DIR}"/consul-*.snap 2>/dev/null | head -1)
    if [[ -z "$snap_file" ]]; then
        log_warn "No Consul backup found, skipping"
        return 0
    fi

    log_step "Restoring Consul from ${snap_file}..."
    confirm "This will restore the Consul snapshot. Continue?" || return 0

    local consul_pod=$(kubectl get pods -n ${NAMESPACE} \
        -l app=consul,component=server \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [[ -z "$consul_pod" ]]; then
        log_error "Consul pod not found"
        return 1
    fi

    kubectl cp "${snap_file}" "${NAMESPACE}/${consul_pod}:/tmp/consul-restore.snap" 2>/dev/null
    kubectl exec -n ${NAMESPACE} ${consul_pod} -- \
        consul snapshot restore /tmp/consul-restore.snap 2>/dev/null

    log_info "Consul restored"
}

# --- etcd ---
restore_etcd() {
    local snap_file=$(ls "${BACKUP_DIR}"/etcd-*.snap 2>/dev/null | head -1)
    if [[ -z "$snap_file" ]]; then
        log_warn "No etcd backup found, skipping"
        return 0
    fi

    log_step "Restoring etcd from ${snap_file}..."
    confirm "This will restore etcd from snapshot. This requires restarting the etcd cluster. Continue?" || return 0

    log_warn "etcd restore requires manual steps:"
    echo "  1. Stop all etcd pods: kubectl scale statefulset etcd --replicas=0 -n ${NAMESPACE}"
    echo "  2. Copy snapshot to each etcd PV"
    echo "  3. Run: etcdctl snapshot restore <snapshot> --data-dir=/etcd-data"
    echo "  4. Restart: kubectl scale statefulset etcd --replicas=3 -n ${NAMESPACE}"
    echo ""
    echo "  Snapshot file: ${snap_file}"
}

# --- NATS ---
restore_nats() {
    local nats_dir="${BACKUP_DIR}/nats"
    if [[ ! -d "$nats_dir" ]]; then
        log_warn "No NATS backup found, skipping"
        return 0
    fi

    log_step "Restoring NATS JetStream config..."
    confirm "This will recreate NATS streams and consumers. Continue?" || return 0

    log_warn "NATS JetStream restore requires manual steps:"
    echo "  Stream configs are in: ${nats_dir}/stream-*.json"
    echo "  Consumer configs are in: ${nats_dir}/consumers-*.json"
    echo ""
    echo "  To restore streams:"
    echo "    nats stream add <name> --config <stream-file>.json"
    echo "  To restore consumers:"
    echo "    nats consumer add <stream> <name> --config <consumer-file>.json"
}

# --- Run restores ---
should_restore "postgres" && restore_postgres
should_restore "redis"    && restore_redis
should_restore "consul"   && restore_consul
should_restore "etcd"     && restore_etcd
should_restore "nats"     && restore_nats

echo ""
log_info "Restore process complete."
log_info "Run health-check.sh to verify the platform state."
