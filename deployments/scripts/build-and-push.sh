#!/bin/bash
# =============================================================================
# ISA Platform - Build and Push to Harbor
# =============================================================================
# Builds Docker images and pushes to Harbor registry.
#
# Usage:
#   ./build-and-push.sh base           # Build and push python-base
#   ./build-and-push.sh mcp            # Build and push mcp-service
#   ./build-and-push.sh model          # Build and push model-service
#   ./build-and-push.sh all            # Build and push all images
#   ./build-and-push.sh mcp v1.2.3     # Build with specific version tag
#
# Prerequisites:
#   - Docker logged into Harbor: docker login harbor.local:30443
#   - Harbor port-forward running: kubectl port-forward svc/harbor -n harbor 30443:443
# =============================================================================

set -e

# Configuration
HARBOR_REGISTRY="harbor.local:30443"
HARBOR_PROJECT="isa"
ISA_ROOT="${ISA_ROOT:-$HOME/Documents/Fun/isA}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check Harbor connectivity
check_harbor() {
    log_info "Checking Harbor connectivity..."
    if ! curl -sk "https://${HARBOR_REGISTRY}/api/v2.0/health" | grep -q "healthy"; then
        log_error "Cannot connect to Harbor at ${HARBOR_REGISTRY}"
        log_info "Make sure port-forward is running:"
        log_info "  kubectl port-forward svc/harbor -n harbor 30443:443 &"
        exit 1
    fi
    log_info "Harbor is accessible"
}

# Build and push base image
build_base() {
    local version="${1:-latest}"
    local image="${HARBOR_REGISTRY}/${HARBOR_PROJECT}/python-base:${version}"

    log_info "Building python-base:${version}..."
    cd "${ISA_ROOT}/isA_Vibe"

    docker build \
        -t "${image}" \
        -f deployment/base/Dockerfile.python-base \
        .

    log_info "Pushing ${image}..."
    docker push "${image}"

    # Also tag as latest if version specified
    if [ "${version}" != "latest" ]; then
        docker tag "${image}" "${HARBOR_REGISTRY}/${HARBOR_PROJECT}/python-base:latest"
        docker push "${HARBOR_REGISTRY}/${HARBOR_PROJECT}/python-base:latest"
    fi

    log_info "Successfully pushed python-base:${version}"
}

# Build and push MCP service
build_mcp() {
    local version="${1:-latest}"
    local image="${HARBOR_REGISTRY}/${HARBOR_PROJECT}/mcp-service:${version}"

    log_info "Building mcp-service:${version}..."
    cd "${ISA_ROOT}/isA_MCP"

    docker build \
        -t "${image}" \
        -f deployment/k8s/Dockerfile.mcp \
        --build-arg ENVIRONMENT=production \
        --build-arg VERSION="${version}" \
        --build-arg BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        --build-arg VCS_REF="$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')" \
        .

    log_info "Pushing ${image}..."
    docker push "${image}"

    # Also tag as latest if version specified
    if [ "${version}" != "latest" ]; then
        docker tag "${image}" "${HARBOR_REGISTRY}/${HARBOR_PROJECT}/mcp-service:latest"
        docker push "${HARBOR_REGISTRY}/${HARBOR_PROJECT}/mcp-service:latest"
    fi

    log_info "Successfully pushed mcp-service:${version}"
}

# Build and push Model service
build_model() {
    local version="${1:-latest}"
    local image="${HARBOR_REGISTRY}/${HARBOR_PROJECT}/model-service:${version}"

    log_info "Building model-service:${version}..."
    cd "${ISA_ROOT}/isA_Model"

    # Check if Dockerfile exists
    if [ ! -f "deployment/k8s/Dockerfile.model" ]; then
        log_warn "deployment/k8s/Dockerfile.model not found, skipping..."
        return 0
    fi

    docker build \
        -t "${image}" \
        -f deployment/k8s/Dockerfile.model \
        --build-arg ENVIRONMENT=production \
        --build-arg VERSION="${version}" \
        .

    log_info "Pushing ${image}..."
    docker push "${image}"

    log_info "Successfully pushed model-service:${version}"
}

# Build all images
build_all() {
    local version="${1:-latest}"

    log_info "Building all images with version: ${version}"

    # Base must be built first
    build_base "${version}"

    # Then services (can be parallel in CI)
    build_mcp "${version}"
    build_model "${version}"

    log_info "All images built and pushed successfully!"
}

# Show usage
usage() {
    echo "Usage: $0 <service> [version]"
    echo ""
    echo "Services:"
    echo "  base    Build and push python-base image"
    echo "  mcp     Build and push mcp-service image"
    echo "  model   Build and push model-service image"
    echo "  all     Build and push all images"
    echo ""
    echo "Examples:"
    echo "  $0 base                    # Build base with 'latest' tag"
    echo "  $0 mcp v1.2.3              # Build MCP with version tag"
    echo "  $0 all v1.0.0              # Build all with version tag"
    echo ""
    echo "Environment:"
    echo "  ISA_ROOT    Root directory of isA projects (default: ~/Documents/Fun/isA)"
}

# Main
main() {
    local service="${1:-}"
    local version="${2:-latest}"

    if [ -z "${service}" ]; then
        usage
        exit 1
    fi

    check_harbor

    case "${service}" in
        base)
            build_base "${version}"
            ;;
        mcp)
            build_mcp "${version}"
            ;;
        model)
            build_model "${version}"
            ;;
        all)
            build_all "${version}"
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown service: ${service}"
            usage
            exit 1
            ;;
    esac
}

main "$@"
