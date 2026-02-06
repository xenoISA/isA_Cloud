#!/bin/bash
set -e

# ============================================
# isA Cloud - Kubernetes Deployment Script
# ============================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT=${1:-staging}
DRY_RUN=${2:-false}

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}isA Cloud - Kubernetes Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Environment: ${YELLOW}${ENVIRONMENT}${NC}"
echo -e "Dry Run: ${YELLOW}${DRY_RUN}${NC}"
echo ""

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|production)$ ]]; then
    echo -e "${RED}Error: Invalid environment. Must be dev, staging, or production${NC}"
    exit 1
fi

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Error: kubectl is not installed${NC}"
    exit 1
fi

# Check if cluster is accessible
echo -e "${YELLOW}Checking cluster connectivity...${NC}"
if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}Error: Cannot connect to Kubernetes cluster${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Connected to cluster${NC}"
echo ""

# Set the overlay path
OVERLAY_PATH="../overlays/${ENVIRONMENT}"

if [ ! -d "$OVERLAY_PATH" ]; then
    echo -e "${RED}Error: Overlay directory not found: ${OVERLAY_PATH}${NC}"
    exit 1
fi

# Build kustomization to preview
echo -e "${YELLOW}Building Kustomization...${NC}"
kubectl kustomize "$OVERLAY_PATH" > /tmp/isa-cloud-${ENVIRONMENT}.yaml
echo -e "${GREEN}✓ Kustomization built successfully${NC}"
echo ""

# Show what will be deployed
echo -e "${YELLOW}Resources to be deployed:${NC}"
kubectl kustomize "$OVERLAY_PATH" | grep -E '^kind:|^  name:' | paste - - | sed 's/kind: //' | sed 's/  name: / - /'
echo ""

# Confirm deployment
if [ "$DRY_RUN" = "false" ]; then
    read -p "Do you want to proceed with deployment? (yes/no): " -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo -e "${YELLOW}Deployment cancelled${NC}"
        exit 0
    fi

    echo -e "${YELLOW}Deploying to ${ENVIRONMENT}...${NC}"
    kubectl apply -k "$OVERLAY_PATH"
    echo ""
    echo -e "${GREEN}✓ Deployment complete!${NC}"
    echo ""

    # Wait for rollout
    echo -e "${YELLOW}Waiting for rollout to complete...${NC}"
    kubectl rollout status statefulset/consul -n isa-cloud-${ENVIRONMENT} --timeout=5m || true
    kubectl rollout status deployment/redis-grpc -n isa-cloud-${ENVIRONMENT} --timeout=5m || true
    echo ""

    # Show pod status
    echo -e "${YELLOW}Pod Status:${NC}"
    kubectl get pods -n isa-cloud-${ENVIRONMENT}
    echo ""

    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Deployment Summary${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "To view logs:"
    echo "  kubectl logs -n isa-cloud-${ENVIRONMENT} -l app=consul --tail=100 -f"
    echo ""
    echo "To access Consul UI (port-forward):"
    echo "  kubectl port-forward -n isa-cloud-${ENVIRONMENT} svc/consul-ui 8500:8500"
    echo ""
    echo "To view all resources:"
    echo "  kubectl get all -n isa-cloud-${ENVIRONMENT}"
    echo ""
else
    echo -e "${YELLOW}Dry run mode - no changes applied${NC}"
    echo ""
    echo "Preview of resources:"
    cat /tmp/isa-cloud-${ENVIRONMENT}.yaml
fi
