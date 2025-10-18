#!/bin/bash
# Management Script for OpenResty Edge Layer
# Provides convenient commands for managing the edge layer

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/deployments/compose/Staging/gateway.staging.yml"

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

print_info() {
    echo -e "${BLUE}9 $1${NC}"
}

# Show usage
usage() {
    cat << EOF
Usage: $0 <command> [options]

Commands:
    start           Start all edge layer services
    stop            Stop all edge layer services
    restart         Restart all edge layer services
    status          Show service status
    logs            View logs (use -f to follow)
    reload          Reload OpenResty configuration without restart
    test-config     Test OpenResty configuration
    shell           Open shell in OpenResty container
    stats           Show traffic and performance stats
    cache-clear     Clear response cache
    cache-stats     Show cache statistics
    block-ip        Block an IP address
    unblock-ip      Unblock an IP address
    list-blocked    List all blocked IPs
    health          Check health of all services

Options:
    -f, --follow    Follow logs (for logs command)
    -n <num>        Number of log lines to show (default: 100)
    <ip>            IP address (for block-ip/unblock-ip commands)

Examples:
    $0 start
    $0 logs -f
    $0 logs -n 50
    $0 reload
    $0 block-ip 192.168.1.100
    $0 cache-stats

EOF
    exit 1
}

# Start services
start_services() {
    print_header "Starting Edge Layer Services"
    docker-compose -f "$COMPOSE_FILE" up -d
    print_success "Services started"
}

# Stop services
stop_services() {
    print_header "Stopping Edge Layer Services"
    docker-compose -f "$COMPOSE_FILE" down
    print_success "Services stopped"
}

# Restart services
restart_services() {
    print_header "Restarting Edge Layer Services"
    docker-compose -f "$COMPOSE_FILE" restart
    print_success "Services restarted"
}

# Show status
show_status() {
    print_header "Service Status"
    docker-compose -f "$COMPOSE_FILE" ps
}

# View logs
view_logs() {
    local follow_flag=""
    local lines=100

    while [[ $# -gt 0 ]]; do
        case $1 in
            -f|--follow)
                follow_flag="-f"
                shift
                ;;
            -n)
                lines="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    if [ -n "$follow_flag" ]; then
        docker-compose -f "$COMPOSE_FILE" logs -f --tail="$lines"
    else
        docker-compose -f "$COMPOSE_FILE" logs --tail="$lines"
    fi
}

# Reload OpenResty configuration
reload_config() {
    print_header "Reloading OpenResty Configuration"

    # Test configuration first
    if ! docker exec isa-cloud-openresty-staging /usr/local/openresty/bin/openresty -t; then
        print_error "Configuration test failed!"
        exit 1
    fi

    # Reload
    docker exec isa-cloud-openresty-staging /usr/local/openresty/bin/openresty -s reload

    print_success "Configuration reloaded"
}

# Test configuration
test_config() {
    print_header "Testing OpenResty Configuration"
    docker exec isa-cloud-openresty-staging /usr/local/openresty/bin/openresty -t
}

# Open shell
open_shell() {
    print_info "Opening shell in OpenResty container (exit with Ctrl+D)"
    docker exec -it isa-cloud-openresty-staging /bin/sh
}

# Show stats
show_stats() {
    print_header "Traffic and Performance Statistics"

    # Get container stats
    docker stats --no-stream isa-cloud-openresty-staging isa-cloud-gateway-staging

    echo ""
    print_header "Request Metrics"

    # Parse access logs for basic stats
    docker exec isa-cloud-openresty-staging sh -c '
        if [ -f /var/log/nginx/access.log ]; then
            echo "Total Requests: $(wc -l < /var/log/nginx/access.log)"
            echo "Status Code Distribution:"
            awk "{print \$9}" /var/log/nginx/access.log | sort | uniq -c | sort -rn | head -10
            echo ""
            echo "Top 10 Requested Paths:"
            awk "{print \$7}" /var/log/nginx/access.log | sort | uniq -c | sort -rn | head -10
        else
            echo "No access log found"
        fi
    '
}

