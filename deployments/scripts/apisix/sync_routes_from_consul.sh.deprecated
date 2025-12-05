#!/bin/bash
# Dynamic Route Synchronization from Consul to APISIX
#
# This script automatically creates/updates/deletes APISIX routes based on
# Consul service registry metadata
#
# Services must have metadata in Consul to be auto-configured:
#   meta.api_path: The URI path (e.g., "/api/v1/billing")
#   meta.auth_required: Whether authentication is required ("true"/"false")
#   meta.rate_limit: Rate limit per minute (default: 100)
#
# Usage:
#   ./sync_routes_from_consul.sh              # Run once
#   watch -n 10 ./sync_routes_from_consul.sh  # Run every 10 seconds

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
CONSUL_URL="${CONSUL_URL:-http://localhost:8500}"
APISIX_ADMIN_URL="${APISIX_ADMIN_URL:-http://localhost:9180}"
ADMIN_KEY="${APISIX_ADMIN_KEY:-edd1c9f034335f136f87ad84b625c8f1}"

# Functions
print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ $1${NC}"; }

# Get service metadata from Consul
get_service_meta() {
    local service_name=$1

    # Use Catalog API instead of Health API (more reliable when health checks are flaky)
    local meta=$(curl -s "${CONSUL_URL}/v1/catalog/service/${service_name}" | \
        jq '.[0].ServiceMeta // {}')

    echo "$meta"
}

# Create or update route in APISIX
create_or_update_route() {
    local service_name=$1
    local api_path=$2
    local auth_required=${3:-false}
    local rate_limit=${4:-100}

    local route_name="${service_name}_route"
    local uri_pattern="${api_path}/*"

    print_info "Syncing route: $route_name ($uri_pattern -> $service_name)"

    # Build plugins
    local plugins=$(cat <<EOF
{
    "cors": {
        "allow_origins": "*",
        "allow_methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS,HEAD",
        "allow_headers": "DNT,X-CustomHeader,Keep-Alive,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Authorization,X-API-Key,X-Request-ID",
        "expose_headers": "X-Request-ID,X-RateLimit-Limit,X-RateLimit-Remaining,X-RateLimit-Reset",
        "max_age": 86400,
        "allow_credentials": true
    },
    "limit-count": {
        "count": ${rate_limit},
        "time_window": 60,
        "rejected_code": 429,
        "rejected_msg": "Rate limit exceeded",
        "policy": "local"
    },
    "request-id": {
        "algorithm": "uuid",
        "include_in_response": true
    },
    "prometheus": {}
}
EOF
)

    # Add JWT auth if required
    if [ "$auth_required" = "true" ]; then
        plugins=$(echo "$plugins" | jq '. + {"jwt-auth": {}}')
    fi

    # Get service instances from Consul Catalog API (more reliable than Health API)
    # Note: Catalog API doesn't check health status, but that's okay since we resolve to IPs
    local instances=$(curl -s "${CONSUL_URL}/v1/catalog/service/${service_name}")

    # Extract host:port pairs and resolve to IP
    # Note: Catalog API uses ServiceAddress/ServicePort, not Service.Address/Service.Port
    local nodes="{}"
    while IFS= read -r line; do
        if [ -z "$line" ]; then continue; fi

        local host=$(echo "$line" | jq -r '.ServiceAddress')
        local port=$(echo "$line" | jq -r '.ServicePort')

        # Resolve hostname to IP using Docker network inspect
        local ip=""

        # Try Docker network inspect first (most reliable for Docker services)
        if command -v docker &> /dev/null; then
            ip=$(docker network inspect staging_staging-network 2>/dev/null | \
                jq -r ".[0].Containers | to_entries[] | select(.value.Name == \"$host\") | .value.IPv4Address" | \
                cut -d'/' -f1)
        fi

        # Fallback to DNS resolution
        if [ -z "$ip" ] || [ "$ip" = "null" ]; then
            if command -v getent &> /dev/null; then
                ip=$(getent hosts "$host" 2>/dev/null | awk '{print $1}' | head -n1)
            elif command -v nslookup &> /dev/null; then
                ip=$(nslookup "$host" 2>/dev/null | awk '/^Address: / { print $2 }' | grep -v '#' | head -n1)
            fi
        fi

        # Use IP if resolved, otherwise skip this instance
        if [ -n "$ip" ] && [ "$ip" != "null" ]; then
            nodes=$(echo "$nodes" | jq ". + {\"$ip:$port\": 1}")
        else
            print_warning "Could not resolve $host to IP, skipping"
        fi
    done < <(echo "$instances" | jq -c '.[]')

    # Create/Update route with resolved IPs
    local response=$(curl -s -w "\n%{http_code}" -X PUT \
        "${APISIX_ADMIN_URL}/apisix/admin/routes/${route_name}" \
        -H "X-API-KEY: ${ADMIN_KEY}" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"${route_name}\",
            \"desc\": \"Auto-synced from Consul service: ${service_name}\",
            \"uri\": \"${uri_pattern}\",
            \"upstream\": {
                \"type\": \"roundrobin\",
                \"nodes\": ${nodes},
                \"timeout\": {
                    \"connect\": 6,
                    \"send\": 6,
                    \"read\": 10
                },
                \"keepalive_pool\": {
                    \"size\": 320,
                    \"idle_timeout\": 60,
                    \"requests\": 1000
                }
            },
            \"plugins\": ${plugins},
            \"enable_websocket\": true,
            \"status\": 1,
            \"labels\": {
                \"managed_by\": \"consul-sync\",
                \"service_name\": \"${service_name}\",
                \"sync_timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
            }
        }")

    local http_code=$(echo "$response" | tail -n1)

    if [[ "$http_code" =~ ^20[0-9]$ ]]; then
        print_success "Route synced: $route_name"
        return 0
    else
        print_error "Failed to sync route: $route_name (HTTP $http_code)"
        return 1
    fi
}

