#!/bin/bash
# L1 Unit Test: Validate APISIX upstream health check configuration
# Tests that consul-apisix-sync scripts include proper health check config
#
# Validates:
# - Active health checks present in main route upstream
# - Passive health checks present in main route upstream
# - Health check parameters match requirements
# - Both production and staging environments configured

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

TESTS_PASSED=0
TESTS_FAILED=0
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

assert_pass() {
    echo -e "${GREEN}PASS:${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

assert_fail() {
    echo -e "${RED}FAIL:${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

# Extract the upstream JSON block from the sync script's create_or_update_route function
# We look for the -d payload and extract the upstream object
check_upstream_has_health_checks() {
    local env=$1
    local file="${BASE_DIR}/deployments/kubernetes/${env}/manifests/consul-apisix-sync.yaml"

    if [ ! -f "$file" ]; then
        assert_fail "${env}: consul-apisix-sync.yaml not found"
        return
    fi

    # The sync script embeds JSON with escaped quotes (\"key\"), so match accordingly
    # Check that the main route upstream contains "checks" config
    if grep -q '\\"checks\\"' "$file"; then
        assert_pass "${env}: upstream contains 'checks' configuration"
    else
        assert_fail "${env}: upstream missing 'checks' configuration"
        return
    fi

    # Check active health check path
    if grep -q '\\"http_path\\"' "$file" && grep -q '/health' "$file"; then
        assert_pass "${env}: active health check polls /health"
    else
        assert_fail "${env}: active health check missing /health path"
    fi

    # Check active healthy interval (should be 5s)
    if grep -q '\\"interval\\": 5' "$file" || grep -q '\\"interval\\":5' "$file"; then
        assert_pass "${env}: active healthy interval is 5s"
    else
        assert_fail "${env}: active healthy interval not set to 5s"
    fi

    # Check active healthy successes (should be 2)
    if grep -q '\\"successes\\": 2' "$file" || grep -q '\\"successes\\":2' "$file"; then
        assert_pass "${env}: healthy successes threshold is 2"
    else
        assert_fail "${env}: healthy successes threshold not set to 2"
    fi

    # Check active unhealthy http_failures (should be 3)
    if grep -q '\\"http_failures\\": 3' "$file" || grep -q '\\"http_failures\\":3' "$file"; then
        assert_pass "${env}: unhealthy http_failures threshold is 3"
    else
        assert_fail "${env}: unhealthy http_failures threshold not set to 3"
    fi

    # Check active health check timeout (should be 3s)
    if grep -q '\\"timeout\\": 3' "$file" || grep -q '\\"timeout\\":3' "$file"; then
        assert_pass "${env}: active health check timeout is 3s"
    else
        assert_fail "${env}: active health check timeout not set to 3s"
    fi

    # Check passive health checks exist
    if grep -q '\\"passive\\"' "$file"; then
        assert_pass "${env}: passive health checks configured"
    else
        assert_fail "${env}: passive health checks missing"
    fi

    # Check passive unhealthy http_statuses includes 500, 502, 503
    if grep -q '500' "$file" && grep -q '502' "$file" && grep -q '503' "$file"; then
        assert_pass "${env}: passive checks monitor 500/502/503 statuses"
    else
        assert_fail "${env}: passive checks missing 500/502/503 status monitoring"
    fi

    # Check passive unhealthy timeouts (should be 3)
    if grep -q '\\"timeouts\\": 3' "$file" || grep -q '\\"timeouts\\":3' "$file"; then
        assert_pass "${env}: passive unhealthy timeouts threshold is 3"
    else
        assert_fail "${env}: passive unhealthy timeouts threshold not set to 3"
    fi
}

# Check that health route upstream also has checks
check_health_route_has_checks() {
    local env=$1
    local file="${BASE_DIR}/deployments/kubernetes/${env}/manifests/consul-apisix-sync.yaml"

    if [ ! -f "$file" ]; then
        return
    fi

    # Count occurrences of "checks" — should appear in both route functions
    local checks_count
    checks_count=$(grep -c '\\"checks\\"' "$file" || true)

    if [ "$checks_count" -ge 2 ]; then
        assert_pass "${env}: health checks in both main and health route upstreams"
    else
        assert_fail "${env}: health checks missing from health route upstream (found ${checks_count}, expected >= 2)"
    fi
}

echo "======================================================================"
echo "APISIX Health Check Configuration Tests"
echo "======================================================================"

echo ""
echo "--- Production ---"
check_upstream_has_health_checks "production"
check_health_route_has_checks "production"

echo ""
echo "--- Staging ---"
check_upstream_has_health_checks "staging"
check_health_route_has_checks "staging"

echo ""
echo "======================================================================"
TOTAL=$((TESTS_PASSED + TESTS_FAILED))
echo -e "Total: $TOTAL | ${GREEN}Passed: $TESTS_PASSED${NC} | ${RED}Failed: $TESTS_FAILED${NC}"

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed${NC}"
    exit 1
fi
