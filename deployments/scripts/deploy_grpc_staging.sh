#!/bin/bash

# ============================================
# isA Platform - gRPC Services Staging Deployment Script
# ============================================
# Deploys all gRPC services for staging environment
# Uses docker-compose file: deployments/compose/grpc-services.yml
# Requires images built by build_grpc_staging.sh
# Requires infrastructure services running (from deploy_infra_staging.sh)

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
COMPOSE_FILE="${PROJECT_ROOT}/deployments/compose/grpc-services.yml"

# gRPC services status
READY_SERVICES=(
    "minio-service"      # Port 50051
    "duckdb-service"     # Port 50052
    "mqtt-service"       # Port 50053
    "loki-service"       # Port 50054
    "redis-service"      # Port 50055
    "nats-service"       # Port 50056
    "supabase-service"   # Port 50057
)

PENDING_SERVICES=(
    # All services are now ready!
)

# Infrastructure dependencies
INFRA_SERVICES=(
    "staging-consul"
    "staging-redis"
    "staging-minio"
    "staging-nats"
    "staging-mosquitto"
    "staging-loki"
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

    # Check if Docker Compose is available
    if ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not available. Please install Docker Compose."
        exit 1
    fi

    # Check if compose file exists
    if [ ! -f "${COMPOSE_FILE}" ]; then
        print_error "Compose file not found: ${COMPOSE_FILE}"
        exit 1
    fi

    print_success "All prerequisites met"
}

