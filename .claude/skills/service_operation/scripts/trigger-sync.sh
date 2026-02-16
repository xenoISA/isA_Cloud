#!/bin/bash
# =============================================================================
# Trigger APISIX Sync from Consul
# =============================================================================
# Manually triggers the consul-apisix-sync CronJob
#
# Usage:
#   ./trigger-sync.sh              # Auto-detect environment
#   ./trigger-sync.sh local        # Explicit local environment
#   ./trigger-sync.sh staging      # Staging environment
# =============================================================================

set -e

# Load environment configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(cd "$SCRIPT_DIR/../../config" && pwd)"
source "$CONFIG_DIR/environments.sh"

# Parse arguments
if [[ "$1" =~ ^(local|staging|production)$ ]]; then
    load_environment "$1"
else
    load_environment
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
echo "Consul-APISIX Sync Trigger"
echo "=============================================="
echo "Environment:  $ISA_ENV"
echo "Cluster:      $CLUSTER_NAME"
echo "Namespace:    $NAMESPACE"
echo "=============================================="
echo ""

echo "Triggering Consul-APISIX sync..."

# Create a job from the CronJob
JOB_NAME="consul-apisix-sync-manual-$(date +%s)"
kubectl create job "$JOB_NAME" \
    --from=cronjob/consul-apisix-sync \
    -n "$NAMESPACE" 2>/dev/null

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Job created: $JOB_NAME${NC}"
    echo "Waiting for completion..."

    # Wait for job to complete
    kubectl wait --for=condition=complete "job/$JOB_NAME" -n "$NAMESPACE" --timeout=60s 2>/dev/null

    # Show logs
    echo ""
    echo -e "${YELLOW}=== Sync Logs ===${NC}"
    kubectl logs -n "$NAMESPACE" "job/$JOB_NAME" --tail=50 2>/dev/null

    # Cleanup
    kubectl delete job "$JOB_NAME" -n "$NAMESPACE" 2>/dev/null
else
    echo -e "${RED}✗ Failed to create sync job. CronJob may not exist.${NC}"
    echo "Checking if CronJob exists:"
    kubectl get cronjob consul-apisix-sync -n "$NAMESPACE" 2>/dev/null || echo "CronJob not found"
fi

# Show route count
echo ""
echo -e "${YELLOW}=== Current APISIX Routes ===${NC}"
curl -s "${APISIX_ADMIN}/apisix/admin/routes" \
    -H "X-API-KEY: $ADMIN_KEY" 2>/dev/null | jq '.total // "Unable to fetch"'
