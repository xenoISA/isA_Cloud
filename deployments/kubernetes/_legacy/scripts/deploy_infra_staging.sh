#!/bin/bash

# ============================================
# isA Platform - Infrastructure Staging Deployment Script
# ============================================
# Deploys all infrastructure services for staging environment
# Uses docker-compose file: deployments/compose/Staging/infrastructure.staging.yml
# Requires images built by build_infra_staging.sh

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
COMPOSE_FILE="${PROJECT_ROOT}/deployments/compose/Staging/infrastructure.staging.yml"
PLATFORM="amd64"

# Service list - must match the compose file
SERVICES=(
    "consul"
    "redis"
    "minio"
    "nats"
    "mosquitto"
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

# Function to verify required images exist
verify_images() {
    print_info "Verifying required Docker images..."
    local missing_images=()

    for service in "${SERVICES[@]}"; do
        local image_name="staging-isa-${service}:${PLATFORM}"
        if ! docker image inspect "${image_name}" &> /dev/null; then
            missing_images+=("${image_name}")
        else
            print_info "   ${image_name}"
        fi
    done

    if [ ${#missing_images[@]} -gt 0 ]; then
        print_error "Missing required images: ${missing_images[*]}"
        print_error "Please run ./deployments/scripts/build_infra_staging.sh first"
        exit 1
    fi

    print_success "All required images are available"
}

# Function to stop existing containers
stop_existing() {
    print_info "Stopping existing staging infrastructure containers..."

    cd "${PROJECT_ROOT}"

    if docker compose -f "${COMPOSE_FILE}" ps --quiet 2>/dev/null | grep -q .; then
        docker compose -f "${COMPOSE_FILE}" down
        print_success "Stopped existing containers"
    else
        print_info "No existing containers found"
    fi
}

# Function to deploy with docker-compose
deploy_services() {
    print_info "Deploying infrastructure services with Docker Compose..."

    cd "${PROJECT_ROOT}"

    # Deploy services
    if docker compose -f "${COMPOSE_FILE}" up -d; then
        print_success "Infrastructure services deployed"
    else
        print_error "Failed to deploy services"
        exit 1
    fi
}

# Function to check service health
check_health() {
    print_info "Checking service health..."

    cd "${PROJECT_ROOT}"

    # Wait a bit for containers to start
    sleep 5

    # Check container status
    print_info "Container status:"
    docker compose -f "${COMPOSE_FILE}" ps

    # Wait for health checks
    print_info "Waiting for services to become healthy..."
    local max_wait=120
    local elapsed=0

    while [ $elapsed -lt $max_wait ]; do
        local unhealthy=$(docker compose -f "${COMPOSE_FILE}" ps --format json 2>/dev/null | \
            jq -r 'select(.Health != "healthy" and .Health != "") | .Service' 2>/dev/null || true)

        if [ -z "$unhealthy" ]; then
            print_success "All services are healthy"
            return 0
        fi

        sleep 5
        elapsed=$((elapsed + 5))
        print_info "Waiting... (${elapsed}s/${max_wait}s)"
    done

    print_warning "Some services may not be fully healthy yet. Check manually with: docker compose -f ${COMPOSE_FILE} ps"
}

# Function to show logs
show_logs() {
    print_info "Recent logs from services:"
    cd "${PROJECT_ROOT}"
    docker compose -f "${COMPOSE_FILE}" logs --tail=20
}

# Function to test service connectivity
test_connectivity() {
    print_info "Testing service connectivity..."

    # Test Consul
    if curl -sf http://localhost:8500/v1/status/leader >/dev/null 2>&1; then
        print_success "   Consul is accessible"
    else
        print_warning "   Consul is not responding"
    fi

    # Test Redis
    if docker exec staging-redis redis-cli ping >/dev/null 2>&1; then
        print_success "   Redis is accessible"
    else
        print_warning "   Redis is not responding"
    fi

    # Test MinIO
    if curl -sf http://localhost:9000/minio/health/live >/dev/null 2>&1; then
        print_success "   MinIO is accessible"
    else
        print_warning "   MinIO is not responding"
    fi

    # Test Loki
    if curl -sf http://localhost:3100/ready >/dev/null 2>&1; then
        print_success "   Loki is accessible"
    else
        print_warning "   Loki is not responding"
    fi

    # Test Grafana
    if curl -sf http://localhost:3000/api/health >/dev/null 2>&1; then
        print_success "   Grafana is accessible"
    else
        print_warning "   Grafana is not responding"
    fi
}

# Function to print deployment info
print_deployment_info() {
    echo ""
    print_success "=== Staging Infrastructure Deployment Complete ==="
    echo ""
    print_info "Services deployed:"
    for service in "${SERVICES[@]}"; do
        echo "  - ${service}"
    done
    echo ""
    print_info "Access points:"
    echo "  Consul:     http://localhost:8500"
    echo "  Redis:      localhost:6379 (password: staging_redis_2024)"
    echo "  MinIO:      http://localhost:9000 (console: http://localhost:9001)"
    echo "              Credentials: minioadmin / minioadmin"
    echo "  NATS:       nats://localhost:4222"
    echo "              Monitoring: http://localhost:8322"
    echo "  MQTT:       mqtt://localhost:1883"
    echo "              WebSocket: ws://localhost:9003"
    echo "  Loki:       http://localhost:3100"
    echo "  Grafana:    http://localhost:3000"
    echo "              Credentials: admin / staging_admin_2024"
    echo ""
    print_info "Useful commands:"
    echo "  View logs:     docker compose -f ${COMPOSE_FILE} logs -f [service]"
    echo "  Check status:  docker compose -f ${COMPOSE_FILE} ps"
    echo "  Stop all:      docker compose -f ${COMPOSE_FILE} down"
    echo "  Restart:       docker compose -f ${COMPOSE_FILE} restart [service]"
    echo ""
}

# Main execution
main() {
    echo ""
    print_info "=== isA Platform - Staging Infrastructure Deployment ==="
    echo ""

    # Parse command line arguments
    SKIP_VERIFY=false
    SKIP_HEALTH=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-verify)
                SKIP_VERIFY=true
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
                echo "  --skip-verify   Skip image verification"
                echo "  --skip-health   Skip health checks"
                echo "  --logs          Show recent logs and exit"
                echo "  --help          Show this help message"
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

    if [ "$SKIP_VERIFY" = false ]; then
        verify_images
    else
        print_warning "Skipping image verification"
    fi

    stop_existing
    deploy_services

    if [ "$SKIP_HEALTH" = false ]; then
        check_health
        test_connectivity
    else
        print_warning "Skipping health checks"
    fi

    print_deployment_info

    print_success "Deployment script completed successfully!"
}

# Run main function
main "$@"
