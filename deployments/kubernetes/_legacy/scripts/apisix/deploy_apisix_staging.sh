#!/bin/bash
# Deploy Apache APISIX API Gateway to Staging
# Usage: ./deploy_apisix_staging.sh [--rebuild]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/deployments/compose/Staging/apisix.staging.yml"
LOG_DIR="$PROJECT_ROOT/deployments/compose/Staging/logs"
SSL_DIR="$PROJECT_ROOT/deployments/compose/Staging/ssl"

# Functions
print_header() {
    echo -e "${BLUE}================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Create necessary directories
create_directories() {
    print_header "Creating Required Directories"

    mkdir -p "$LOG_DIR/apisix"
    mkdir -p "$LOG_DIR/dashboard"
    mkdir -p "$SSL_DIR"

    print_success "Directories created"
}

# Check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"

    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    print_success "Docker is installed"

    # Check if Docker Compose is installed
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed"
        exit 1
    fi
    print_success "Docker Compose is installed"

    # Check if jq is installed (needed for route configuration)
    if ! command -v jq &> /dev/null; then
        print_warning "jq is not installed (needed for route configuration)"
        print_info "Install with: brew install jq (macOS) or apt-get install jq (Linux)"
    else
        print_success "jq is installed"
    fi

    # Check if network exists
    if ! docker network inspect staging_staging-network &> /dev/null; then
        print_error "Network staging_staging-network not found"
        print_info "Please run infrastructure.staging.yml first"
        exit 1
    fi
    print_success "Network staging_staging-network exists"

    # Check if Consul is running
    if ! docker ps | grep -q staging-consul; then
        print_warning "Consul is not running - APISIX service discovery won't work"
        print_info "Please start Consul with infrastructure.staging.yml"
    else
        print_success "Consul is running"
    fi
}

# Stop existing containers
stop_containers() {
    print_header "Stopping Existing APISIX Containers"

    if docker-compose -f "$COMPOSE_FILE" ps -q 2>/dev/null | grep -q .; then
        docker-compose -f "$COMPOSE_FILE" down
        print_success "Containers stopped"
    else
        print_info "No running containers found"
    fi
}

# Start services
start_services() {
    print_header "Starting APISIX Services"

    cd "$PROJECT_ROOT"
    docker-compose -f "$COMPOSE_FILE" up -d

    print_success "Services started"
}

# Wait for services to be healthy
wait_for_health() {
    print_header "Waiting for Services to be Healthy"

    local max_wait=90
    local wait_time=0

    # Wait for etcd
    print_info "Waiting for etcd..."
    while [ $wait_time -lt $max_wait ]; do
        if docker inspect --format='{{.State.Health.Status}}' staging-etcd 2>/dev/null | grep -q "healthy"; then
            print_success "etcd is healthy"
            break
        fi
        echo -n "."
        sleep 2
        wait_time=$((wait_time + 2))
    done

    if [ $wait_time -ge $max_wait ]; then
        print_warning "etcd health check timed out"
    fi

    # Wait for APISIX
    wait_time=0
    print_info "Waiting for APISIX..."
    while [ $wait_time -lt $max_wait ]; do
        if curl -s http://localhost:9180/apisix/admin/routes -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" > /dev/null 2>&1; then
            print_success "APISIX is ready"
            break
        fi
        echo -n "."
        sleep 2
        wait_time=$((wait_time + 2))
    done

    echo ""

    if [ $wait_time -ge $max_wait ]; then
        print_error "APISIX failed to start"
        print_info "Checking logs..."
        docker-compose -f "$COMPOSE_FILE" logs --tail=50 apisix
        exit 1
    fi
}

# Configure routes
configure_routes() {
    print_header "Configuring APISIX Routes"

    if [ ! -f "$SCRIPT_DIR/configure_routes.sh" ]; then
        print_error "configure_routes.sh not found"
        return 1
    fi

    # Check if jq is available
    if ! command -v jq &> /dev/null; then
        print_error "jq is required for route configuration"
        print_info "Install with: brew install jq (macOS) or apt-get install jq (Linux)"
        return 1
    fi

    # Run route configuration
    "$SCRIPT_DIR/configure_routes.sh"
}

