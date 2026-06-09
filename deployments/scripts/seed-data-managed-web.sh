#!/usr/bin/env bash
# =============================================================================
# seed-data-managed-web.sh — write the data-service managed-web provider creds
# into Vault at secret/isa-bigdata/data-managed-web (companion to the
# cluster-prereqs/external-secrets/15-data-managed-web.yaml ExternalSecret).
# =============================================================================
# Bright Data (shared with isA_OS pool_manager) + Oxylabs. Values are NEVER
# echoed. Bright Data key is read from the local secret backup; Oxylabs creds
# are read from env (no account yet at time of writing).
#
# Vault auth: standard $VAULT_ADDR + $VAULT_TOKEN. Token needs create+update on
# secret/data/isa-bigdata/data-managed-web.
#
# Usage:
#   ./seed-data-managed-web.sh                 # dry-run: show what would write
#   ./seed-data-managed-web.sh --apply         # actually write to Vault
#   BRIGHTDATA_BACKUP=/path/to/backup.env OXYLABS_USERNAME=u OXYLABS_PASSWORD=p \
#     ./seed-data-managed-web.sh --apply
#
# Requires the `vault` CLI on PATH.
# =============================================================================
set -euo pipefail

APPLY=false; [ "${1:-}" = "--apply" ] && APPLY=true
BACKUP="${BRIGHTDATA_BACKUP:-$HOME/.isa-secrets-backup/isa-secrets-recovered.env}"
# vault CLI kv path (KV-v2 mount `secret`; ESO reads it as secret/data/...).
# isA upstream uses isa-cloud; on the SN cluster this is secret/sn-cloud/production/...
VAULT_KV_PATH="${VAULT_KV_PATH:-secret/isa-cloud/production/data-managed-web}"

die() { echo "ERROR: $*" >&2; exit 1; }

# Bright Data key from backup (prefer BRIGHTDATA_API_KEY, fall back to BRIGHT_API_KEY)
[ -f "$BACKUP" ] || die "backup not found: $BACKUP"
BRIGHTDATA_API_KEY="$(grep -m1 '^BRIGHTDATA_API_KEY=' "$BACKUP" | cut -d= -f2- || true)"
[ -n "$BRIGHTDATA_API_KEY" ] || BRIGHTDATA_API_KEY="$(grep -m1 '^BRIGHT_API_KEY=' "$BACKUP" | cut -d= -f2- || true)"
[ -n "$BRIGHTDATA_API_KEY" ] || die "no BRIGHTDATA_API_KEY/BRIGHT_API_KEY in $BACKUP"

# Oxylabs from env (optional — no account yet)
OXY_U="${OXYLABS_USERNAME:-}"
OXY_P="${OXYLABS_PASSWORD:-}"

# Build kv args without exposing values in argv of subshells/logs
ARGS=( "brightdata-api-key=${BRIGHTDATA_API_KEY}" )
[ -n "$OXY_U" ] && ARGS+=( "oxylabs-username=${OXY_U}" )
[ -n "$OXY_P" ] && ARGS+=( "oxylabs-password=${OXY_P}" )

echo "Vault path : ${VAULT_KV_PATH}"
echo "Keys       : brightdata-api-key$([ -n "$OXY_U" ] && echo ', oxylabs-username')$([ -n "$OXY_P" ] && echo ', oxylabs-password')"
echo "Bright Data: present (redacted)$([ -z "$OXY_U" ] && echo '   [oxylabs: skipped — set OXYLABS_USERNAME/PASSWORD when account exists]')"

if ! $APPLY; then
  echo
  echo "[dry-run] would run: vault kv put ${VAULT_KV_PATH} <${#ARGS[@]} keys>"
  echo "[dry-run] re-run with --apply to write the vault property FIRST, THEN apply the"
  echo "          updated isa-platform-secrets ExternalSecret (which adds the BRIGHTDATA_API_KEY"
  echo "          mapping). Order matters: if the ExternalSecret references a missing vault"
  echo "          property, ESO fails the WHOLE isa-platform-secrets sync."
  exit 0
fi

command -v vault >/dev/null || die "vault CLI not found"
: "${VAULT_ADDR:?set VAULT_ADDR}"; : "${VAULT_TOKEN:?set VAULT_TOKEN}"
vault kv put "${VAULT_KV_PATH}" "${ARGS[@]}" >/dev/null
echo "✅ wrote ${#ARGS[@]} key(s) to ${VAULT_KV_PATH}"
echo "   NOW apply the ExternalSecret edit:"
echo "     kubectl apply -f deployments/editions/sn/externalsecret-isa-platform-secrets.yaml"
echo "     kubectl -n sn-cloud-production annotate externalsecret isa-platform-secrets force-sync=\$(date +%s) --overwrite"
