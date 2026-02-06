#!/bin/bash
# =============================================================================
# Consul & APISIX Stale Entry Cleanup
# =============================================================================
# Automatically finds and removes:
#   1. Consul services with critical/failing health checks
#   2. Consul services not matching the _service naming convention
#   3. APISIX routes pointing to services no longer in Consul
#
# Usage:
#   ./consul-cleanup.sh              # Dry-run (report only)
#   ./consul-cleanup.sh --apply      # Actually remove stale entries
#   ./consul-cleanup.sh local --apply # Explicit environment + apply
# =============================================================================

set -e

# Load environment configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(cd "$SCRIPT_DIR/../../config" && pwd)"
source "$CONFIG_DIR/environments.sh"

# Parse arguments
DRY_RUN=true
for arg in "$@"; do
    if [[ "$arg" =~ ^(local|staging|production)$ ]]; then
        load_environment "$arg"
    elif [[ "$arg" == "--apply" ]]; then
        DRY_RUN=false
    fi
done

# Auto-detect if not yet loaded
if [ -z "$ISA_ENV" ]; then
    load_environment
fi

ADMIN_KEY="${APISIX_ADMIN_KEY}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}==============================================${NC}"
echo "Consul & APISIX Stale Entry Cleanup"
echo "=============================================="
echo "Environment:  $ISA_ENV"
echo "Consul URL:   $CONSUL_URL"
echo "APISIX Admin: $APISIX_ADMIN"
if $DRY_RUN; then
    echo -e "Mode:         ${YELLOW}DRY-RUN${NC} (use --apply to execute)"
else
    echo -e "Mode:         ${RED}APPLY${NC} (changes will be made)"
fi
echo "=============================================="
echo ""

STALE_COUNT=0
CLEANED_COUNT=0
ROUTE_CLEANED=0

# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: Find and remove stale Consul services (critical health)
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[Phase 1] Checking for Consul services with critical health...${NC}"

SERVICES=$(curl -s "${CONSUL_URL}/v1/catalog/services" | jq -r 'keys[] | select(. != "consul")')

for SERVICE in $SERVICES; do
    # Get all instances of this service
    INSTANCES=$(curl -s "${CONSUL_URL}/v1/health/service/${SERVICE}")
    INSTANCE_COUNT=$(echo "$INSTANCES" | jq 'length')

    for i in $(seq 0 $((INSTANCE_COUNT - 1))); do
        INSTANCE=$(echo "$INSTANCES" | jq ".[$i]")
        SERVICE_ID=$(echo "$INSTANCE" | jq -r '.Service.ID')

        # Check non-serfHealth checks for critical status
        CRITICAL=$(echo "$INSTANCE" | jq -r '[.Checks[] | select(.CheckID != "serfHealth") | select(.Status == "critical")] | length')

        if [ "$CRITICAL" -gt 0 ]; then
            ((STALE_COUNT++))
            echo -e "  ${RED}STALE${NC} ${SERVICE_ID} (health: critical)"

            if ! $DRY_RUN; then
                curl -s -X PUT "${CONSUL_URL}/v1/agent/service/deregister/${SERVICE_ID}"
                echo -e "    ${GREEN}-> Deregistered${NC}"
                ((CLEANED_COUNT++))
            fi
        fi
    done
done

if [ "$STALE_COUNT" -eq 0 ]; then
    echo -e "  ${GREEN}No stale services found${NC}"
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Phase 2: Find services not following _service naming convention
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[Phase 2] Checking for non-standard service names...${NC}"

NON_STANDARD=0
for SERVICE in $SERVICES; do
    if [[ "$SERVICE" != *"_service" ]]; then
        ((NON_STANDARD++))
        # Get instance details
        PORT=$(curl -s "${CONSUL_URL}/v1/catalog/service/${SERVICE}" | jq -r '.[0].ServicePort // "?"')
        echo -e "  ${YELLOW}NON-STANDARD${NC} ${SERVICE} (port: ${PORT}) - should end with _service"
    fi
done

