#!/bin/bash
# L1 Unit Test: Validate port 8081 in network policies
# Tests that network-policies.yaml includes port 8081 for MCP service
# in both ingress (allow-apisix-to-backends) and egress (allow-apisix-egress)
#
# Validates all 3 environments: production, staging, local

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

check_port_8081() {
    local env=$1
    local file="${BASE_DIR}/deployments/kubernetes/${env}/manifests/network-policies.yaml"

    if [ ! -f "$file" ]; then
        assert_fail "${env}: network-policies.yaml not found"
        return
    fi

    # Check port 8081 exists at all
    if grep -q 'port: 8081' "$file"; then
        assert_pass "${env}: port 8081 present in network policies"
    else
        assert_fail "${env}: port 8081 missing from network policies"
    fi

    # Check it appears at least twice (ingress + egress)
    local count
    count=$(grep -c 'port: 8081' "$file" || true)

    if [ "$count" -ge 2 ]; then
        assert_pass "${env}: port 8081 in both ingress and egress policies (found ${count})"
    else
        assert_fail "${env}: port 8081 only in ${count} policy (expected >= 2 for ingress + egress)"
    fi
}

echo "======================================================================"
echo "Network Policy Port 8081 Tests"
echo "======================================================================"

echo ""
echo "--- Production ---"
check_port_8081 "production"

echo ""
echo "--- Staging ---"
check_port_8081 "staging"

echo ""
echo "--- Local ---"
check_port_8081 "local"

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
