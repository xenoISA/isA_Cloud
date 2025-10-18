#!/bin/bash
# Deploy OpenResty Edge Layer + Gateway to Staging
# Usage: ./deploy_edge_staging.sh [--rebuild]

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
COMPOSE_FILE="$PROJECT_ROOT/deployments/compose/Staging/gateway.staging.yml"
LOG_DIR="$PROJECT_ROOT/deployments/compose/Staging/logs"
SSL_DIR="$PROJECT_ROOT/deployments/compose/Staging/ssl"
STATIC_DIR="$PROJECT_ROOT/deployments/compose/Staging/static"

# Functions
print_header() {
    echo -e "${BLUE}================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================================${NC}"
}

print_success() {
    echo -e "${GREEN} $1${NC}"
}

print_error() {
    echo -e "${RED} $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}  $1${NC}"
}

print_info() {
    echo -e "${BLUE}9 $1${NC}"
}

# Create necessary directories
create_directories() {
    print_header "Creating Required Directories"

    mkdir -p "$LOG_DIR/openresty"
    mkdir -p "$LOG_DIR/gateway"
    mkdir -p "$SSL_DIR"
    mkdir -p "$STATIC_DIR"

    print_success "Directories created"
}

# Setup SSL certificates
setup_ssl() {
    print_header "Setting Up SSL Certificates"

    if [ ! -f "$SSL_DIR/cert.pem" ] || [ ! -f "$SSL_DIR/key.pem" ]; then
        print_warning "SSL certificates not found. Generating self-signed certificates..."

        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "$SSL_DIR/key.pem" \
            -out "$SSL_DIR/cert.pem" \
            -subj "/C=US/ST=State/L=City/O=isA_Cloud/OU=IT/CN=isa-cloud-staging" \
            2>/dev/null

        print_success "Self-signed SSL certificates generated"
        print_warning "For production, replace with real certificates from Let's Encrypt"
    else
        print_success "SSL certificates found"
    fi
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

    # Check if network exists
    if ! docker network inspect isa-cloud-network &> /dev/null; then
        print_warning "Network isa-cloud-network not found, creating..."
        docker network create isa-cloud-network
        print_success "Network created"
    else
        print_success "Network isa-cloud-network exists"
    fi
}

# Stop existing containers
stop_containers() {
    print_header "Stopping Existing Containers"

    if docker-compose -f "$COMPOSE_FILE" ps -q 2>/dev/null | grep -q .; then
        docker-compose -f "$COMPOSE_FILE" down
        print_success "Containers stopped"
    else
        print_info "No running containers found"
    fi
}

# Build images
build_images() {
    print_header "Building Docker Images"

    local rebuild_flag=""
    if [ "$1" == "--rebuild" ]; then
        rebuild_flag="--no-cache"
        print_info "Rebuilding images from scratch (no cache)"
    fi

    docker-compose -f "$COMPOSE_FILE" build $rebuild_flag

    print_success "Images built successfully"
}

# Start services
start_services() {
    print_header "Starting Services"

    docker-compose -f "$COMPOSE_FILE" up -d

    print_success "Services started"
}

# Wait for services to be healthy
wait_for_health() {
    print_header "Waiting for Services to be Healthy"

    local max_wait=60
    local wait_time=0

    while [ $wait_time -lt $max_wait ]; do
        # Check if gateway is healthy
        if docker inspect --format='{{.State.Health.Status}}' isa-cloud-gateway-staging 2>/dev/null | grep -q "healthy"; then
            print_success "Gateway is healthy"
            break
        fi

        echo -n "."
        sleep 2
        wait_time=$((wait_time + 2))
    done

    echo ""

    if [ $wait_time -ge $max_wait ]; then
        print_warning "Gateway health check timed out"
    fi

    # Check if OpenResty is healthy
    wait_time=0
    while [ $wait_time -lt $max_wait ]; do
        if docker inspect --format='{{.State.Health.Status}}' isa-cloud-openresty-staging 2>/dev/null | grep -q "healthy"; then
            print_success "OpenResty is healthy"
            break
        fi

        echo -n "."
        sleep 2
        wait_time=$((wait_time + 2))
    done

    echo ""

    if [ $wait_time -ge $max_wait ]; then
        print_warning "OpenResty health check timed out"
    fi
}

# Show service status
show_status() {
    print_header "Service Status"

    docker-compose -f "$COMPOSE_FILE" ps

    echo ""
    print_header "Service Logs (last 20 lines)"

    echo -e "\n${YELLOW}OpenResty Logs:${NC}"
    docker-compose -f "$COMPOSE_FILE" logs --tail=20 openresty

    echo -e "\n${YELLOW}Gateway Logs:${NC}"
    docker-compose -f "$COMPOSE_FILE" logs --tail=20 gateway
}

# Test endpoints
test_endpoints() {
    print_header "Testing Endpoints"

    # Wait a bit for services to fully start
    sleep 5

    # Test HTTP redirect
    print_info "Testing HTTP to HTTPS redirect..."
    if curl -s -o /dev/null -w "%{http_code}" http://localhost/ | grep -q "301"; then
        print_success "HTTP redirect working"
    else
        print_warning "HTTP redirect may not be working"
    fi

    # Test HTTPS health endpoint
    print_info "Testing HTTPS health endpoint..."
    if curl -k -s https://localhost/health | grep -q "healthy"; then
        print_success "Health endpoint working"
    else
        print_warning "Health endpoint may not be working"
    fi

    # Test API endpoint
    print_info "Testing API endpoint..."
    if curl -k -s https://localhost/api/v1/gateway/services | grep -q "services"; then
        print_success "API endpoint working"
    else
        print_warning "API endpoint may not be working"
    fi
}

# Main deployment
main() {
    cd "$PROJECT_ROOT"

    print_header "isA_Cloud Edge Layer Deployment - Staging"

    check_prerequisites
    create_directories
    setup_ssl
    stop_containers
    build_images "$1"
    start_services
    wait_for_health
    show_status
    test_endpoints

    print_header "Deployment Complete!"

    echo ""
    print_info "Access points:"
    echo "  HTTP:  http://localhost"
    echo "  HTTPS: https://localhost"
    echo "  Consul UI: http://localhost:8500"
    echo ""
    print_info "Management commands:"
    echo "  View logs:    docker-compose -f $COMPOSE_FILE logs -f"
    echo "  Stop:         docker-compose -f $COMPOSE_FILE down"
    echo "  Restart:      docker-compose -f $COMPOSE_FILE restart"
    echo "  Status:       docker-compose -f $COMPOSE_FILE ps"
}

# Run main function
main "$@"
