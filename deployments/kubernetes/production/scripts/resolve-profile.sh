#!/bin/bash
# =============================================================================
# Resolve provider profile — reads a profile YAML and outputs storage class
# mappings as shell variables for use by deploy.sh
# =============================================================================
# Usage: source <(./resolve-profile.sh infotrend)
#        echo $STORAGE_BLOCK  # => infotrend-block
# =============================================================================

set -e

PROFILE_NAME="${1:-generic}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROFILES_DIR="${SCRIPT_DIR}/../profiles"
PROFILE_FILE="${PROFILES_DIR}/${PROFILE_NAME}.yaml"

if [[ ! -f "$PROFILE_FILE" ]]; then
    echo "ERROR: Provider profile not found: ${PROFILE_FILE}" >&2
    echo "Available profiles:" >&2
    ls "${PROFILES_DIR}"/*.yaml 2>/dev/null | xargs -I{} basename {} .yaml >&2
    exit 1
fi

# Parse YAML storage mappings (portable — no yq dependency)
parse_storage() {
    local key="$1"
    local value
    value=$(grep "^  ${key}:" "$PROFILE_FILE" | sed 's/^.*: *//' | tr -d '"' | tr -d "'")
    echo "$value"
}

STORAGE_BLOCK=$(parse_storage "block")
STORAGE_FAST=$(parse_storage "fast")
STORAGE_NFS=$(parse_storage "nfs")
STORAGE_OBJECT=$(parse_storage "object")
PROVIDER=$(grep "^provider:" "$PROFILE_FILE" | sed 's/^.*: *//' | tr -d '"')

# Export as shell variables
echo "export PROVIDER=\"${PROVIDER}\""
echo "export STORAGE_BLOCK=\"${STORAGE_BLOCK}\""
echo "export STORAGE_FAST=\"${STORAGE_FAST}\""
echo "export STORAGE_NFS=\"${STORAGE_NFS}\""
echo "export STORAGE_OBJECT=\"${STORAGE_OBJECT}\""
