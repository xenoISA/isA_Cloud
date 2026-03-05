#!/bin/bash
# L1 Unit Test: Validate APISIX upstream retry policy configuration
# Tests that consul-apisix-sync scripts include proper retry config

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
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

check_retry_config() {
    local env=$1
    local file="${BASE_DIR}/deployments/kubernetes/${env}/manifests/consul-apisix-sync.yaml"

    if [ ! -f "$file" ]; then
        assert_fail "${env}: consul-apisix-sync.yaml not found"
        return
    fi

    if grep -q '\\"retries\\": 2' "$file" || grep -q '\\"retries\\":2' "$file"; then
        assert_pass "${env}: retries set to 2"
    else
        assert_fail "${env}: retries not set to 2"
    fi

    if grep -q '\\"retry_timeout\\": 6' "$file" || grep -q '\\"retry_timeout\\":6' "$file"; then
        assert_pass "${env}: retry_timeout set to 6s"
    else
        assert_fail "${env}: retry_timeout not set to 6s"
    fi

    local retries_count
    retries_count=$(grep -c '\\"retries\\"' "$file" || true)
    if [ "$retries_count" -ge 2 ]; then
        assert_pass "${env}: retries configured in both main and health route upstreams"
    else
        assert_fail "${env}: retries missing from health route upstream (found ${retries_count}, expected >= 2)"
    fi

    local retry_timeout_count
    retry_timeout_count=$(grep -c '\\"retry_timeout\\"' "$file" || true)
    if [ "$retry_timeout_count" -ge 2 ]; then
        assert_pass "${env}: retry_timeout configured in both main and health route upstreams"
    else
        assert_fail "${env}: retry_timeout missing from health route upstream (found ${retry_timeout_count}, expected >= 2)"
    fi
}

echo "======================================================================"
echo "APISIX Retry Policy Configuration Tests"
echo "======================================================================"

echo ""
echo "--- Production ---"
check_retry_config "production"

echo ""
echo "--- Staging ---"
check_retry_config "staging"

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
