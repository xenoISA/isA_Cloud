#!/bin/bash
# Unit test: Validate OAuth .well-known route config across all environments
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

echo "=== OAuth .well-known Route Config Validation ==="

for env in local staging production; do
    SYNC_FILE="$DEPLOY_ROOT/$env/manifests/consul-apisix-sync.yaml"

    if [ ! -f "$SYNC_FILE" ]; then
        fail "$env: consul-apisix-sync.yaml not found"
        continue
    fi

    echo ""
    echo "--- Environment: $env ---"

    # Check that create_oauth_wellknown_routes function exists
    if grep -q 'create_oauth_wellknown_routes()' "$SYNC_FILE"; then
        pass "$env: create_oauth_wellknown_routes function defined"
    else
        fail "$env: create_oauth_wellknown_routes function missing"
    fi

    # Check that the function is called in main()
    if grep -q 'create_oauth_wellknown_routes$' "$SYNC_FILE"; then
        pass "$env: create_oauth_wellknown_routes called in main"
    else
        fail "$env: create_oauth_wellknown_routes not called in main"
    fi

    # Check oauth_protected_resource_route exists with correct URI
    if grep -q 'oauth_protected_resource_route' "$SYNC_FILE"; then
        pass "$env: oauth_protected_resource_route defined"
    else
        fail "$env: oauth_protected_resource_route missing"
    fi

    if grep -q '/.well-known/oauth-protected-resource' "$SYNC_FILE"; then
        pass "$env: /.well-known/oauth-protected-resource URI present"
    else
        fail "$env: /.well-known/oauth-protected-resource URI missing"
    fi

    # Check oauth_authorization_server_route exists with correct URI
    if grep -q 'oauth_authorization_server_route' "$SYNC_FILE"; then
        pass "$env: oauth_authorization_server_route defined"
    else
        fail "$env: oauth_authorization_server_route missing"
    fi

    if grep -q '/.well-known/oauth-authorization-server' "$SYNC_FILE"; then
        pass "$env: /.well-known/oauth-authorization-server URI present"
    else
        fail "$env: /.well-known/oauth-authorization-server URI missing"
    fi

    # Check upstream service names are correct
    if grep -A5 'oauth-protected-resource' "$SYNC_FILE" | head -20 | grep -q 'mcp_service' 2>/dev/null ||
       sed -n '/oauth_protected_resource_route/,/oauth_authorization_server_route/p' "$SYNC_FILE" | grep -q '"service_name": "mcp_service"'; then
        pass "$env: oauth-protected-resource routes to mcp_service"
    else
        fail "$env: oauth-protected-resource does not route to mcp_service"
    fi

    if sed -n '/oauth_authorization_server_route/,/^    }/p' "$SYNC_FILE" | grep -q '"service_name": "auth_service"'; then
        pass "$env: oauth-authorization-server routes to auth_service"
    else
        fail "$env: oauth-authorization-server does not route to auth_service"
    fi

    # Check routes are public (no jwt-auth in the wellknown function block)
    WELLKNOWN_BLOCK=$(sed -n '/create_oauth_wellknown_routes()/,/^    }/p' "$SYNC_FILE")
    if echo "$WELLKNOWN_BLOCK" | grep -q 'jwt-auth'; then
        fail "$env: .well-known routes should not have jwt-auth (must be public)"
    else
        pass "$env: .well-known routes are public (no jwt-auth)"
    fi

    # Check routes are tracked in processed_services (prevents stale cleanup)
    if grep -q 'processed_services+=("oauth_protected_resource_route")' "$SYNC_FILE"; then
        pass "$env: oauth_protected_resource_route tracked in processed_services"
    else
        fail "$env: oauth_protected_resource_route not tracked in processed_services"
    fi

    if grep -q 'processed_services+=("oauth_authorization_server_route")' "$SYNC_FILE"; then
        pass "$env: oauth_authorization_server_route tracked in processed_services"
    else
        fail "$env: oauth_authorization_server_route not tracked in processed_services"
    fi

    # Check methods are GET and OPTIONS only (discovery endpoints are read-only)
    if echo "$WELLKNOWN_BLOCK" | grep -q '"methods": \["GET", "OPTIONS"\]'; then
        pass "$env: .well-known routes allow only GET and OPTIONS"
    else
        fail "$env: .well-known routes should only allow GET and OPTIONS"
    fi
done

echo ""
echo "=== Results: $TESTS_PASSED passed, $TESTS_FAILED failed ==="

if [ "$TESTS_FAILED" -gt 0 ]; then
    exit 1
fi
