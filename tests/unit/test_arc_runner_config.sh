#!/bin/bash
# Unit test: Validate local ARC self-hosted runner deployment contract.
# L1 — Static config validation, no live cluster needed.

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_PASSED=0
TESTS_FAILED=0
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ARC_DIR="$REPO_ROOT/deployments/kubernetes/local/arc"
CONTROLLER_VALUES="$ARC_DIR/values/controller.yaml"
RUNNER_VALUES="$ARC_DIR/values/runner-scale-set.yaml"
NAMESPACES_MANIFEST="$ARC_DIR/manifests/namespaces.yaml"
SECRET_TEMPLATE="$ARC_DIR/manifests/github-app-secret.template.yaml"
INSTALL_SCRIPT="$ARC_DIR/scripts/install-arc.sh"
GITIGNORE="$REPO_ROOT/.gitignore"

pass() { echo -e "${GREEN}PASS${NC} $1"; ((TESTS_PASSED++)); }
fail() { echo -e "${RED}FAIL${NC} $1"; ((TESTS_FAILED++)); }

require_file() {
    if [ -f "$1" ]; then
        pass "$2 exists"
    else
        fail "$2 missing"
    fi
}

echo "=== ARC Runner Config Validation ==="

require_file "$CONTROLLER_VALUES" "controller values"
require_file "$RUNNER_VALUES" "runner scale-set values"
require_file "$NAMESPACES_MANIFEST" "namespace manifest"
require_file "$SECRET_TEMPLATE" "GitHub App secret template"
require_file "$INSTALL_SCRIPT" "install script"

if [ -f "$NAMESPACES_MANIFEST" ]; then
    if grep -q 'name: arc-systems' "$NAMESPACES_MANIFEST" &&
       grep -q 'name: arc-runners' "$NAMESPACES_MANIFEST"; then
        pass "controller and runner namespaces are separate"
    else
        fail "controller and runner namespaces are not separate"
    fi

    if grep -A8 'name: arc-runners' "$NAMESPACES_MANIFEST" | grep -q 'pod-security.kubernetes.io/enforce: privileged'; then
        pass "runner namespace allows dind sidecar explicitly"
    else
        fail "runner namespace does not declare privileged PSA for dind"
    fi
fi

if [ -f "$CONTROLLER_VALUES" ]; then
    if grep -q 'watchSingleNamespace: "arc-runners"' "$CONTROLLER_VALUES"; then
        pass "controller watches only arc-runners"
    else
        fail "controller watch namespace is not constrained to arc-runners"
    fi

    if grep -q 'name: "arc-gha-rs-controller"' "$CONTROLLER_VALUES"; then
        pass "controller service account is pinned"
    else
        fail "controller service account is not pinned"
    fi
fi

if [ -f "$RUNNER_VALUES" ]; then
    if grep -q 'githubConfigUrl: "https://github.com/xenoISA"' "$RUNNER_VALUES"; then
        pass "runner scale set registers at xenoISA org scope"
    else
        fail "runner scale set is not org-scoped to xenoISA"
    fi

    if grep -q 'githubConfigSecret: arc-github-app' "$RUNNER_VALUES"; then
        pass "runner scale set uses GitHub App secret reference"
    else
        fail "runner scale set does not use expected GitHub App secret"
    fi

    if grep -q 'runnerGroup: "isA CI"' "$RUNNER_VALUES"; then
        pass "runner scale set is assigned to scoped isA CI runner group"
    else
        fail "runner scale set is not assigned to scoped isA CI runner group"
    fi

    # maxRunners caps concurrency so a burst of jobs can't exhaust the kind
    # cluster. The cap is currently 3 (one per kind worker); the absolute
    # bound is whatever the local cluster's worker count is, so we just
    # assert it is a positive small integer rather than pinning a value.
    if grep -q 'minRunners: 0' "$RUNNER_VALUES" &&
       grep -qE '^maxRunners: [1-9][0-9]?$' "$RUNNER_VALUES"; then
        pass "runner autoscaling scales to zero and caps concurrency"
    else
        fail "runner autoscaling is not bounded (expect minRunners: 0 + small maxRunners)"
    fi

    # dind sidecar is intentionally omitted on the local kind cluster — the
    # chart's hard-coded `docker info` startup probe (1 s timeout) cannot pass
    # under overlay-storage IO pressure. See #306. Once a workflow needs
    # docker-build, take over the pod template or switch to kubernetes mode.
    if ! grep -qE '^containerMode:' "$RUNNER_VALUES"; then
        pass "runner pods skip the dind sidecar (probe untunable on kind, #306)"
    else
        fail "containerMode is set; expect dind sidecar to stall on kind"
    fi

    if grep -q 'runnerScaleSetName: "self-hosted"' "$RUNNER_VALUES"; then
        pass "runner scale-set preserves existing self-hosted workflow label"
    else
        fail "runner scale-set label would break existing self-hosted workflows"
    fi
fi