if [ "$NON_STANDARD" -eq 0 ]; then
    echo -e "  ${GREEN}All services follow naming convention${NC}"
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Phase 3: Find orphaned APISIX routes (service no longer in Consul)
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[Phase 3] Checking for orphaned APISIX routes...${NC}"

# Get all healthy Consul services
HEALTHY_SERVICES=$(curl -s "${CONSUL_URL}/v1/catalog/services" | jq -r 'keys[]' | grep -v consul)

# Get all APISIX routes
ROUTES_JSON=$(curl -s "${APISIX_ADMIN}/apisix/admin/routes" -H "X-API-KEY: ${ADMIN_KEY}" 2>/dev/null)
ROUTE_COUNT=$(echo "$ROUTES_JSON" | jq '.total // 0')

if [ "$ROUTE_COUNT" -gt 0 ]; then
    # Extract route IDs and names
    ROUTE_LIST=$(echo "$ROUTES_JSON" | jq -r '.list[] | "\(.value.id // .key)|\(.value.name // "unnamed")"' 2>/dev/null)

    while IFS='|' read -r ROUTE_ID ROUTE_NAME; do
        [ -z "$ROUTE_ID" ] && continue

        # Extract service name from route name
        # Routes are named like "service_name_route", "service_name_health_route",
        # or "service_name-main", "service_name-health"
        SVC_FROM_ROUTE=$(echo "$ROUTE_NAME" | sed 's/_health_route$//' | sed 's/_route$//' | sed 's/-main$//' | sed 's/-health$//')

        # Check if this service exists in Consul
        FOUND=false
        for SVC in $HEALTHY_SERVICES; do
            if [ "$SVC" = "$SVC_FROM_ROUTE" ]; then
                FOUND=true
                break
            fi
        done

        if ! $FOUND; then
            echo -e "  ${YELLOW}ORPHAN${NC} route '${ROUTE_NAME}' (id: ${ROUTE_ID}) - service '${SVC_FROM_ROUTE}' not in Consul"

            if ! $DRY_RUN; then
                curl -s -X DELETE "${APISIX_ADMIN}/apisix/admin/routes/${ROUTE_ID}" \
                    -H "X-API-KEY: ${ADMIN_KEY}" >/dev/null 2>&1
                echo -e "    ${GREEN}-> Deleted route${NC}"
                ((ROUTE_CLEANED++))
            fi
        fi
    done <<< "$ROUTE_LIST"
else
    echo "  No APISIX routes found (or APISIX not reachable)"
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Phase 4: Find duplicate registrations (same service, multiple instances)
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${BLUE}[Phase 4] Checking for duplicate registrations...${NC}"

DUPLICATES=0
for SERVICE in $SERVICES; do
    COUNT=$(curl -s "${CONSUL_URL}/v1/catalog/service/${SERVICE}" | jq 'length')
    if [ "$COUNT" -gt 1 ]; then
        ((DUPLICATES++))
        echo -e "  ${YELLOW}DUPLICATE${NC} ${SERVICE} has ${COUNT} instances:"
        curl -s "${CONSUL_URL}/v1/catalog/service/${SERVICE}" | jq -r '.[] | "    - \(.ServiceID) (\(.ServiceAddress):\(.ServicePort))"'
    fi
done

if [ "$DUPLICATES" -eq 0 ]; then
    echo -e "  ${GREEN}No duplicate registrations${NC}"
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
echo "=============================================="
echo "Cleanup Summary"
echo "=============================================="
echo "Stale services found:     $STALE_COUNT"
echo "Non-standard names:       $NON_STANDARD"
echo "Duplicate registrations:  $DUPLICATES"

if $DRY_RUN; then
    echo ""
    echo -e "${YELLOW}This was a dry run. Use --apply to execute cleanup.${NC}"
else
    echo "Services deregistered:    $CLEANED_COUNT"
    echo "APISIX routes deleted:    $ROUTE_CLEANED"
    echo ""
    echo -e "${GREEN}Cleanup complete.${NC}"
fi