# Show service status
show_status() {
    print_header "Service Status"

    docker-compose -f "$COMPOSE_FILE" ps

    echo ""
    print_header "APISIX Configuration"

    # Check Consul connectivity
    print_info "Checking Consul connectivity..."
    if docker exec isa-cloud-apisix-staging curl -s http://staging-consul:8500/v1/catalog/services > /dev/null 2>&1; then
        print_success "APISIX can reach Consul"

        # Show discovered services
        echo ""
        print_info "Services discovered from Consul:"
        docker exec isa-cloud-apisix-staging curl -s http://staging-consul:8500/v1/catalog/services | jq -r 'keys[]' | grep -v consul | sort
    else
        print_warning "APISIX cannot reach Consul"
    fi

    echo ""
    print_header "Service Logs (last 20 lines)"

    echo -e "\n${YELLOW}APISIX Logs:${NC}"
    docker-compose -f "$COMPOSE_FILE" logs --tail=20 apisix
}

# Test endpoints
test_endpoints() {
    print_header "Testing APISIX Endpoints"

    # Wait a bit for services to fully start
    sleep 5

    # Test Admin API
    print_info "Testing Admin API..."
    if curl -s http://localhost:9180/apisix/admin/routes -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq -e '.list' > /dev/null 2>&1; then
        print_success "Admin API working"
    else
        print_warning "Admin API may not be working"
    fi

    # Test Prometheus metrics
    print_info "Testing Prometheus metrics..."
    if curl -s http://localhost:9091/apisix/prometheus/metrics | grep -q "apisix"; then
        print_success "Prometheus metrics working"
    else
        print_warning "Prometheus metrics may not be working"
    fi

    # Test Control API
    print_info "Testing Control API..."
    if curl -s http://localhost:9092/v1/healthcheck > /dev/null 2>&1; then
        print_success "Control API working"
    else
        print_warning "Control API may not be working"
    fi

    # Test gateway (will fail if no routes configured)
    print_info "Testing Gateway..."
    http_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/api/v1/billing/stats 2>/dev/null || echo "000")
    if [ "$http_code" = "404" ]; then
        print_warning "Gateway responding but route not found (configure routes with configure_routes.sh)"
    elif [ "$http_code" = "000" ]; then
        print_warning "Gateway may not be responding"
    else
        print_info "Gateway responding with HTTP $http_code"
    fi
}

# Main deployment
main() {
    cd "$PROJECT_ROOT"

    print_header "Apache APISIX Gateway Deployment - Staging"

    check_prerequisites
    create_directories
    stop_containers
    start_services
    wait_for_health
    show_status

    # Only configure routes if jq is available
    if command -v jq &> /dev/null; then
        configure_routes
    else
        print_warning "Skipping route configuration (jq not installed)"
        print_info "Install jq and run: $SCRIPT_DIR/configure_routes.sh"
    fi

    test_endpoints

    print_header "Deployment Complete!"

    echo ""
    print_info "Access points:"
    echo "  HTTP Gateway:       http://localhost"
    echo "  Admin API:          http://localhost:9180"
    echo "  Dashboard:          http://localhost:9010"
    echo "  Prometheus Metrics: http://localhost:9091/apisix/prometheus/metrics"
    echo "  Control API:        http://localhost:9092"
    echo "  Consul UI:          http://localhost:8500"
    echo ""
    print_info "Management commands:"
    echo "  View logs:    docker-compose -f $COMPOSE_FILE logs -f"
    echo "  Stop:         docker-compose -f $COMPOSE_FILE down"
    echo "  Restart:      docker-compose -f $COMPOSE_FILE restart"
    echo "  Status:       docker-compose -f $COMPOSE_FILE ps"
    echo ""
    print_info "Configuration:"
    echo "  Configure routes:  $SCRIPT_DIR/configure_routes.sh"
    echo "  Admin API key:     edd1c9f034335f136f87ad84b625c8f1"
}

# Run main function
main "$@"