# Function to check infrastructure services
check_infrastructure() {
    print_info "Checking infrastructure services..."
    local missing_services=()

    for service in "${INFRA_SERVICES[@]}"; do
        if ! docker ps --format '{{.Names}}' | grep -q "^${service}$"; then
            missing_services+=("${service}")
        else
            print_info "   ${service} is running"
        fi
    done

    if [ ${#missing_services[@]} -gt 0 ]; then
        print_error "Missing infrastructure services: ${missing_services[*]}"
        print_error "Please run ./deployments/scripts/deploy_infra_staging.sh first"
        exit 1
    fi

    print_success "All required infrastructure services are running"
}

# Function to check if service image exists
check_service_image() {
    local service=$1
    local image_name="isa-${service}:latest"

    if docker image inspect "${image_name}" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# Function to verify required images exist
verify_images() {
    print_info "Verifying required Docker images..."
    local missing_images=()
    local available_count=0

    for service in "${READY_SERVICES[@]}"; do
        local image_name="isa-${service}:latest"
        if ! docker image inspect "${image_name}" &> /dev/null; then
            missing_images+=("${image_name}")
        else
            print_info "   ${image_name}"
            available_count=$((available_count + 1))
        fi
    done

    # Check pending services (warn if missing)
    for service in "${PENDING_SERVICES[@]}"; do
        local image_name="isa-${service}:latest"
        if docker image inspect "${image_name}" &> /dev/null; then
            print_success "   ${image_name} (newly available!)"
            available_count=$((available_count + 1))
        else
            print_warning "   ⏳ ${image_name} (not yet implemented)"
        fi
    done

    if [ ${#missing_images[@]} -gt 0 ]; then
        print_warning "Missing images (will skip): ${missing_images[*]}"
        print_warning "Run ./deployments/scripts/build_grpc_staging.sh to build missing images"
    fi

    if [ $available_count -eq 0 ]; then
        print_error "No images available for deployment"
        print_error "Please run ./deployments/scripts/build_grpc_staging.sh first"
        exit 1
    fi

    print_success "${available_count} images verified and ready for deployment"
}

# Function to stop existing containers
stop_existing() {
    local specific_service=$1

    cd "${PROJECT_ROOT}"

    if [ -n "$specific_service" ]; then
        # Only stop the specific service
        # Convert service name to compose service name
        local compose_service="$specific_service"
        if [[ ! "$compose_service" =~ -grpc-service$ ]]; then
            compose_service="${specific_service%-service}-grpc-service"
        fi

        print_info "Stopping existing ${specific_service} container..."

        if docker compose -f "${COMPOSE_FILE}" ps --quiet "${compose_service}" 2>/dev/null | grep -q .; then
            docker compose -f "${COMPOSE_FILE}" stop "${compose_service}"
            docker compose -f "${COMPOSE_FILE}" rm -f "${compose_service}"
            print_success "Stopped and removed ${specific_service} container"
        else
            print_info "No existing ${specific_service} container found"
        fi
    else
        # Stop all services
        print_info "Stopping all existing gRPC service containers..."

        if docker compose -f "${COMPOSE_FILE}" ps --quiet 2>/dev/null | grep -q .; then
            docker compose -f "${COMPOSE_FILE}" down
            print_success "Stopped all existing containers"
        else
            print_info "No existing containers found"
        fi
    fi
}

# Function to deploy with docker-compose
deploy_services() {
    local specific_service=$1

    if [ -n "$specific_service" ]; then
        print_info "Deploying ${specific_service} with Docker Compose..."
    else
        print_info "Deploying gRPC services with Docker Compose..."
    fi

    cd "${PROJECT_ROOT}"

    # Deploy services (will only start services with available images, no building)
    if [ -n "$specific_service" ]; then
        # Convert service name to compose service name
        # Handle both formats: "nats-service" -> "nats-grpc-service" OR "nats-grpc-service" -> "nats-grpc-service"
        local compose_service="$specific_service"
        if [[ ! "$compose_service" =~ -grpc-service$ ]]; then
            # Remove -service suffix and add -grpc-service
            compose_service="${specific_service%-service}-grpc-service"
        fi

        if docker compose -f "${COMPOSE_FILE}" up -d --no-build --remove-orphans "${compose_service}" 2>&1; then
            print_success "${specific_service} deployed"
        else
            print_error "Failed to deploy ${specific_service}"
            exit 1
        fi
    else
        if docker compose -f "${COMPOSE_FILE}" up -d --no-build --remove-orphans 2>&1; then
            print_success "gRPC services deployed"
        else
            print_error "Failed to deploy services"
            exit 1
        fi
    fi
}

# Function to check service health
check_health() {
    print_info "Checking service health..."

    cd "${PROJECT_ROOT}"

    # Wait a bit for containers to start
    sleep 10

    # Check container status
    print_info "Container status:"
    docker compose -f "${COMPOSE_FILE}" ps

    # Wait for health checks
    print_info "Waiting for services to become healthy..."
    local max_wait=120
    local elapsed=0

    while [ $elapsed -lt $max_wait ]; do
        local unhealthy=$(docker compose -f "${COMPOSE_FILE}" ps --format json 2>/dev/null | \
            jq -r 'select(.Health != "healthy" and .Health != "" and .Health != null) | .Service' 2>/dev/null || true)

        if [ -z "$unhealthy" ]; then
            print_success "All running services are healthy"
            return 0
        fi

        sleep 5
        elapsed=$((elapsed + 5))
        print_info "Waiting... (${elapsed}s/${max_wait}s)"
    done

    print_warning "Some services may not be fully healthy yet. Check manually with: docker compose -f ${COMPOSE_FILE} ps"
}

# Function to test gRPC connectivity
test_grpc_connectivity() {
    print_info "Testing gRPC service connectivity..."

    # Test each service port using simple array with colon separator
    local services=(
        "MinIO:50051"
        "DuckDB:50052"
        "MQTT:50053"
        "Loki:50054"
        "Redis:50055"
        "NATS:50056"
        "Supabase:50057"
    )

    for service_port in "${services[@]}"; do
        local service_name="${service_port%%:*}"
        local port="${service_port##*:}"
        if nc -z localhost $port 2>/dev/null; then
            print_success "  ✓ ${service_name} gRPC Service (port ${port}) is accessible"
        else
            print_warning "  ✗ ${service_name} gRPC Service (port ${port}) is not responding"
        fi
    done
}

# Function to check Consul registration
check_consul_registration() {
    print_info "Checking Consul service registration..."

    if ! command -v curl &> /dev/null; then
        print_warning "curl not found, skipping Consul check"
        return
    fi

    # Wait a bit for services to register
    sleep 5

    local services=$(curl -s http://localhost:8500/v1/catalog/services 2>/dev/null | jq -r 'keys[]' 2>/dev/null || echo "")

    if [ -n "$services" ]; then
        print_info "Registered services in Consul:"
        echo "$services" | grep -i "grpc\|service" | while read -r svc; do
            print_info "  - ${svc}"
        done
    else
        print_warning "Could not retrieve Consul service list"
    fi
}

# Function to show logs
show_logs() {
    print_info "Recent logs from services:"
    cd "${PROJECT_ROOT}"
    docker compose -f "${COMPOSE_FILE}" logs --tail=20
}

# Function to print deployment info
print_deployment_info() {
    echo ""
    print_success "=== gRPC Services Staging Deployment Complete ==="
    echo ""

    print_info "Deployed services:"
    for service in "${READY_SERVICES[@]}"; do
        echo "   ${service}"
    done

    echo ""
    print_warning "Pending implementation (need Dockerfiles):"
    for service in "${PENDING_SERVICES[@]}"; do
        if check_service_image "${service}"; then
            echo "   ${service} (newly deployed!)"
        else
            echo "  � ${service}"
        fi
    done

    echo ""
    print_info "gRPC Endpoints:"
    echo "  MinIO Service:    localhost:50051"
    echo "  DuckDB Service:   localhost:50052"
    echo "  MQTT Service:     localhost:50053"
    echo "  NATS Service:     localhost:50056"
    echo "  Supabase Service: localhost:50057"
    echo ""
    echo "  Pending:"
    echo "  Loki Service:     localhost:50054 �"
    echo "  Redis Service:    localhost:50055 �"
    echo ""
    print_info "Service Discovery:"
    echo "  Consul:           http://localhost:8500"
    echo ""
    print_info "Useful commands:"
    echo "  View logs:        docker compose -f ${COMPOSE_FILE} logs -f [service]"
    echo "  Check status:     docker compose -f ${COMPOSE_FILE} ps"
    echo "  Stop all:         docker compose -f ${COMPOSE_FILE} down"
    echo "  Restart service:  docker compose -f ${COMPOSE_FILE} restart [service]"
    echo ""
    print_info "Test gRPC with grpcurl:"
    echo "  grpcurl -plaintext localhost:50051 list"
    echo "  grpcurl -plaintext localhost:50052 list"
    echo "  grpcurl -plaintext localhost:50053 list"
    echo ""
}

# Main execution
main() {
    echo ""
    print_info "=== isA Platform - gRPC Services Staging Deployment ==="
    echo ""

    # Parse command line arguments
    SKIP_VERIFY=false
    SKIP_INFRA_CHECK=false
    SKIP_HEALTH=false
    SPECIFIC_SERVICE=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --service)
                SPECIFIC_SERVICE="$2"
                shift 2
                ;;
            --skip-verify)
                SKIP_VERIFY=true
                shift
                ;;
            --skip-infra-check)
                SKIP_INFRA_CHECK=true
                shift
                ;;
            --skip-health)
                SKIP_HEALTH=true
                shift
                ;;
            --logs)
                show_logs
                exit 0
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --service <name>    Deploy only a specific service"
                echo "  --skip-verify       Skip image verification"
                echo "  --skip-infra-check  Skip infrastructure check"
                echo "  --skip-health       Skip health checks"
                echo "  --logs              Show recent logs and exit"
                echo "  --help              Show this help message"
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done

    # Execute deployment steps
    check_prerequisites

    if [ "$SKIP_INFRA_CHECK" = false ]; then
        check_infrastructure
    else
        print_warning "Skipping infrastructure check"
    fi

    if [ "$SKIP_VERIFY" = false ]; then
        verify_images
    else
        print_warning "Skipping image verification"
    fi

    stop_existing "$SPECIFIC_SERVICE"
    deploy_services "$SPECIFIC_SERVICE"

    if [ "$SKIP_HEALTH" = false ]; then
        check_health
        test_grpc_connectivity
        check_consul_registration
    else
        print_warning "Skipping health checks"
    fi

    print_deployment_info

    print_success "Deployment script completed successfully!"
}

# Run main function
main "$@"
