#!/usr/bin/env bash
# =============================================================================
# bootstrap-vault-secrets.sh — populate vault with the 5 isa-bigdata secrets
# =============================================================================
# Tracking: xenoISA/isA_Cloud#234 (parent epic), companion to
# deployments/cluster-prereqs/external-secrets/ (the 5 ExternalSecret
# CRs + 1 ClusterSecretStore).
#
# Writes 5 secrets at the canonical vault paths the ExternalSecret CRs
# read from. Each value is randomly generated on first run; subsequent
# runs read existing values back unless --rotate is passed.
#
# Vault auth: standard $VAULT_ADDR + $VAULT_TOKEN env vars. The token
# needs `create + update + read` on `secret/data/isa-bigdata/*`.
#
# Usage:
#   ./bootstrap-vault-secrets.sh                    # idempotent: skip existing
#   ./bootstrap-vault-secrets.sh --rotate-all       # regenerate ALL passwords
#   ./bootstrap-vault-secrets.sh --rotate=minio-credentials   # rotate one
#   ./bootstrap-vault-secrets.sh --backup-file /path/to/secrets.txt
#                                                   # write a sealed copy locally
#   ./bootstrap-vault-secrets.sh --dry-run          # print what would write
#
# Requires the `vault` CLI on PATH.
# =============================================================================

set -euo pipefail

VAULT_KV_PATH_PREFIX="${VAULT_KV_PATH_PREFIX:-secret/isa-bigdata}"
DRY_RUN=false
ROTATE=""
ROTATE_ALL=false
BACKUP_FILE=""

# -----------------------------------------------------------------------------
# Output
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { printf '%b[bootstrap-vault]%b %s\n'  "${BLUE}"   "${NC}" "$*"; }
ok()   { printf '%b[bootstrap-vault]%b %s\n'  "${GREEN}"  "${NC}" "$*"; }
warn() { printf '%b[bootstrap-vault]%b %s\n'  "${YELLOW}" "${NC}" "$*" >&2; }
die()  { printf '%b[bootstrap-vault]%b %s\n'  "${RED}"    "${NC}" "$*" >&2; exit 1; }

usage() {
  sed -n '1,30p' "${BASH_SOURCE[0]}" | grep -E '^#' | sed 's/^# \?//'
  exit 0
}

# -----------------------------------------------------------------------------
# Argument parsing
# -----------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rotate-all)  ROTATE_ALL=true; shift ;;
    --rotate=*)    ROTATE="${1#*=}"; shift ;;
    --backup-file) BACKUP_FILE="$2"; shift 2 ;;
    --dry-run)     DRY_RUN=true; shift ;;
    -h|--help)     usage ;;
    *)             die "Unknown argument: $1 (try --help)" ;;
  esac
done

# -----------------------------------------------------------------------------
# Pre-flight
# -----------------------------------------------------------------------------
command -v vault   >/dev/null 2>&1 || die "vault CLI not on PATH (https://developer.hashicorp.com/vault/install)"
command -v openssl >/dev/null 2>&1 || die "openssl not on PATH"

if [[ -z "${VAULT_ADDR:-}" ]]; then
  die "VAULT_ADDR not set (e.g. export VAULT_ADDR=http://vault.vault.svc.cluster.local:8200)"
fi
if [[ -z "${VAULT_TOKEN:-}" ]]; then
  die "VAULT_TOKEN not set (login via 'vault login' or set the env var)"
fi

if ! vault status >/dev/null 2>&1; then
  warn "vault status returned non-zero (sealed? unreachable?). Continuing..."
fi

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
gen_password() {
  openssl rand -base64 36 | tr -d '\n=+/' | head -c 32
}

vault_kv_path_for() {
  printf '%s/%s' "${VAULT_KV_PATH_PREFIX}" "$1"
}

vault_kv_get_field() {
  local path="$1"
  local key="$2"
  vault kv get -field="${key}" "$(vault_kv_path_for "${path}")" 2>/dev/null || true
}

vault_kv_put() {
  local path="$1"; shift
  if [[ "${DRY_RUN}" == "true" ]]; then
    log "  [dry-run] vault kv put $(vault_kv_path_for "${path}") <values>"
    return
  fi
  vault kv put "$(vault_kv_path_for "${path}")" "$@" >/dev/null
}

should_rotate() {
  local name="$1"
  if [[ "${ROTATE_ALL}" == "true" ]]; then return 0; fi
  if [[ -n "${ROTATE}" && "${ROTATE}" == "${name}" ]]; then return 0; fi
  return 1
}

