#!/bin/bash
# =============================================================================
# Service Health Check Script
# =============================================================================
# Checks Consul registration, APISIX routes, and gateway health for a service
#
# Usage:
#   ./service-check.sh model_service /api/v1/models
#   ./service-check.sh mcp_service /api/v1/mcp
#   ./service-check.sh --all  # Check all services
#   ./service-check.sh local model_service /api/v1/models  # Explicit environment
# =============================================================================

set -e

# Load environment configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(cd "$SCRIPT_DIR/../../config" && pwd)"
source "$CONFIG_DIR/environments.sh"

# Parse arguments - check if first arg is environment
if [[ "$1" =~ ^(local|staging|production)$ ]]; then
    load_environment "$1"
    SERVICE_NAME="${2:-model_service}"
    API_PATH="${3:-/api/v1/models}"
else
    load_environment
    SERVICE_NAME="${1:-model_service}"
    API_PATH="${2:-/api/v1/models}"
fi

# Use environment config
ADMIN_KEY="${APISIX_ADMIN_KEY}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}==============================================${NC}"
echo "Service Health Check"
echo "=============================================="
echo "Environment:   $ISA_ENV"
echo "Cluster:       $CLUSTER_NAME"
echo "Consul URL:    $CONSUL_URL"
echo "APISIX Admin:  $APISIX_ADMIN"
echo "=============================================="
echo ""

check_service() {
    local svc_name="$1"
    local api_path="$2"

    echo "=== Checking ${svc_name} ==="

    # 1. Consul Registration
    echo -e "\n${YELLOW}[1/4] Consul Registration:${NC}"
    CONSUL_DATA=$(curl -s "${CONSUL_URL}/v1/catalog/service/${svc_name}")
    if [ "$(echo $CONSUL_DATA | jq length)" -gt 0 ]; then
        echo "$CONSUL_DATA" | jq '.[0] | {ServiceID, ServiceAddress, ServicePort}'
        echo -e "${GREEN}✓ Registered in Consul${NC}"

        # Check metadata
        echo "Metadata:"
        echo "$CONSUL_DATA" | jq '.[0].ServiceMeta | {api_path, base_path, version}'
    else
        echo -e "${RED}✗ NOT REGISTERED in Consul${NC}"
    fi

    # 2. Health Status
    echo -e "\n${YELLOW}[2/4] Health Status:${NC}"
    HEALTH_DATA=$(curl -s "${CONSUL_URL}/v1/health/service/${svc_name}")
    echo "$HEALTH_DATA" | jq '.[0].Checks[] | {Name, Status}' 2>/dev/null || echo "No health checks"

    # 3. APISIX Routes
    echo -e "\n${YELLOW}[3/4] APISIX Routes:${NC}"
    ROUTES=$(curl -s "${APISIX_ADMIN}/apisix/admin/routes" -H "X-API-KEY: ${ADMIN_KEY}" | \
        jq ".list[] | select(.value.name | test(\"${svc_name}\")) | {name: .value.name, uris: .value.uris}" 2>/dev/null)
    if [ -n "$ROUTES" ] && [ "$ROUTES" != "null" ]; then
        echo "$ROUTES"
        echo -e "${GREEN}✓ Routes configured${NC}"
    else
        echo -e "${RED}✗ No routes found for ${svc_name}${NC}"
    fi

    # 4. Gateway Test
    echo -e "\n${YELLOW}[4/4] Gateway Test (${api_path}/health):${NC}"
    RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" "${APISIX_GATEWAY}${api_path}/health" 2>/dev/null)
    HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
    BODY=$(echo "$RESPONSE" | grep -v "HTTP_CODE:")

    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}✓ SUCCESS (HTTP 200)${NC}"
        echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
    else
        echo -e "${RED}✗ FAILED (HTTP ${HTTP_CODE})${NC}"
        echo "$BODY" | head -c 200
    fi

    echo -e "\n=== Check Complete ===\n"
}

# Check all services
if [ "$SERVICE_NAME" = "--all" ]; then
    echo "Checking all registered services..."

    # Get all services from Consul
    SERVICES=$(curl -s "${CONSUL_URL}/v1/catalog/services" | jq -r 'keys[]' | grep -v consul)

    for svc in $SERVICES; do
        # Get API path from metadata
        api_path=$(curl -s "${CONSUL_URL}/v1/catalog/service/${svc}" | jq -r '.[0].ServiceMeta.api_path // .[0].ServiceMeta.base_path // "/api/v1/unknown"' 2>/dev/null)
        check_service "$svc" "$api_path"
    done
else
    check_service "$SERVICE_NAME" "$API_PATH"
fi