# Delete route from APISIX
delete_route() {
    local route_name=$1

    curl -s -X DELETE \
        "${APISIX_ADMIN_URL}/apisix/admin/routes/${route_name}" \
        -H "X-API-KEY: ${ADMIN_KEY}" > /dev/null

    print_success "Deleted route: $route_name"
}

# Main sync logic
main() {
    print_info "🔄 Starting Consul → APISIX route synchronization..."
    echo ""

    # Get all services from Consul
    local services=$(curl -s "${CONSUL_URL}/v1/catalog/services")

    if [ $? -ne 0 ]; then
        print_error "Failed to connect to Consul at ${CONSUL_URL}"
        exit 1
    fi

    local synced=0
    local skipped=0
    local failed=0

    # Track processed services
    declare -a processed_services=()

    # Process each service
    for service_name in $(echo "$services" | jq -r 'keys[]'); do
        # Skip Consul itself
        if [ "$service_name" = "consul" ]; then
            continue
        fi

        # Get service metadata
        local meta=$(get_service_meta "$service_name")
        # Support both api_path and base_path
        local api_path=$(echo "$meta" | jq -r '.api_path // .base_path // empty')

        # If no api_path/base_path, try to extract from 'api' field (e.g., mcp_service)
        if [ -z "$api_path" ] || [ "$api_path" = "null" ]; then
            # Try to get first route from 'api' field
            local api_field=$(echo "$meta" | jq -r '.api // empty')
            if [ -n "$api_field" ] && [ "$api_field" != "null" ]; then
                # Extract first route (before first comma)
                api_path=$(echo "$api_field" | cut -d',' -f1)
                print_info "Using first route from 'api' field for $service_name: $api_path"
            fi
        fi

        # Skip if still no api_path
        if [ -z "$api_path" ] || [ "$api_path" = "null" ]; then
            print_info "Skipping $service_name (no api_path/base_path in metadata)"
            ((skipped++))
            continue
        fi

        # Get optional metadata
        local auth_required=$(echo "$meta" | jq -r '.auth_required // "false"')
        local rate_limit=$(echo "$meta" | jq -r '.rate_limit // "100"')

        # Create/Update route
        if create_or_update_route "$service_name" "$api_path" "$auth_required" "$rate_limit"; then
            ((synced++))
            processed_services+=("${service_name}_route")
        else
            ((failed++))
        fi
    done

    echo ""
    print_info "🧹 Cleaning up stale routes..."

    # Get all managed routes from APISIX
    local apisix_routes=$(curl -s "${APISIX_ADMIN_URL}/apisix/admin/routes" \
        -H "X-API-KEY: ${ADMIN_KEY}" | \
        jq -r '.list[] | select(.value.labels.managed_by == "consul-sync") | .value.name')

    # Delete routes that no longer exist in Consul
    local deleted=0
    for route_name in $apisix_routes; do
        # Check if this route was processed
        local found=false
        for processed in "${processed_services[@]}"; do
            if [ "$processed" = "$route_name" ]; then
                found=true
                break
            fi
        done

        if [ "$found" = false ]; then
            delete_route "$route_name"
            ((deleted++))
        fi
    done

    echo ""
    print_info "📊 Synchronization Summary"
    echo "   Synced:  ${synced}"
    echo "   Skipped: ${skipped}"
    echo "   Failed:  ${failed}"
    echo "   Deleted: ${deleted}"
    echo ""

    local total_routes=$(curl -s "${APISIX_ADMIN_URL}/apisix/admin/routes" \
        -H "X-API-KEY: ${ADMIN_KEY}" | jq '.total')

    print_success "✨ Sync complete! Total active routes: ${total_routes}"
}

# Run
main
