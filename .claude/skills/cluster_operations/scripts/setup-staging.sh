#!/bin/bash
# =============================================================================
# Staging Environment Setup (EKS/GKE/AKS)
# =============================================================================
# Sets up staging environment on cloud Kubernetes
#
# Usage:
#   ./setup-staging.sh                    # Setup staging on existing cluster
#   ./setup-staging.sh --create-cluster   # Create EKS cluster first
#   AWS_PROFILE=myprofile ./setup-staging.sh
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISA_CLOUD_DIR="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"

CLUSTER_NAME="${CLUSTER_NAME:-isa-cloud-staging}"
NAMESPACE="isa-cloud-staging"
REGION="${AWS_REGION:-us-east-1}"
CREATE_CLUSTER=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --create-cluster) CREATE_CLUSTER=true; shift ;;
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
echo "ISA Cloud - Staging Environment Setup"
echo "=============================================="
echo -e "${NC}"

# =============================================================================
# Step 1: Create/Connect to Cluster
# =============================================================================
echo -e "${YELLOW}[1/6] Setting up cluster...${NC}"

if [ "$CREATE_CLUSTER" = true ]; then
    echo "  Creating EKS cluster: $CLUSTER_NAME"

    eksctl create cluster \
        --name "$CLUSTER_NAME" \
        --region "$REGION" \
        --nodegroup-name workers \
        --node-type m5.xlarge \
        --nodes 3 \
        --nodes-min 2 \
        --nodes-max 5 \
        --managed

    echo -e "  ${GREEN}✓ EKS cluster created${NC}"
fi

# Configure kubectl
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$REGION" 2>/dev/null || \
    echo -e "  ${YELLOW}⚠ Make sure kubectl is configured for the cluster${NC}"

# Verify connection
if ! kubectl cluster-info &>/dev/null; then
    echo -e "${RED}ERROR: Cannot connect to cluster${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓ Connected to cluster${NC}"

# =============================================================================
# Step 2: Create Namespace and Secrets
# =============================================================================
echo ""
echo -e "${YELLOW}[2/6] Creating namespace and secrets...${NC}"

kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Apply secrets
SECRETS_FILE="$ISA_CLOUD_DIR/deployments/kubernetes/staging/secrets/infrastructure-secrets.yaml"
if [ -f "$SECRETS_FILE" ]; then
    kubectl apply -f "$SECRETS_FILE" -n "$NAMESPACE"
    echo -e "  ${GREEN}✓ Secrets applied${NC}"
else
    echo -e "  ${YELLOW}⚠ Secrets file not found: $SECRETS_FILE${NC}"
fi

# =============================================================================
# Step 3: Install ArgoCD
# =============================================================================
echo ""
echo -e "${YELLOW}[3/6] Installing ArgoCD...${NC}"

kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for ArgoCD
kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd
echo -e "  ${GREEN}✓ ArgoCD installed${NC}"

# Get ArgoCD password
ARGOCD_PASS=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)
echo "  ArgoCD admin password: $ARGOCD_PASS"

# =============================================================================
# Step 4: Add Helm Repos
# =============================================================================
echo ""
echo -e "${YELLOW}[4/6] Adding Helm repositories...${NC}"

helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
helm repo add qdrant https://qdrant.github.io/qdrant-helm 2>/dev/null || true
helm repo add nats https://nats-io.github.io/k8s/helm/charts/ 2>/dev/null || true
helm repo add hashicorp https://helm.releases.hashicorp.com 2>/dev/null || true
helm repo add apisix https://charts.apiseven.com 2>/dev/null || true
helm repo update
echo -e "  ${GREEN}✓ Helm repos configured${NC}"

# =============================================================================
# Step 5: Deploy Infrastructure via Helm
# =============================================================================
echo ""
echo -e "${YELLOW}[5/6] Deploying infrastructure...${NC}"

VALUES_DIR="$ISA_CLOUD_DIR/deployments/kubernetes/staging/values"

# Deploy each service with staging values
for service in postgresql redis qdrant minio neo4j nats consul; do
    if [ -f "$VALUES_DIR/${service}.yaml" ]; then
        echo "  Installing $service..."

        case $service in
            postgresql)
                helm upgrade --install $service bitnami/postgresql -n "$NAMESPACE" -f "$VALUES_DIR/${service}.yaml" --wait --timeout 10m
                ;;
            redis)
                helm upgrade --install $service bitnami/redis -n "$NAMESPACE" -f "$VALUES_DIR/${service}.yaml" --wait --timeout 10m
                ;;
            qdrant)
                helm upgrade --install $service qdrant/qdrant -n "$NAMESPACE" -f "$VALUES_DIR/${service}.yaml" --wait --timeout 10m
                ;;
            minio)
                helm upgrade --install $service bitnami/minio -n "$NAMESPACE" -f "$VALUES_DIR/${service}.yaml" --wait --timeout 10m
                ;;
            neo4j)
                helm upgrade --install $service bitnami/neo4j -n "$NAMESPACE" -f "$VALUES_DIR/${service}.yaml" --wait --timeout 10m
                ;;
            nats)
                helm upgrade --install $service nats/nats -n "$NAMESPACE" -f "$VALUES_DIR/${service}.yaml" --wait --timeout 10m
                ;;
            consul)
                helm upgrade --install $service hashicorp/consul -n "$NAMESPACE" -f "$VALUES_DIR/${service}.yaml" --wait --timeout 10m
                ;;
        esac
        echo -e "    ${GREEN}✓ $service${NC}"
    fi
done

# APISIX
echo "  Installing APISIX..."
helm upgrade --install apisix apisix/apisix -n "$NAMESPACE" \
    --set gateway.type=LoadBalancer \
    --wait --timeout 10m && echo -e "    ${GREEN}✓ APISIX${NC}" || echo -e "    ${YELLOW}⚠ APISIX${NC}"

# =============================================================================
# Step 6: Deploy Applications via ArgoCD
# =============================================================================
echo ""
echo -e "${YELLOW}[6/6] Deploying applications via ArgoCD...${NC}"

ARGOCD_APPS="$ISA_CLOUD_DIR/deployments/argocd/apps/staging"
if [ -d "$ARGOCD_APPS" ]; then
    kubectl apply -f "$ARGOCD_APPS/" -n argocd
    echo -e "  ${GREEN}✓ ArgoCD applications deployed${NC}"
else
    echo -e "  ${YELLOW}⚠ ArgoCD apps not found: $ARGOCD_APPS${NC}"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo -e "${BLUE}=============================================="
echo "Staging Environment Ready!"
echo "=============================================="
echo -e "${NC}"
echo "Cluster: $CLUSTER_NAME"
echo "Region: $REGION"
echo "Namespace: $NAMESPACE"
echo ""
echo "ArgoCD:"
echo "  kubectl port-forward svc/argocd-server -n argocd 8080:443"
echo "  URL: https://localhost:8080"
echo "  User: admin"
echo "  Password: $ARGOCD_PASS"
echo ""
echo "Get service endpoints:"
echo "  kubectl get svc -n $NAMESPACE"
echo "=============================================="
