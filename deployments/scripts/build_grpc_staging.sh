#!/bin/bash

# ============================================
# isA Platform - gRPC Services Staging Build Script
# ============================================
# Builds all gRPC service Docker images for staging environment
# Uses Dockerfiles from deployments/dockerfiles/

set -e

# Enable Docker BuildKit for faster builds with cache mounts
export DOCKER_BUILDKIT=1

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DOCKERFILES_DIR="${PROJECT_ROOT}/deployments/dockerfiles"
PLATFORM="linux/amd64"

# Service list - all gRPC services
READY_SERVICES=(
    "minio-service"
    "duckdb-service"
    "mqtt-service"
    "nats-service"
    "postgres-service"
    "qdrant-service"
    "neo4j-service"
)

PENDING_SERVICES=(
    "redis-service"
    "loki-service"
)

# Combine all services
ALL_SERVICES=("${READY_SERVICES[@]}" "${PENDING_SERVICES[@]}")

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

# Function to generate proto files
generate_proto_files() {
    print_info "Generating gRPC proto files..."

    local proto_script="${PROJECT_ROOT}/scripts/generate-grpc.sh"

    if [ ! -f "${proto_script}" ]; then
        print_warning "Proto generation script not found: ${proto_script}"
        return 0
    fi

    cd "${PROJECT_ROOT}"

    # Run proto generation silently
    if bash "${proto_script}" > /tmp/proto-gen.log 2>&1; then
        print_success "Proto files generated successfully"
    else
        print_warning "Proto generation completed with warnings (check /tmp/proto-gen.log)"
    fi
}

# Function to check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."

    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    # Check if git is installed
    if ! command -v git &> /dev/null; then
        print_warning "Git is not installed. Version tagging will be limited."
    fi

    # Check if Dockerfiles directory exists
    if [ ! -d "${DOCKERFILES_DIR}" ]; then
        print_error "Dockerfiles directory not found: ${DOCKERFILES_DIR}"
        exit 1
    fi

    print_success "All prerequisites met"
}

# Function to check if service is ready
is_service_ready() {
    local service=$1
    local dockerfile="${DOCKERFILES_DIR}/Dockerfile.${service}"

    if [ -f "${dockerfile}" ]; then
        return 0
    else
        return 1
    fi
}

# Function to build a single service image
build_service() {
    local service=$1
    local dockerfile="${DOCKERFILES_DIR}/Dockerfile.${service}"

    # Check if service is ready
    if ! is_service_ready "${service}"; then
        print_warning "Skipping ${service} - Dockerfile not found (not yet implemented)"
        return 0
    fi

    # Get version info
    local git_commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    local build_date=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local image_name="isa-${service}"
    local image_tag="staging-${git_commit}"
    local full_image_name="${image_name}:${image_tag}"

    print_info "Building ${service}..."
    print_info "  Image: ${full_image_name}"
    print_info "  Commit: ${git_commit}"

    # Build the image from project root
    cd "${PROJECT_ROOT}"

    # Create temp file for build output
    local build_log=$(mktemp)

    # Run docker build and capture output
    if docker build \
        --platform ${PLATFORM} \
        -f "${dockerfile}" \
        -t "${full_image_name}" \
        -t "${image_name}:latest" \
        --build-arg SERVICE_NAME="${service}" \
        --build-arg GIT_COMMIT="${git_commit}" \
        --build-arg BUILD_DATE="${build_date}" \
        --build-arg ENVIRONMENT="staging" \
        --progress=plain \
        . > "${build_log}" 2>&1; then
        # Build succeeded - show summary
        grep -E "(CACHED|exporting|naming)" "${build_log}" | grep -v "^#" || true
        print_success "Built ${full_image_name}"
        rm -f "${build_log}"
        return 0
    else
        # Build failed - show errors
        print_error "Build failed. Showing error details:"
        grep -E "(error|ERROR|undefined|failed)" "${build_log}" | tail -20
        print_error "Failed to build ${full_image_name}"
        rm -f "${build_log}"
        return 1
    fi
}

