#!/bin/bash
# Unit test: Validate JupyterHub API routes use auth_service JWTs.
# L1 — Static config validation, no live services needed.

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_PASSED=0
TESTS_FAILED=0
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROUTE_MANIFEST="$REPO_ROOT/deployments/kubernetes/local/manifests/jupyterhub-apisix-route.yaml"

pass() { echo -e "${GREEN}PASS${NC} $1"; ((TESTS_PASSED++)); }
fail() { echo -e "${RED}FAIL${NC} $1"; ((TESTS_FAILED++)); }

echo "=== JupyterHub APISIX JWT Auth Validation ==="

if [ ! -f "$ROUTE_MANIFEST" ]; then
    fail "JupyterHub APISIX route manifest not found"
else
    if grep -q 'jupyterhub_api_route' "$ROUTE_MANIFEST" &&
       grep -Fq '"/jupyter/api/*"' "$ROUTE_MANIFEST"; then
        pass "jupyterhub_api_route protects direct Jupyter API paths"
    else
        fail "jupyterhub_api_route for /jupyter/api/* is missing"
    fi

    if grep -q '"jwt-auth"' "$ROUTE_MANIFEST"; then
        pass "JupyterHub API route enables APISIX jwt-auth"
    else
        fail "JupyterHub API route does not enable APISIX jwt-auth"
    fi

    if grep -q '"key_claim_name": "iss"' "$ROUTE_MANIFEST"; then
        pass "jwt-auth matches auth_service issuer claim"
    else
        fail "jwt-auth does not match auth_service issuer claim"
    fi

    if grep -q '"serverless-pre-function"' "$ROUTE_MANIFEST" && grep -q 'x-jupyter-jwt' "$ROUTE_MANIFEST"; then
        pass "route normalizes Authorization Bearer tokens for APISIX jwt-auth"
    else
        fail "route does not normalize Authorization Bearer tokens for APISIX jwt-auth"
    fi

    if grep -q '/apisix/admin/consumers/auth-service-jwt' "$ROUTE_MANIFEST"; then
        pass "job registers auth_service JWT APISIX consumer idempotently"
    else
        fail "job does not register auth_service JWT APISIX consumer"
    fi

    if grep -q 'AUTH_SERVICE_JWT_SECRET' "$ROUTE_MANIFEST"; then
        pass "job reads auth_service JWT secret from environment"
    else
        fail "job does not read auth_service JWT secret from environment"
    fi

    if grep -q '"uris": \["/jupyter", "/jupyter/\*"\]' "$ROUTE_MANIFEST" &&
       ! grep -q '"/jupyter/hub/login".*"jwt-auth"' "$ROUTE_MANIFEST" &&
       ! grep -q '"/jupyter/hub/oauth_callback".*"jwt-auth"' "$ROUTE_MANIFEST"; then
        pass "browser OAuth/login routes remain on the unprotected JupyterHub session route"
    else
        fail "browser OAuth/login route protection is unsafe"
    fi
fi

echo ""
echo "=== Results: $TESTS_PASSED passed, $TESTS_FAILED failed ==="

[ "$TESTS_FAILED" -eq 0 ] && exit 0 || exit 1
