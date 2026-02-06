#!/bin/bash

# ============================================
# isA Platform - Infrastructure Staging Build Script
# ============================================
# Builds all infrastructure Docker images for staging environment
# Uses Dockerfiles from deployments/dockerfiles/Staging/

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DOCKERFILES_DIR="${PROJECT_ROOT}/deployments/dockerfiles/Staging"
PLATFORM="amd64"

# Service list - must match the Dockerfiles in Staging directory
SERVICES=(
    "consul"
    "redis"
    "minio"
    "nats"
    "mosquitto"
    "postgres"
    "qdrant"
    "neo4j"
    "loki"
    "grafana"
)

# Function to print colored messages
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."

    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    # Check if Dockerfiles directory exists
    if [ ! -d "${DOCKERFILES_DIR}" ]; then
        print_error "Dockerfiles directory not found: ${DOCKERFILES_DIR}"
        exit 1
    fi

    print_success "All prerequisites met"
}

# Function to build a single service image
build_service() {
    local service=$1
    local dockerfile="${DOCKERFILES_DIR}/Dockerfile.${service}.staging"
    local image_name="staging-isa-${service}:${PLATFORM}"

    print_info "Building ${service} image..."

    if [ ! -f "${dockerfile}" ]; then
        print_error "Dockerfile not found: ${dockerfile}"
        return 1
    fi

    # Build the image from project root (to access COPY paths correctly)
    cd "${PROJECT_ROOT}"

    if docker build \
        --platform linux/${PLATFORM} \
        -f "${dockerfile}" \
        -t "${image_name}" \
        --no-cache \
        .; then
        print_success "Built ${image_name}"
        return 0
    else
        print_error "Failed to build ${image_name}"
        return 1
    fi
}

# Function to build all images
build_all_images() {
    print_info "Starting build process for all infrastructure services..."
    local failed_services=()

    for service in "${SERVICES[@]}"; do
        if ! build_service "${service}"; then
            failed_services+=("${service}")
        fi
    done

    if [ ${#failed_services[@]} -gt 0 ]; then
        print_error "Failed to build the following services: ${failed_services[*]}"
        exit 1
    fi

    print_success "All infrastructure images built successfully"
}

# Function to verify images
verify_images() {
    print_info "Verifying built images..."
    local missing_images=()

    for service in "${SERVICES[@]}"; do
        local image_name="staging-isa-${service}:${PLATFORM}"
        if ! docker image inspect "${image_name}" &> /dev/null; then
            missing_images+=("${image_name}")
        else
            local size=$(docker image inspect "${image_name}" --format='{{.Size}}' | awk '{printf "%.2f MB", $1/1024/1024}')
            print_info "   ${image_name} (${size})"
        fi
    done

    if [ ${#missing_images[@]} -gt 0 ]; then
        print_error "Missing images: ${missing_images[*]}"
        exit 1
    fi

    print_success "All images verified"
}

# Function to list built images
list_images() {
    print_info "Built staging infrastructure images:"
    echo ""
    docker images --filter "reference=staging-isa-*:${PLATFORM}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
    echo ""
}

# Main execution
main() {
    echo ""
    print_info "=== isA Platform - Staging Infrastructure Build ==="
    echo ""

    # Parse command line arguments
    SPECIFIC_SERVICE=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --service)
                SPECIFIC_SERVICE="$2"
                shift 2
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --service <name>  Build only a specific service"
                echo "  --help           Show this help message"
                echo ""
                echo "Available services:"
                for service in "${SERVICES[@]}"; do
                    echo "  - ${service}"
                done
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done

    # Execute build steps
    check_prerequisites

    if [ -n "$SPECIFIC_SERVICE" ]; then
        # Build specific service
        if [[ " ${SERVICES[@]} " =~ " ${SPECIFIC_SERVICE} " ]]; then
            build_service "${SPECIFIC_SERVICE}"
        else
            print_error "Unknown service: ${SPECIFIC_SERVICE}"
            echo "Available services: ${SERVICES[*]}"
            exit 1
        fi
    else
        # Build all services
        build_all_images
    fi

    verify_images
    list_images

    print_success "Build script completed successfully!"
    echo ""
    print_info "Next step: Run ./deployments/scripts/deploy_infra_staging.sh to deploy the services"
    echo ""
}

# Run main function
main "$@"
