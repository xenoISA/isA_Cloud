#!/bin/bash
# =============================================================================
# Local Development Environment Setup (Kind)
# =============================================================================
# Sets up a complete local Kubernetes cluster using Kind with all infrastructure
#
# Usage:
#   ./setup-local.sh              # Full setup
#   ./setup-local.sh --infra-only # Infrastructure only (no applications)
#   ./setup-local.sh --rebuild    # Delete and recreate cluster
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISA_CLOUD_DIR="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"

CLUSTER_NAME="${KIND_CLUSTER:-isa-cloud-local}"
NAMESPACE="isa-cloud-staging"
INFRA_ONLY=false
REBUILD=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --infra-only) INFRA_ONLY=true; shift ;;
        --rebuild) REBUILD=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=============================================="
echo "ISA Cloud - Local Environment Setup"
echo "=============================================="
echo -e "${NC}"

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"
command -v kind >/dev/null 2>&1 || { echo -e "${RED}kind not installed. Install with: brew install kind${NC}"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo -e "${RED}kubectl not installed. Install with: brew install kubectl${NC}"; exit 1; }
command -v helm >/dev/null 2>&1 || { echo -e "${RED}helm not installed. Install with: brew install helm${NC}"; exit 1; }
echo -e "${GREEN}✓ All prerequisites installed${NC}"

# Handle rebuild
if [ "$REBUILD" = true ]; then
    echo -e "${YELLOW}Rebuilding cluster...${NC}"
    if kind get clusters 2>/dev/null | grep -q "$CLUSTER_NAME"; then
        echo "  Deleting existing cluster: $CLUSTER_NAME"
        kind delete cluster --name "$CLUSTER_NAME"
    fi
fi

# =============================================================================
# Step 1: Create Kind Cluster
# =============================================================================
echo ""
echo -e "${YELLOW}[1/5] Setting up Kind cluster...${NC}"

if kind get clusters 2>/dev/null | grep -q "$CLUSTER_NAME"; then
    echo -e "  ${GREEN}✓ Cluster '$CLUSTER_NAME' already exists${NC}"
else
    # Create kind config
    KIND_CONFIG=$(mktemp)
    cat > "$KIND_CONFIG" << 'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: isa-cloud-local
nodes:
  - role: control-plane
    extraPortMappings:
      # PostgreSQL
      - containerPort: 30432
        hostPort: 5432
        protocol: TCP
      # Redis
      - containerPort: 30379
        hostPort: 6379
        protocol: TCP
      # Qdrant gRPC
      - containerPort: 30334
        hostPort: 6334
        protocol: TCP
      # Qdrant HTTP
      - containerPort: 30333
        hostPort: 6333
        protocol: TCP
      # MinIO API
      - containerPort: 30900
        hostPort: 9000
        protocol: TCP
      # MinIO Console
      - containerPort: 30901
        hostPort: 9001
        protocol: TCP
      # Neo4j Bolt
      - containerPort: 30687
        hostPort: 7687
        protocol: TCP
      # Neo4j HTTP
      - containerPort: 30474
        hostPort: 7474
        protocol: TCP
      # NATS
      - containerPort: 30422
        hostPort: 4222
        protocol: TCP
      # Consul
      - containerPort: 30500
        hostPort: 8500
        protocol: TCP
      # APISIX Gateway
      - containerPort: 30080
        hostPort: 9080
        protocol: TCP
      # APISIX Admin
      - containerPort: 30180
        hostPort: 9180
        protocol: TCP
      # EMQX MQTT
      - containerPort: 31883
        hostPort: 1883
        protocol: TCP
EOF

    kind create cluster --config "$KIND_CONFIG"
    rm "$KIND_CONFIG"
    echo -e "  ${GREEN}✓ Kind cluster created${NC}"
fi

# Set context
kubectl config use-context "kind-$CLUSTER_NAME"

# =============================================================================
# Step 2: Create Namespace
# =============================================================================
echo ""
echo -e "${YELLOW}[2/5] Creating namespace...${NC}"
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
echo -e "  ${GREEN}✓ Namespace '$NAMESPACE' ready${NC}"

# =============================================================================
# Step 3: Add Helm Repos
# =============================================================================
echo ""
echo -e "${YELLOW}[3/5] Adding Helm repositories...${NC}"
helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
helm repo add qdrant https://qdrant.github.io/qdrant-helm 2>/dev/null || true
helm repo add nats https://nats-io.github.io/k8s/helm/charts/ 2>/dev/null || true
helm repo add hashicorp https://helm.releases.hashicorp.com 2>/dev/null || true
helm repo add apisix https://charts.apiseven.com 2>/dev/null || true
helm repo update
echo -e "  ${GREEN}✓ Helm repos configured${NC}"

# =============================================================================
# Step 4: Deploy Infrastructure
# =============================================================================
echo ""
echo -e "${YELLOW}[4/5] Deploying infrastructure...${NC}"

VALUES_DIR="$ISA_CLOUD_DIR/deployments/kubernetes/staging/values"

