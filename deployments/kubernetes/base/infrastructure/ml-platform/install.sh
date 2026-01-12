#!/bin/bash
# Install ML Platform for Kind (Local Development)
# Usage: ./install.sh

set -e

echo "=========================================="
echo "  isA ML Platform - Kind Installation"
echo "=========================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check kubectl
if ! command -v kubectl &> /dev/null; then
    echo "kubectl not found. Please install kubectl first."
    exit 1
fi

# Check cluster
CONTEXT=$(kubectl config current-context 2>/dev/null || echo "")
if [[ -z "$CONTEXT" ]]; then
    echo "No Kubernetes context found. Please configure kubectl."
    exit 1
fi
echo -e "${GREEN}Using context: ${CONTEXT}${NC}"

# Step 1: Install Ray CRDs
echo ""
echo -e "${YELLOW}Step 1: Installing Ray CRDs...${NC}"
kubectl apply -f https://raw.githubusercontent.com/ray-project/kuberay/v1.2.2/ray-operator/config/crd/bases/ray.io_rayclusters.yaml
kubectl apply -f https://raw.githubusercontent.com/ray-project/kuberay/v1.2.2/ray-operator/config/crd/bases/ray.io_rayjobs.yaml
kubectl apply -f https://raw.githubusercontent.com/ray-project/kuberay/v1.2.2/ray-operator/config/crd/bases/ray.io_rayservices.yaml
echo -e "${GREEN}Ray CRDs installed${NC}"

# Step 2: Apply ML Platform manifests
echo ""
echo -e "${YELLOW}Step 2: Applying ML Platform manifests...${NC}"
kubectl apply -k .
echo -e "${GREEN}ML Platform manifests applied${NC}"

# Step 3: Wait for deployments
echo ""
echo -e "${YELLOW}Step 3: Waiting for deployments...${NC}"

echo "Waiting for KubeRay operator..."
kubectl wait --for=condition=available --timeout=120s deployment/kuberay-operator -n ray-system || true

echo "Waiting for MLflow..."
kubectl wait --for=condition=available --timeout=120s deployment/mlflow -n mlflow || true

echo "Waiting for JupyterHub..."
kubectl wait --for=condition=available --timeout=120s deployment/jupyterhub -n isa-cloud-staging || true

# Step 4: Setup port-forwarding
echo ""
echo -e "${YELLOW}Step 4: Port forwarding commands:${NC}"
echo ""
echo "# Ray Dashboard (8265)"
echo "kubectl port-forward svc/ray-dashboard 8265:8265 -n isa-cloud-staging"
echo ""
echo "# MLflow (5000)"
echo "kubectl port-forward svc/mlflow 5000:5000 -n mlflow"
echo ""
echo "# JupyterHub (8888)"
echo "kubectl port-forward svc/jupyterhub 8888:8888 -n isa-cloud-staging"
echo ""

# Step 5: Show status
echo ""
echo -e "${YELLOW}Step 5: ML Platform Status${NC}"
echo ""
echo "KubeRay Operator:"
kubectl get pods -n ray-system -l app.kubernetes.io/name=kuberay-operator
echo ""
echo "Ray Cluster:"
kubectl get rayclusters -n isa-cloud-staging 2>/dev/null || echo "No RayCluster yet (operator needs to create it)"
echo ""
echo "MLflow:"
kubectl get pods -n mlflow -l app.kubernetes.io/name=mlflow
echo ""
echo "JupyterHub:"
kubectl get pods -n isa-cloud-staging -l app.kubernetes.io/name=jupyterhub
echo ""

echo "=========================================="
echo -e "${GREEN}  ML Platform Installation Complete!${NC}"
echo "=========================================="
echo ""
echo "Access URLs (after port-forwarding):"
echo "  - Ray Dashboard: http://localhost:8265"
echo "  - MLflow:        http://localhost:5000"
echo "  - JupyterHub:    http://localhost:8888"
echo ""