if [ -f "$SECRET_TEMPLATE" ]; then
    if grep -q 'github_app_id:' "$SECRET_TEMPLATE" &&
       grep -q 'github_app_installation_id:' "$SECRET_TEMPLATE" &&
       grep -q 'github_app_private_key:' "$SECRET_TEMPLATE"; then
        pass "GitHub App secret template exposes required ARC keys"
    else
        fail "GitHub App secret template is missing required ARC keys"
    fi

    if grep -q '<REPLACE_WITH_GITHUB_APP_PRIVATE_KEY_PEM_CONTENTS>' "$SECRET_TEMPLATE"; then
        pass "GitHub App secret template contains placeholders only"
    else
        fail "GitHub App secret template may contain real key material"
    fi
fi

if [ -f "$INSTALL_SCRIPT" ]; then
    if grep -q 'CHART_VERSION="${ISA_ARC_CHART_VERSION:-0.14.1}"' "$INSTALL_SCRIPT"; then
        pass "install script pins ARC chart version"
    else
        fail "install script does not pin ARC chart version"
    fi

    if grep -q 'helm upgrade --install "$CONTROLLER_RELEASE"' "$INSTALL_SCRIPT" &&
       grep -q 'helm upgrade --install "$RUNNER_RELEASE"' "$INSTALL_SCRIPT"; then
        pass "install script reconciles controller and runner scale set"
    else
        fail "install script does not install both ARC releases"
    fi

    if grep -q 'kubectl create secret generic "$SECRET_NAME"' "$INSTALL_SCRIPT" &&
       grep -q -- '--dry-run=client -o yaml | kubectl apply -f -' "$INSTALL_SCRIPT"; then
        pass "install script creates GitHub App secret idempotently"
    else
        fail "install script does not create GitHub App secret idempotently"
    fi
fi

if [ -f "$GITIGNORE" ]; then
    if grep -q 'deployments/kubernetes/local/arc/manifests/github-app-secret.local.yaml' "$GITIGNORE" &&
       grep -q '\*.pem' "$GITIGNORE"; then
        pass "gitignore protects ARC local secret material"
    else
        fail "gitignore does not protect ARC local secret material"
    fi
fi

# ----------------------------------------------------------------------------
# Pre-baked runner image (#306)
# ----------------------------------------------------------------------------
RUNNER_DOCKERFILE="$ARC_DIR/runner-image/Dockerfile"
RUNNER_IMAGE_README="$ARC_DIR/runner-image/README.md"
BUILD_SCRIPT="$ARC_DIR/scripts/build-runner-image.sh"

require_file "$RUNNER_DOCKERFILE" "runner image Dockerfile"
require_file "$RUNNER_IMAGE_README" "runner image README"
require_file "$BUILD_SCRIPT" "build-runner-image.sh"

if [ -f "$RUNNER_DOCKERFILE" ]; then
    if grep -q "RUNNER_TOOL_CACHE=/opt/hostedtoolcache" "$RUNNER_DOCKERFILE"; then
        pass "Dockerfile sets RUNNER_TOOL_CACHE for actions/setup-* cache hits"
    else
        fail "Dockerfile does not set RUNNER_TOOL_CACHE"
    fi

    if grep -q "PYTHON_311=" "$RUNNER_DOCKERFILE" && grep -q "PYTHON_312=" "$RUNNER_DOCKERFILE"; then
        pass "Dockerfile pins Python 3.11 + 3.12 versions"
    else
        fail "Dockerfile does not pin Python versions"
    fi

    if grep -q "NODE_20=" "$RUNNER_DOCKERFILE" && grep -q "NODE_22=" "$RUNNER_DOCKERFILE"; then
        pass "Dockerfile pins Node.js 20 + 22 versions"
    else
        fail "Dockerfile does not pin Node.js versions"
    fi

    if grep -q "\.complete" "$RUNNER_DOCKERFILE"; then
        pass "Dockerfile writes tool-cache <arch>.complete markers"
    else
        fail "Dockerfile missing tool-cache .complete markers (setup-python will miss cache)"
    fi

    if grep -q "FROM ghcr.io/actions/actions-runner:" "$RUNNER_DOCKERFILE"; then
        pass "Dockerfile extends the official actions/actions-runner base"
    else
        fail "Dockerfile does not extend ghcr.io/actions/actions-runner"
    fi
fi

if [ -f "$BUILD_SCRIPT" ]; then
    if [ -x "$BUILD_SCRIPT" ]; then
        pass "build script is executable"
    else
        fail "build script is not executable"
    fi

    if grep -q "kind load docker-image" "$BUILD_SCRIPT"; then
        pass "build script loads image into the kind cluster"
    else
        fail "build script does not call kind load docker-image"
    fi
fi

if [ -f "$RUNNER_VALUES" ]; then
    if grep -q "image: isa-arc-runner:" "$RUNNER_VALUES"; then
        pass "runner scale-set values reference the custom isa-arc-runner image"
    else
        fail "runner scale-set values still point at the stock actions/runner image"
    fi

    if grep -q "imagePullPolicy: IfNotPresent" "$RUNNER_VALUES"; then
        pass "runner scale-set uses imagePullPolicy: IfNotPresent (uses kind-loaded image)"
    else
        fail "runner scale-set will try to pull from a registry (image is kind-loaded only)"
    fi
fi

echo ""
echo "=== Results: $TESTS_PASSED passed, $TESTS_FAILED failed ==="

[ "$TESTS_FAILED" -eq 0 ] && exit 0 || exit 1