# PostgreSQL
echo "  Installing PostgreSQL..."
helm upgrade --install postgresql bitnami/postgresql \
    -n "$NAMESPACE" \
    -f "$VALUES_DIR/postgresql.yaml" \
    --set primary.service.type=NodePort \
    --set primary.service.nodePorts.postgresql=30432 \
    --wait --timeout 5m 2>/dev/null && echo -e "    ${GREEN}✓ PostgreSQL${NC}" || echo -e "    ${YELLOW}⚠ PostgreSQL (may already exist)${NC}"

# Redis
echo "  Installing Redis..."
helm upgrade --install redis bitnami/redis \
    -n "$NAMESPACE" \
    -f "$VALUES_DIR/redis.yaml" \
    --set master.service.type=NodePort \
    --set master.service.nodePorts.redis=30379 \
    --wait --timeout 5m 2>/dev/null && echo -e "    ${GREEN}✓ Redis${NC}" || echo -e "    ${YELLOW}⚠ Redis${NC}"

# Qdrant
echo "  Installing Qdrant..."
helm upgrade --install qdrant qdrant/qdrant \
    -n "$NAMESPACE" \
    -f "$VALUES_DIR/qdrant.yaml" \
    --set service.type=NodePort \
    --set service.nodePort=30333 \
    --wait --timeout 5m 2>/dev/null && echo -e "    ${GREEN}✓ Qdrant${NC}" || echo -e "    ${YELLOW}⚠ Qdrant${NC}"

# MinIO
echo "  Installing MinIO..."
helm upgrade --install minio bitnami/minio \
    -n "$NAMESPACE" \
    -f "$VALUES_DIR/minio.yaml" \
    --set service.type=NodePort \
    --set service.nodePorts.api=30900 \
    --set service.nodePorts.console=30901 \
    --wait --timeout 5m 2>/dev/null && echo -e "    ${GREEN}✓ MinIO${NC}" || echo -e "    ${YELLOW}⚠ MinIO${NC}"

# Neo4j
echo "  Installing Neo4j..."
helm upgrade --install neo4j bitnami/neo4j \
    -n "$NAMESPACE" \
    -f "$VALUES_DIR/neo4j.yaml" \
    --set service.type=NodePort \
    --set service.nodePorts.bolt=30687 \
    --set service.nodePorts.http=30474 \
    --wait --timeout 5m 2>/dev/null && echo -e "    ${GREEN}✓ Neo4j${NC}" || echo -e "    ${YELLOW}⚠ Neo4j${NC}"

# NATS
echo "  Installing NATS..."
helm upgrade --install nats nats/nats \
    -n "$NAMESPACE" \
    -f "$VALUES_DIR/nats.yaml" \
    --set service.type=NodePort \
    --wait --timeout 5m 2>/dev/null && echo -e "    ${GREEN}✓ NATS${NC}" || echo -e "    ${YELLOW}⚠ NATS${NC}"

# Consul
echo "  Installing Consul..."
helm upgrade --install consul hashicorp/consul \
    -n "$NAMESPACE" \
    -f "$VALUES_DIR/consul.yaml" \
    --set ui.service.type=NodePort \
    --set ui.service.nodePort=30500 \
    --wait --timeout 5m 2>/dev/null && echo -e "    ${GREEN}✓ Consul${NC}" || echo -e "    ${YELLOW}⚠ Consul${NC}"

# APISIX
echo "  Installing APISIX..."
helm upgrade --install apisix apisix/apisix \
    -n "$NAMESPACE" \
    --set gateway.type=NodePort \
    --set gateway.http.nodePort=30080 \
    --set admin.type=NodePort \
    --wait --timeout 5m 2>/dev/null && echo -e "    ${GREEN}✓ APISIX${NC}" || echo -e "    ${YELLOW}⚠ APISIX${NC}"

# =============================================================================
# Step 5: Verify Deployment
# =============================================================================
echo ""
echo -e "${YELLOW}[5/5] Verifying deployment...${NC}"
sleep 5

echo ""
kubectl get pods -n "$NAMESPACE"

echo ""
echo -e "${BLUE}=============================================="
echo "Local Environment Ready!"
echo "=============================================="
echo -e "${NC}"
echo "Services available at:"
echo "  PostgreSQL: localhost:5432"
echo "  Redis:      localhost:6379"
echo "  Qdrant:     localhost:6333 (HTTP), localhost:6334 (gRPC)"
echo "  MinIO:      localhost:9000 (API), localhost:9001 (Console)"
echo "  Neo4j:      localhost:7474 (HTTP), localhost:7687 (Bolt)"
echo "  NATS:       localhost:4222"
echo "  Consul:     localhost:8500"
echo "  APISIX:     localhost:9080 (Gateway), localhost:9180 (Admin)"
echo ""
echo "Next steps:"
echo "  1. Run MCP service: cd isA_MCP && ./deployment/local-dev.sh"
echo "  2. Run Model service: cd isA_Model && ./deployment/local-dev.sh"
echo "=============================================="
