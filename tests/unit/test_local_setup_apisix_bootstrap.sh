#!/bin/bash
# Unit test: Validate local bootstrap includes APISIX values + Consul sync wiring
# L1 — Static config validation, no live services needed

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_PASSED=0
TESTS_FAILED=0
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SETUP_SCRIPT="$REPO_ROOT/.claude/skills/cluster_operations/scripts/setup-local.sh"
APISIX_VALUES="$REPO_ROOT/deployments/kubernetes/local/values/apisix.yaml"
SYNC_MANIFEST="$REPO_ROOT/deployments/kubernetes/local/manifests/consul-apisix-sync.yaml"
STAGING_APISIX_VALUES="$REPO_ROOT/deployments/kubernetes/staging/values/apisix.yaml"
PRODUCTION_APISIX_VALUES="$REPO_ROOT/deployments/kubernetes/production/values/apisix.yaml"
STAGING_SYNC_MANIFEST="$REPO_ROOT/deployments/kubernetes/staging/manifests/consul-apisix-sync.yaml"
PRODUCTION_SYNC_MANIFEST="$REPO_ROOT/deployments/kubernetes/production/manifests/consul-apisix-sync.yaml"

pass() { echo -e "${GREEN}PASS${NC} $1"; ((TESTS_PASSED++)); }
fail() { echo -e "${RED}FAIL${NC} $1"; ((TESTS_FAILED++)); }

echo "=== Local APISIX Bootstrap Validation ==="

if [ ! -f "$SETUP_SCRIPT" ]; then
    fail "setup-local.sh not found"
else
    if grep -q 'values_for apisix' "$SETUP_SCRIPT"; then
        pass "setup-local.sh resolves local APISIX values"
    else
        fail "setup-local.sh does not resolve APISIX values"
    fi

    if grep -q 'consul-apisix-sync.yaml' "$SETUP_SCRIPT"; then
        pass "setup-local.sh applies consul-apisix-sync manifest"
    else
        fail "setup-local.sh does not apply consul-apisix-sync manifest"
    fi
fi

if [ ! -f "$APISIX_VALUES" ]; then
    fail "local APISIX values file not found"
else
    if grep -q 'default_service:' "$APISIX_VALUES"; then
        pass "local APISIX values configure discovery default_service"
    else
        fail "local APISIX values missing discovery default_service"
    fi

    if grep -q 'consul-server.isa-cloud-local.svc.cluster.local:8500' "$APISIX_VALUES"; then
        pass "local APISIX values point discovery at consul-server:8500"
    else
        fail "local APISIX values missing consul-server:8500 discovery target"
    fi

    if grep -A2 '^etcd:' "$APISIX_VALUES" | grep -q 'enabled: true'; then
        pass "local APISIX values keep chart-managed etcd enabled"
    else
        fail "local APISIX values do not keep chart-managed etcd enabled"
    fi
fi

if [ ! -f "$SYNC_MANIFEST" ]; then
    fail "local Consul-APISIX sync manifest not found"
else
    if grep -q 'image: hashicorp/consul:1.22.6' "$SYNC_MANIFEST"; then
        pass "local sync manifest pins watch/sync image to hashicorp/consul:1.22.6"
    else
        fail "local sync manifest does not pin the validated consul image"
    fi

    if grep -q 'host.docker.internal' "$SYNC_MANIFEST"; then
        pass "local sync manifest defaults frontend static upstreams to host.docker.internal"
    else
        fail "local sync manifest does not default frontend static upstreams to host.docker.internal"
    fi
fi

for values_file in "$STAGING_APISIX_VALUES" "$PRODUCTION_APISIX_VALUES"; do
    env_name="$(basename "$(dirname "$(dirname "$values_file")")")"
    if [ ! -f "$values_file" ]; then
        fail "$env_name APISIX values file not found"
        continue
    fi

    if grep -q 'default_service:' "$values_file"; then
        pass "$env_name APISIX values configure discovery default_service"
    else
        fail "$env_name APISIX values missing discovery default_service"
    fi

    if grep -q 'consul-server\..*\.svc\.cluster\.local:8500' "$values_file"; then
        pass "$env_name APISIX values point discovery at consul-server:8500"
    else
        fail "$env_name APISIX values missing consul-server:8500 discovery target"
    fi
done

for manifest_file in "$STAGING_SYNC_MANIFEST" "$PRODUCTION_SYNC_MANIFEST"; do
    env_name="$(basename "$(dirname "$(dirname "$manifest_file")")")"
    if [ ! -f "$manifest_file" ]; then
        fail "$env_name sync manifest not found"
        continue
    fi

    if grep -q 'image: hashicorp/consul:1.22.6' "$manifest_file"; then
        pass "$env_name sync manifest pins watch/sync image to hashicorp/consul:1.22.6"
    else
        fail "$env_name sync manifest does not pin the validated consul image"
    fi

    if grep -Fq '\"allow_origins\": \"${cors_origins}\"' "$manifest_file"; then
        pass "$env_name sync manifest uses explicit CORS origins for frontend routes"
    else
        fail "$env_name sync manifest still uses invalid wildcard CORS for frontend routes"
    fi
done

echo ""
echo "=== Results: $TESTS_PASSED passed, $TESTS_FAILED failed ==="

[ "$TESTS_FAILED" -eq 0 ] && exit 0 || exit 1
