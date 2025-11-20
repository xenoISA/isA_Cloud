#!/bin/bash
# Dynamic Route Synchronization from Consul to APISIX (K8s Version)
#
# Designed for Kubernetes environment where services use DNS names instead of IPs

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
CONSUL_URL="${CONSUL_URL:-http://consul-agent.isa-cloud-staging.svc.cluster.local:8500}"
APISIX_ADMIN_URL="${APISIX_ADMIN_URL:-http://apisix-gateway.isa-cloud-staging.svc.cluster.local:9180}"
ADMIN_KEY="${APISIX_ADMIN_KEY:-edd1c9f034335f136f87ad84b625c8f1}"

# Functions
print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ $1${NC}"; }

# Get service metadata from Consul
get_service_meta() {
    local service_name=$1
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
    # Support both root path and sub-paths using uris array
    # e.g., ["/api/v1/accounts", "/api/v1/accounts/*"]
    local uri_root="${api_path}"
    local uri_pattern="${api_path}/*"

    print_info "Syncing route: $route_name ($uri_root + $uri_pattern -> $service_name)"

    # Check if service needs proxy-rewrite by detecting path mismatch
    # Services like mcp_service expose routes at root (/) but are accessed via /api/v1/mcp
    local needs_rewrite=false
    local meta=$(get_service_meta "$service_name")

    # Check for services that need path rewriting (e.g., mcp_service)
    # MCP service routes start with / but base_path is /api/v1/mcp
    if [[ "$service_name" == "mcp_service" ]]; then
        needs_rewrite=true
    fi

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

    # Add proxy-rewrite if needed
    if [ "$needs_rewrite" = "true" ]; then
        # Strip the base_path prefix before forwarding to backend
        # e.g., /api/v1/mcp/health -> /health
        local rewrite_pattern="^${api_path}(/.*)\$"
        local rewrite_replacement="\$1"
        plugins=$(echo "$plugins" | jq --arg pattern "$rewrite_pattern" --arg replacement "$rewrite_replacement" '. + {"proxy-rewrite": {"regex_uri": [$pattern, $replacement]}}')
        print_info "  Added proxy-rewrite: $api_path/* -> /*"
    fi

    # Add JWT auth if required
    if [ "$auth_required" = "true" ]; then
        plugins=$(echo "$plugins" | jq '. + {"jwt-auth": {}}')
    fi

    # Get service instances from Consul - K8s版本直接使用DNS名称，无需IP解析
    local instances=$(curl -s "${CONSUL_URL}/v1/catalog/service/${service_name}")

    # In K8s, ServiceAddress is already a DNS name (e.g., auth.isa-cloud-staging.svc.cluster.local)
    # We can use it directly without IP resolution
    local nodes="{}"
    while IFS= read -r line; do
        if [ -z "$line" ]; then continue; fi

        local host=$(echo "$line" | jq -r '.ServiceAddress')
        local port=$(echo "$line" | jq -r '.ServicePort')

        # Use DNS name directly (K8s will handle resolution)
        if [ -n "$host" ] && [ "$host" != "null" ]; then
            nodes=$(echo "$nodes" | jq ". + {\"$host:$port\": 1}")
            print_info "  Added upstream: $host:$port"
        fi
    done < <(echo "$instances" | jq -c '.[]')

    # Create/Update route with K8s Service DNS names
    local response=$(curl -s -w "\n%{http_code}" -X PUT \
        "${APISIX_ADMIN_URL}/apisix/admin/routes/${route_name}" \
        -H "X-API-KEY: ${ADMIN_KEY}" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"${route_name}\",
            \"desc\": \"Auto-synced from Consul service: ${service_name}\",
            \"uris\": [\"${uri_root}\", \"${uri_pattern}\"],
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
                },
                \"pass_host\": \"pass\"
            },
            \"plugins\": ${plugins},
            \"enable_websocket\": true,
            \"status\": 1,
            \"labels\": {
                \"managed_by\": \"consul-sync-k8s\",
                \"service_name\": \"${service_name}\",
                \"sync_timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
            }
        }")

    local http_code=$(echo "$response" | tail -n1)

    if [[ "$http_code" =~ ^20[0-9]$ ]]; then
        print_success "Route synced: $route_name"
        return 0
    else
        local body=$(echo "$response" | head -n-1)
        print_error "Failed to sync route: $route_name (HTTP $http_code)"
        echo "$body" | jq '.' 2>/dev/null || echo "$body"
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
    print_info "🔄 Starting Consul → APISIX route synchronization (K8s)..."
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
        local api_path=$(echo "$meta" | jq -r '.api_path // .base_path // empty')

        # Skip if no api_path
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
        jq -r '.list[]? | select(.value.labels.managed_by == "consul-sync-k8s") | .value.name' 2>/dev/null)

    # Delete routes that no longer exist in Consul
    local deleted=0
    for route_name in $apisix_routes; do
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
        -H "X-API-KEY: ${ADMIN_KEY}" | jq '.total // 0')

    print_success "✨ Sync complete! Total active routes: ${total_routes}"
}

# Run
main
