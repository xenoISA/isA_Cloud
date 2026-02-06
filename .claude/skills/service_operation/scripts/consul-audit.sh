#!/bin/bash
# consul-audit.sh - Audit all Consul service registrations against the isA standard
#
# Usage: ./consul-audit.sh [consul_url]
# Default consul_url: http://localhost:8500

set -euo pipefail

CONSUL_URL="${1:-http://localhost:8500}"
REQUIRED_META_KEYS=("base_path" "capabilities" "health" "methods" "version")
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}PASS${NC} $1"; ((PASS_COUNT++)); }
fail() { echo -e "  ${RED}FAIL${NC} $1"; ((FAIL_COUNT++)); }
warn() { echo -e "  ${YELLOW}WARN${NC} $1"; ((WARN_COUNT++)); }

echo "=== Consul Service Registration Audit ==="
echo "Consul: ${CONSUL_URL}"
echo "Date: $(date)"
echo ""

# Get all services (exclude consul itself)
SERVICES=$(curl -s "${CONSUL_URL}/v1/catalog/services" | jq -r 'keys[] | select(. != "consul")')

if [ -z "$SERVICES" ]; then
    echo "No services found in Consul"
    exit 1
fi

SERVICE_COUNT=$(echo "$SERVICES" | wc -l | tr -d ' ')
echo "Found ${SERVICE_COUNT} services"
echo ""

for SERVICE in $SERVICES; do
    echo "--- ${SERVICE} ---"

    # Check 1: Naming convention (_service suffix)
    if [[ "$SERVICE" == *"_service" ]]; then
        pass "Naming: follows {name}_service convention"
    else
        fail "Naming: missing _service suffix (got: ${SERVICE})"
    fi

    # Get service details
    CATALOG=$(curl -s "${CONSUL_URL}/v1/catalog/service/${SERVICE}")
    HEALTH=$(curl -s "${CONSUL_URL}/v1/health/service/${SERVICE}")

    # Check 2: Health check passing
    HEALTH_STATUS=$(echo "$HEALTH" | jq -r '.[0].Checks[] | select(.CheckID != "serfHealth") | .Status' 2>/dev/null || echo "unknown")
    if [ "$HEALTH_STATUS" = "passing" ]; then
        pass "Health: passing"
    elif [ "$HEALTH_STATUS" = "critical" ]; then
        fail "Health: critical"
    elif [ "$HEALTH_STATUS" = "warning" ]; then
        warn "Health: warning"
    else
        fail "Health: ${HEALTH_STATUS}"
    fi

    # Check 3: Required metadata keys
    META=$(echo "$CATALOG" | jq -r '.[0].ServiceMeta // {}')
    MISSING_META=()
    for KEY in "${REQUIRED_META_KEYS[@]}"; do
        HAS_KEY=$(echo "$META" | jq -r "has(\"${KEY}\")")
        if [ "$HAS_KEY" != "true" ]; then
            MISSING_META+=("$KEY")
        fi
    done
    if [ ${#MISSING_META[@]} -eq 0 ]; then
        pass "Metadata: all required keys present"
    else
        fail "Metadata: missing keys: ${MISSING_META[*]}"
    fi

    # Check 4: Version tag present
    TAGS=$(echo "$CATALOG" | jq -r '.[0].ServiceTags // [] | .[]' 2>/dev/null)
    HAS_VERSION_TAG=false
    for TAG in $TAGS; do
        if [[ "$TAG" =~ ^v[0-9]+ ]]; then
            HAS_VERSION_TAG=true
            break
        fi
    done
    if [ "$HAS_VERSION_TAG" = true ]; then
        pass "Tags: version tag present"
    else
        fail "Tags: no version tag (v1, v2, etc.)"
    fi

    # Check 5: Address is 127.0.0.1 (local dev)
    ADDRESS=$(echo "$CATALOG" | jq -r '.[0].ServiceAddress // "unknown"')
    if [ "$ADDRESS" = "127.0.0.1" ]; then
        pass "Address: 127.0.0.1 (local dev)"
    elif [ "$ADDRESS" = "localhost" ]; then
        warn "Address: localhost (should be 127.0.0.1)"
    else
        warn "Address: ${ADDRESS} (expected 127.0.0.1 for local dev)"
    fi

    echo ""
done

# Summary
echo "=== Audit Summary ==="
echo -e "Services: ${SERVICE_COUNT}"
echo -e "${GREEN}PASS: ${PASS_COUNT}${NC}"
echo -e "${RED}FAIL: ${FAIL_COUNT}${NC}"
echo -e "${YELLOW}WARN: ${WARN_COUNT}${NC}"

if [ "$FAIL_COUNT" -gt 0 ]; then
    echo ""
    echo "Some checks failed. Fix the issues above and re-run."
    exit 1
else
    echo ""
    echo "All checks passed!"
    exit 0
fi
