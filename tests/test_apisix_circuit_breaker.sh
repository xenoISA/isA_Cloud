#!/bin/bash
# L5 Smoke Test: Verify circuit breaker and Redis rate limiting on APISIX routes
#
# Queries the APISIX admin API to verify that:
# 1. MCP route has api-breaker plugin configured
# 2. Model route has api-breaker plugin configured
# 3. limit-count policy is "redis" with correct connection params
#
# Usage: bash tests/test_apisix_circuit_breaker.sh
# Requires: APISIX_ADMIN_URL, APISIX_ADMIN_KEY env vars (or defaults to local)

set -euo pipefail

APISIX_ADMIN_URL="${APISIX_ADMIN_URL:-http://localhost:9180}"
ADMIN_KEY="${APISIX_ADMIN_KEY:-}"
PASS=0
FAIL=0

if [ -z "$ADMIN_KEY" ]; then
    echo "ERR: APISIX_ADMIN_KEY must be set"
    exit 1
fi

check() {
    local desc=$1
    local condition=$2
    if eval "$condition"; then
        echo "PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $desc"
        FAIL=$((FAIL + 1))
    fi
}

get_route() {
    local route_name=$1
    curl -s "${APISIX_ADMIN_URL}/apisix/admin/routes/${route_name}" \
        -H "X-API-KEY: ${ADMIN_KEY}"
}

# --- MCP circuit breaker (#134) ---

MCP_ROUTE=$(get_route "mcp_service_route")

check "MCP route has api-breaker plugin" \
    "echo '$MCP_ROUTE' | jq -e '.value.plugins[\"api-breaker\"]' > /dev/null 2>&1"

check "MCP api-breaker break_response_code is 502" \
    "[ \"\$(echo '$MCP_ROUTE' | jq '.value.plugins[\"api-breaker\"].break_response_code')\" = '502' ]"

check "MCP api-breaker max_breaker_sec is 30" \
    "[ \"\$(echo '$MCP_ROUTE' | jq '.value.plugins[\"api-breaker\"].max_breaker_sec')\" = '30' ]"

check "MCP api-breaker unhealthy failures is 3" \
    "[ \"\$(echo '$MCP_ROUTE' | jq '.value.plugins[\"api-breaker\"].unhealthy.failures')\" = '3' ]"

check "MCP api-breaker healthy successes is 2" \
    "[ \"\$(echo '$MCP_ROUTE' | jq '.value.plugins[\"api-breaker\"].healthy.successes')\" = '2' ]"

check "MCP api-breaker unhealthy http_statuses is [500,502,503]" \
    "[ \"\$(echo '$MCP_ROUTE' | jq -c '.value.plugins[\"api-breaker\"].unhealthy.http_statuses')\" = '[500,502,503]' ]"

# --- Model circuit breaker (existing, regression check) ---

MODEL_ROUTE=$(get_route "model_service_route")

check "Model route has api-breaker plugin" \
    "echo '$MODEL_ROUTE' | jq -e '.value.plugins[\"api-breaker\"]' > /dev/null 2>&1"

check "Model api-breaker max_breaker_sec is 15" \
    "[ \"\$(echo '$MODEL_ROUTE' | jq '.value.plugins[\"api-breaker\"].max_breaker_sec')\" = '15' ]"

check "Model api-breaker unhealthy http_statuses includes 504" \
    "echo '$MODEL_ROUTE' | jq -e '.value.plugins[\"api-breaker\"].unhealthy.http_statuses | index(504)' > /dev/null 2>&1"

# --- Redis rate limiting (#135) ---

check "MCP limit-count policy is redis" \
    "[ \"\$(echo '$MCP_ROUTE' | jq -r '.value.plugins[\"limit-count\"].policy')\" = 'redis' ]"

check "MCP limit-count redis_port is 6379" \
    "[ \"\$(echo '$MCP_ROUTE' | jq '.value.plugins[\"limit-count\"].redis_port')\" = '6379' ]"

check "MCP limit-count redis_database is 1" \
    "[ \"\$(echo '$MCP_ROUTE' | jq '.value.plugins[\"limit-count\"].redis_database')\" = '1' ]"

check "MCP limit-count redis_host is set" \
    "[ \"\$(echo '$MCP_ROUTE' | jq -r '.value.plugins[\"limit-count\"].redis_host')\" != 'null' ]"

check "Model limit-count policy is redis" \
    "[ \"\$(echo '$MODEL_ROUTE' | jq -r '.value.plugins[\"limit-count\"].policy')\" = 'redis' ]"

# --- Summary ---

echo ""
echo "Results: $PASS passed, $FAIL failed"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi

echo "SMOKE: Circuit breaker + Redis rate limiting verification passed"
