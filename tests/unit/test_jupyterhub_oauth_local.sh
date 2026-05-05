#!/bin/bash
# Unit test: Validate local JupyterHub uses isA Auth OAuth, not DummyAuthenticator.
# L1 — Static config validation, no live cluster needed.

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_PASSED=0
TESTS_FAILED=0
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VALUES_FILE="$REPO_ROOT/deployments/kubernetes/local/values/jupyterhub.yaml"

pass() { echo -e "${GREEN}PASS${NC} $1"; ((TESTS_PASSED++)); }
fail() { echo -e "${RED}FAIL${NC} $1"; ((TESTS_FAILED++)); }

echo "=== Local JupyterHub OAuth Validation ==="

if [ ! -f "$VALUES_FILE" ]; then
    fail "local JupyterHub values file not found"
else
    if grep -q 'authenticator_class: generic-oauth' "$VALUES_FILE"; then
        pass "JupyterHub uses GenericOAuthenticator"
    else
        fail "JupyterHub does not use GenericOAuthenticator"
    fi

    if grep -q 'DummyAuthenticator:' "$VALUES_FILE"; then
        fail "DummyAuthenticator config is still present"
    else
        pass "DummyAuthenticator config is removed"
    fi

    if grep -q 'jupyterhub-oauth' "$VALUES_FILE" && grep -q 'jupyterhub-crypt-key' "$VALUES_FILE"; then
        pass "OAuth client and crypt key secrets are referenced"
    else
        fail "OAuth client and crypt key secrets are not referenced"
    fi

    if grep -q 'http://localhost:18000/hub/oauth_callback' "$VALUES_FILE"; then
        pass "local OAuth callback URL is configured"
    else
        fail "local OAuth callback URL is missing"
    fi

    if grep -q 'http://127.0.0.1:8201/oauth/authorize' "$VALUES_FILE" &&
       grep -q 'http://127.0.0.1:8201/oauth/token' "$VALUES_FILE" &&
       grep -q 'http://127.0.0.1:8201/oauth/userinfo' "$VALUES_FILE"; then
        pass "local auth_service OAuth endpoints are configured"
    else
        fail "local auth_service OAuth endpoints are missing"
    fi

    if grep -q 'ISA_TENANT_ID' "$VALUES_FILE" && grep -q 'Refusing to spawn' "$VALUES_FILE"; then
        pass "tenant claim propagation and refusal path are configured"
    else
        fail "tenant claim propagation/refusal path is missing"
    fi
fi

echo ""
echo "=== Results: $TESTS_PASSED passed, $TESTS_FAILED failed ==="

[ "$TESTS_FAILED" -eq 0 ] && exit 0 || exit 1