# Clear cache
clear_cache() {
    print_header "Clearing Response Cache"

    # Clear cache via Redis
    docker exec staging-redis redis-cli KEYS "cache:*" | xargs -r docker exec -i staging-redis redis-cli DEL

    # Clear nginx cache directory
    docker exec isa-cloud-openresty-staging sh -c 'rm -rf /var/cache/nginx/api/*'

    print_success "Cache cleared"
}

# Show cache stats
cache_stats() {
    print_header "Cache Statistics"

    docker exec staging-redis redis-cli INFO stats | grep -E "keyspace_hits|keyspace_misses"

    echo ""
    echo "Cached entries:"
    docker exec staging-redis redis-cli KEYS "cache:*" | wc -l
}

# Block IP
block_ip() {
    local ip="$1"

    if [ -z "$ip" ]; then
        print_error "IP address required"
        echo "Usage: $0 block-ip <ip_address>"
        exit 1
    fi

    print_info "Blocking IP: $ip"

    docker exec staging-redis redis-cli SETEX "blocked:ip:$ip" 3600 "Manually blocked"

    print_success "IP $ip blocked for 1 hour"
}

# Unblock IP
unblock_ip() {
    local ip="$1"

    if [ -z "$ip" ]; then
        print_error "IP address required"
        echo "Usage: $0 unblock-ip <ip_address>"
        exit 1
    fi

    print_info "Unblocking IP: $ip"

    docker exec staging-redis redis-cli DEL "blocked:ip:$ip"

    print_success "IP $ip unblocked"
}

# List blocked IPs
list_blocked() {
    print_header "Blocked IP Addresses"

    docker exec staging-redis redis-cli KEYS "blocked:ip:*" | while read key; do
        if [ -n "$key" ]; then
            ip=$(echo "$key" | sed 's/blocked:ip://')
            reason=$(docker exec staging-redis redis-cli GET "$key")
            ttl=$(docker exec staging-redis redis-cli TTL "$key")
            echo "IP: $ip | Reason: $reason | TTL: ${ttl}s"
        fi
    done
}

# Health check
health_check() {
    print_header "Health Check"

    # Check OpenResty
    if docker exec isa-cloud-openresty-staging curl -f http://localhost/health > /dev/null 2>&1; then
        print_success "OpenResty is healthy"
    else
        print_error "OpenResty is unhealthy"
    fi

    # Check Gateway
    if docker exec isa-cloud-gateway-staging wget -q --spider http://localhost:8000/health; then
        print_success "Gateway is healthy"
    else
        print_error "Gateway is unhealthy"
    fi

    # Check Redis
    if docker exec staging-redis redis-cli ping > /dev/null 2>&1; then
        print_success "Redis is healthy"
    else
        print_error "Redis is unhealthy"
    fi

    # Check Consul
    if docker exec staging-consul consul members > /dev/null 2>&1; then
        print_success "Consul is healthy"
    else
        print_error "Consul is unhealthy"
    fi
}

# Main
main() {
    if [ $# -eq 0 ]; then
        usage
    fi

    cd "$PROJECT_ROOT"

    case "$1" in
        start)
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            restart_services
            ;;
        status)
            show_status
            ;;
        logs)
            shift
            view_logs "$@"
            ;;
        reload)
            reload_config
            ;;
        test-config)
            test_config
            ;;
        shell)
            open_shell
            ;;
        stats)
            show_stats
            ;;
        cache-clear)
            clear_cache
            ;;
        cache-stats)
            cache_stats
            ;;
        block-ip)
            block_ip "$2"
            ;;
        unblock-ip)
            unblock_ip "$2"
            ;;
        list-blocked)
            list_blocked
            ;;
        health)
            health_check
            ;;
        *)
            print_error "Unknown command: $1"
            usage
            ;;
    esac
}

main "$@"
