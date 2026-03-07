#!/bin/bash
# Unit test: Validate api-breaker circuit breaker config across all environments
# L1 — Static config validation, no live services needed

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_PASSED=0
TESTS_FAILED=0
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_ROOT="$SCRIPT_DIR/../../deployments/kubernetes"

pass() { echo -e "${GREEN}PASS${NC} $1"; ((TESTS_PASSED++)); }
fail() { echo -e "${RED}FAIL${NC} $1"; ((TESTS_FAILED++)); }

# Extract the api-breaker block for a given service from the sync script
get_breaker_block() {
    local file="$1" service="$2"
    # Get lines from the service match through the next fi/elif, capturing the api-breaker JSON
    sed -n "/\"$service\"/,/print_info.*api-breaker/p" "$file"
}

echo "=== Circuit Breaker Config Validation ==="

for env in local staging production; do
    SYNC_FILE="$DEPLOY_ROOT/$env/manifests/consul-apisix-sync.yaml"

    if [ ! -f "$SYNC_FILE" ]; then
        fail "$env: consul-apisix-sync.yaml not found"
        continue
    fi

    BLOCK=$(get_breaker_block "$SYNC_FILE" "mcp_service")

    # Check mcp_service circuit breaker block exists
    if echo "$BLOCK" | grep -q 'api-breaker'; then
        pass "$env: mcp_service has api-breaker plugin"
    else
        fail "$env: mcp_service missing api-breaker plugin"
    fi

    # Validate break_response_code is 502
    if echo "$BLOCK" | grep -q '"break_response_code": 502'; then
        pass "$env: break_response_code is 502"
    else
        fail "$env: break_response_code is not 502"
    fi

    # Validate failures threshold is 3
    if echo "$BLOCK" | grep -q '"failures": 3'; then
        pass "$env: failures threshold is 3"
    else
        fail "$env: failures threshold is not 3"
    fi

    # Validate healthy successes is 2
    if echo "$BLOCK" | grep -q '"successes": 2'; then
        pass "$env: healthy successes is 2"
    else
        fail "$env: healthy successes is not 2"
    fi

    # Validate max_breaker_sec <= 30 (take last match — the mcp_service one)
    MAX_SEC=$(echo "$BLOCK" | grep '"max_breaker_sec"' | tail -1 | grep -o '[0-9]*')
    if [ -n "$MAX_SEC" ] && [ "$MAX_SEC" -le 30 ]; then
        pass "$env: max_breaker_sec=$MAX_SEC (<=30)"
    else
        fail "$env: max_breaker_sec missing or >30 (got: ${MAX_SEC:-none})"
    fi
done

# Regression: model_service api-breaker still present
for env in local staging production; do
    SYNC_FILE="$DEPLOY_ROOT/$env/manifests/consul-apisix-sync.yaml"
    [ ! -f "$SYNC_FILE" ] && continue

    BLOCK=$(get_breaker_block "$SYNC_FILE" "model_service")
    if echo "$BLOCK" | grep -q 'api-breaker'; then
        pass "$env: model_service has api-breaker (regression)"
    else
        fail "$env: model_service missing api-breaker (regression)"
    fi
done

echo ""
echo "=== Results: $TESTS_PASSED passed, $TESTS_FAILED failed ==="

[ "$TESTS_FAILED" -eq 0 ] && exit 0 || exit 1