append_backup() {
  local name="$1"; shift
  if [[ -z "${BACKUP_FILE}" || "${DRY_RUN}" == "true" ]]; then return; fi
  {
    printf '# %s — %s\n' "${name}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    while [[ $# -gt 0 ]]; do
      printf '%s/%s/%s: %s\n' "${VAULT_KV_PATH_PREFIX}" "${name}" "$1" "$2"
      shift 2
    done
    echo ""
  } >> "${BACKUP_FILE}"
}

ensure_secret() {
  # ensure_secret <name> <key1> <key2> ...
  local name="$1"; shift
  local keys=("$@")

  local existing_value
  local missing=false
  local rotate=false

  if should_rotate "${name}"; then
    rotate=true
    log "rotating: ${name}"
  fi

  declare -A values=()
  for key in "${keys[@]}"; do
    existing_value=$(vault_kv_get_field "${name}" "${key}")
    if [[ -z "${existing_value}" || "${rotate}" == "true" ]]; then
      values["${key}"]=$(gen_password)
      missing=true
    else
      values["${key}"]="${existing_value}"
    fi
  done

  if [[ "${missing}" == "false" && "${rotate}" == "false" ]]; then
    ok "  ${name}: all keys present, skip"
    return
  fi

  local kv_args=()
  local backup_args=()
  for key in "${keys[@]}"; do
    kv_args+=("${key}=${values[${key}]}")
    backup_args+=("${key}" "${values[${key}]}")
  done

  vault_kv_put "${name}" "${kv_args[@]}"
  ok "  ${name}: wrote ${#keys[@]} keys (${keys[*]})"
  append_backup "${name}" "${backup_args[@]}"
}

# minio-credentials needs (rootUser == access-key) and (rootPassword == secret-key).
# Custom logic so we generate 2 values and write 4 keys aligned.
ensure_minio_credentials() {
  local name=minio-credentials
  local rotate=false
  if should_rotate "${name}"; then
    rotate=true
    log "rotating: ${name}"
  fi

  local access=$(vault_kv_get_field "${name}" access-key)
  local secret=$(vault_kv_get_field "${name}" secret-key)

  if [[ -z "${access}" || "${rotate}" == "true" ]]; then access=$(gen_password); fi
  if [[ -z "${secret}" || "${rotate}" == "true" ]]; then secret=$(gen_password); fi

  if [[ "${DRY_RUN}" == "true" ]]; then
    log "  [dry-run] vault kv put $(vault_kv_path_for "${name}") <4 keys>"
  else
    vault kv put "$(vault_kv_path_for "${name}")" \
      "access-key=${access}" \
      "secret-key=${secret}" \
      "rootUser=${access}" \
      "rootPassword=${secret}" >/dev/null
  fi
  ok "  ${name}: access-key/secret-key + rootUser/rootPassword aligned"
  append_backup "${name}" \
    access-key "${access}" \
    secret-key "${secret}" \
    rootUser "${access}" \
    rootPassword "${secret}"
}

# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
log "Vault: ${VAULT_ADDR}"
log "Path prefix: ${VAULT_KV_PATH_PREFIX}/<secret>"
[[ "${DRY_RUN}" == "true" ]] && warn "DRY-RUN — no writes will happen"
[[ "${ROTATE_ALL}" == "true" ]] && warn "ROTATE-ALL — every secret regenerates"
[[ -n "${ROTATE}" ]] && warn "ROTATE one: ${ROTATE}"

if [[ -n "${BACKUP_FILE}" ]]; then
  log "Backup file: ${BACKUP_FILE}"
  : > "${BACKUP_FILE}"
  printf '# bootstrap-vault-secrets.sh — generated at %s\n# vault: %s\n# DELETE THIS FILE AFTER COPYING TO YOUR PASSWORD MANAGER.\n\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${VAULT_ADDR}" >> "${BACKUP_FILE}"
fi

ensure_secret apicurio-registry-db        username password
ensure_secret hive-metastore-db           username password
ensure_minio_credentials
ensure_secret starrocks-root-credentials  password
ensure_secret postgres-bigdata-auth       postgres-password password replication-password

ok "Done."

if [[ -n "${BACKUP_FILE}" ]]; then
  warn "Backup written to ${BACKUP_FILE} — move to a password manager and delete."
fi

# -----------------------------------------------------------------------------
# Next steps
# -----------------------------------------------------------------------------
log "Next:"
log "  1. Apply ExternalSecret CRs:  kubectl apply -f deployments/cluster-prereqs/external-secrets/"
log "  2. Wait for sync:             kubectl -n isa-bigdata wait externalsecret --all --for=condition=Ready --timeout=2m"
log "  3. Verify Secrets exist:      kubectl -n isa-bigdata get secret apicurio-registry-db hive-metastore-db minio-credentials starrocks-root-credentials postgres-bigdata-auth"