# Function to build all images
build_all_images() {
    print_info "Starting build process for all gRPC services..."
    local failed_services=()
    local skipped_services=()

    for service in "${ALL_SERVICES[@]}"; do
        if ! is_service_ready "${service}"; then
            skipped_services+=("${service}")
            print_warning "Skipping ${service} - not yet implemented"
        elif ! build_service "${service}"; then
            failed_services+=("${service}")
        fi
        echo ""
    done

    if [ ${#skipped_services[@]} -gt 0 ]; then
        print_warning "Skipped services (not yet implemented): ${skipped_services[*]}"
    fi

    if [ ${#failed_services[@]} -gt 0 ]; then
        print_error "Failed to build the following services: ${failed_services[*]}"
        exit 1
    fi

    print_success "All available gRPC service images built successfully"
}

# Function to verify images
verify_images() {
    print_info "Verifying built images..."
    local missing_images=()
    local verified_count=0

    for service in "${ALL_SERVICES[@]}"; do
        if ! is_service_ready "${service}"; then
            continue
        fi

        local image_name="isa-${service}:latest"
        if ! docker image inspect "${image_name}" &> /dev/null; then
            missing_images+=("${image_name}")
        else
            local size=$(docker image inspect "${image_name}" --format='{{.Size}}' | awk '{printf "%.2f MB", $1/1024/1024}')
            print_info "  ✓ ${image_name} (${size})"
            verified_count=$((verified_count + 1))
        fi
    done

    if [ ${#missing_images[@]} -gt 0 ]; then
        print_error "Missing images: ${missing_images[*]}"
        exit 1
    fi

    print_success "All ${verified_count} images verified"
}

# Function to list built images
list_images() {
    print_info "Built gRPC service images:"
    echo ""
    docker images --filter "reference=isa-*-service:staging-*" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
    echo ""
}

# Function to show status
show_status() {
    echo ""
    print_info "=== Service Implementation Status ==="
    echo ""

    print_info "Ready services:"
    for service in "${READY_SERVICES[@]}"; do
        if is_service_ready "${service}"; then
            echo "  ✓ ${service}"
        else
            echo "  ✗ ${service} (Dockerfile missing)"
        fi
    done

    echo ""
    print_warning "Pending implementation:"
    for service in "${PENDING_SERVICES[@]}"; do
        if is_service_ready "${service}"; then
            echo "  ✓ ${service} (ready)"
        else
            echo "  ⏳ ${service}"
        fi
    done
    echo ""
}

# Main execution
main() {
    echo ""
    print_info "=== isA Platform - gRPC Services Staging Build ==="
    echo ""

    # Parse command line arguments
    SPECIFIC_SERVICE=""
    SHOW_STATUS_ONLY=false
    SKIP_PROTO_GEN=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --service)
                SPECIFIC_SERVICE="$2"
                shift 2
                ;;
            --status)
                SHOW_STATUS_ONLY=true
                shift
                ;;
            --skip-proto-gen)
                SKIP_PROTO_GEN=true
                shift
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --service <name>     Build only a specific service"
                echo "  --status             Show service implementation status"
                echo "  --skip-proto-gen     Skip proto file generation"
                echo "  --help               Show this help message"
                echo ""
                echo "Ready services:"
                for service in "${READY_SERVICES[@]}"; do
                    echo "  - ${service}"
                done
                echo ""
                echo "Pending implementation:"
                for service in "${PENDING_SERVICES[@]}"; do
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

    # Show status if requested
    if [ "$SHOW_STATUS_ONLY" = true ]; then
        show_status
        exit 0
    fi

    # Execute build steps
    check_prerequisites

    # Build isA_common Python package
    print_info "Building isA_common Python package..."
    cd "${PROJECT_ROOT}/isA_common" && python3 -m build --wheel > /dev/null 2>&1 && print_success "isA_common package built"

    # Generate proto files first
    if [ "$SKIP_PROTO_GEN" = false ]; then
        generate_proto_files
    else
        print_warning "Skipping proto generation (--skip-proto-gen)"
    fi

    if [ -n "$SPECIFIC_SERVICE" ]; then
        # Build specific service
        if [[ " ${ALL_SERVICES[@]} " =~ " ${SPECIFIC_SERVICE} " ]]; then
            if is_service_ready "${SPECIFIC_SERVICE}"; then
                build_service "${SPECIFIC_SERVICE}"
            else
                print_error "Service ${SPECIFIC_SERVICE} is not yet implemented"
                print_info "Available services: ${READY_SERVICES[*]}"
                exit 1
            fi
        else
            print_error "Unknown service: ${SPECIFIC_SERVICE}"
            echo "Available services: ${ALL_SERVICES[*]}"
            exit 1
        fi
    else
        # Build all available services
        build_all_images
    fi

    verify_images
    list_images
    show_status

    print_success "Build script completed successfully!"
    echo ""
    print_info "Next step: Run ./deployments/scripts/deploy_grpc_staging.sh to deploy the services"
    echo ""
}

# Run main function
main "$@"
