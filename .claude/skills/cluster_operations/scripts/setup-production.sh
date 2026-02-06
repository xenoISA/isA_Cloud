#!/bin/bash
# =============================================================================
# Production Environment Setup (EKS/GKE/AKS)
# =============================================================================
# Sets up production environment with HA configurations
#
# IMPORTANT: Production deployments require:
#   - Proper secrets management (AWS Secrets Manager, Vault)
#   - Network policies
#   - Resource quotas
#   - Monitoring and alerting
#
# Usage:
#   ./setup-production.sh                    # Setup on existing cluster
#   ./setup-production.sh --create-cluster   # Create EKS cluster first
#   ./setup-production.sh --dry-run          # Preview changes only
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISA_CLOUD_DIR="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"

CLUSTER_NAME="${CLUSTER_NAME:-isa-cloud-production}"
NAMESPACE="isa-cloud-production"
REGION="${AWS_REGION:-us-east-1}"
CREATE_CLUSTER=false
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --create-cluster) CREATE_CLUSTER=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
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
echo "ISA Cloud - PRODUCTION Environment Setup"
echo "=============================================="
echo -e "${NC}"

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}DRY RUN MODE - No changes will be made${NC}"
    echo ""
fi

# Safety check
echo -e "${RED}⚠️  WARNING: This will modify PRODUCTION environment!${NC}"
read -p "Are you sure you want to continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

# =============================================================================
# Step 1: Create/Connect to Production Cluster
# =============================================================================
echo -e "${YELLOW}[1/7] Setting up production cluster...${NC}"

if [ "$CREATE_CLUSTER" = true ]; then
    echo "  Creating production EKS cluster: $CLUSTER_NAME"

    if [ "$DRY_RUN" = false ]; then
        eksctl create cluster \
            --name "$CLUSTER_NAME" \
            --region "$REGION" \
            --nodegroup-name workers \
            --node-type m5.2xlarge \
            --nodes 5 \
            --nodes-min 3 \
            --nodes-max 10 \
            --managed \
            --asg-access \
            --full-ecr-access
    fi
    echo -e "  ${GREEN}✓ Production cluster created${NC}"
fi

# Configure kubectl
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$REGION" 2>/dev/null || true

if ! kubectl cluster-info &>/dev/null; then
    echo -e "${RED}ERROR: Cannot connect to cluster${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓ Connected to cluster${NC}"

# =============================================================================
# Step 2: Create Namespace with Resource Quotas
# =============================================================================
echo ""
echo -e "${YELLOW}[2/7] Creating namespace with production quotas...${NC}"

if [ "$DRY_RUN" = false ]; then
    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

    # Apply resource quotas
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ResourceQuota
metadata:
  name: production-quota
  namespace: $NAMESPACE
spec:
  hard:
    requests.cpu: "100"
    requests.memory: 200Gi
    limits.cpu: "200"
    limits.memory: 400Gi
    persistentvolumeclaims: "50"
    services.loadbalancers: "10"
EOF
fi
echo -e "  ${GREEN}✓ Namespace and quotas configured${NC}"

# =============================================================================
# Step 3: Install External Secrets Operator
# =============================================================================
echo ""
echo -e "${YELLOW}[3/7] Installing External Secrets Operator...${NC}"

if [ "$DRY_RUN" = false ]; then
    helm repo add external-secrets https://charts.external-secrets.io
    helm repo update

    helm upgrade --install external-secrets external-secrets/external-secrets \
        -n external-secrets --create-namespace \
        --wait --timeout 5m
fi
echo -e "  ${GREEN}✓ External Secrets Operator installed${NC}"

# =============================================================================
# Step 4: Add Helm Repos
# =============================================================================
echo ""
echo -e "${YELLOW}[4/7] Adding Helm repositories...${NC}"

helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
helm repo add qdrant https://qdrant.github.io/qdrant-helm 2>/dev/null || true
helm repo add nats https://nats-io.github.io/k8s/helm/charts/ 2>/dev/null || true
helm repo add hashicorp https://helm.releases.hashicorp.com 2>/dev/null || true
helm repo add apisix https://charts.apiseven.com 2>/dev/null || true
helm repo update
echo -e "  ${GREEN}✓ Helm repos configured${NC}"

# =============================================================================
# Step 5: Deploy HA Infrastructure
# =============================================================================
echo ""
echo -e "${YELLOW}[5/7] Deploying HA infrastructure...${NC}"

VALUES_DIR="$ISA_CLOUD_DIR/deployments/kubernetes/production/values"

if [ "$DRY_RUN" = false ]; then
    # PostgreSQL HA
    echo "  Installing PostgreSQL HA..."
    if [ -f "$VALUES_DIR/postgresql-ha.yaml" ]; then
        helm upgrade --install postgresql bitnami/postgresql-ha \
            -n "$NAMESPACE" -f "$VALUES_DIR/postgresql-ha.yaml" \
            --wait --timeout 15m && echo -e "    ${GREEN}✓ PostgreSQL HA${NC}"
    else
        helm upgrade --install postgresql bitnami/postgresql-ha \
            -n "$NAMESPACE" \
            --set postgresql.replicaCount=3 \
            --set pgpool.replicaCount=2 \
            --wait --timeout 15m && echo -e "    ${GREEN}✓ PostgreSQL HA${NC}"
    fi

    # Redis Cluster
    echo "  Installing Redis Cluster..."
    if [ -f "$VALUES_DIR/redis-cluster.yaml" ]; then
        helm upgrade --install redis bitnami/redis-cluster \
            -n "$NAMESPACE" -f "$VALUES_DIR/redis-cluster.yaml" \
            --wait --timeout 15m && echo -e "    ${GREEN}✓ Redis Cluster${NC}"
    else
        helm upgrade --install redis bitnami/redis-cluster \
            -n "$NAMESPACE" \
            --set cluster.nodes=6 \
            --set cluster.replicas=1 \
            --wait --timeout 15m && echo -e "    ${GREEN}✓ Redis Cluster${NC}"
    fi

    # Qdrant Distributed
    echo "  Installing Qdrant Distributed..."
    if [ -f "$VALUES_DIR/qdrant-distributed.yaml" ]; then
        helm upgrade --install qdrant qdrant/qdrant \
            -n "$NAMESPACE" -f "$VALUES_DIR/qdrant-distributed.yaml" \
            --wait --timeout 15m && echo -e "    ${GREEN}✓ Qdrant Distributed${NC}"
    fi

    # MinIO Distributed
    echo "  Installing MinIO Distributed..."
    if [ -f "$VALUES_DIR/minio-distributed.yaml" ]; then
        helm upgrade --install minio bitnami/minio \
            -n "$NAMESPACE" -f "$VALUES_DIR/minio-distributed.yaml" \
            --wait --timeout 15m && echo -e "    ${GREEN}✓ MinIO Distributed${NC}"
    fi

    # Neo4j Cluster
    echo "  Installing Neo4j Cluster..."
    if [ -f "$VALUES_DIR/neo4j-cluster.yaml" ]; then
        helm upgrade --install neo4j bitnami/neo4j \
            -n "$NAMESPACE" -f "$VALUES_DIR/neo4j-cluster.yaml" \
            --wait --timeout 15m && echo -e "    ${GREEN}✓ Neo4j Cluster${NC}"
    fi

    # NATS JetStream Cluster
    echo "  Installing NATS JetStream Cluster..."
    if [ -f "$VALUES_DIR/nats-jetstream.yaml" ]; then
        helm upgrade --install nats nats/nats \
            -n "$NAMESPACE" -f "$VALUES_DIR/nats-jetstream.yaml" \
            --wait --timeout 15m && echo -e "    ${GREEN}✓ NATS Cluster${NC}"
    fi

    # Consul HA
    echo "  Installing Consul HA..."
    helm upgrade --install consul hashicorp/consul \
        -n "$NAMESPACE" \
        --set server.replicas=3 \
        --set server.bootstrapExpect=3 \
        --wait --timeout 15m && echo -e "    ${GREEN}✓ Consul HA${NC}"

    # APISIX with multiple replicas
    echo "  Installing APISIX HA..."
    helm upgrade --install apisix apisix/apisix \
        -n "$NAMESPACE" \
        --set apisix.replicaCount=3 \
        --set etcd.replicaCount=3 \
        --set gateway.type=LoadBalancer \
        --wait --timeout 15m && echo -e "    ${GREEN}✓ APISIX HA${NC}"
fi

# =============================================================================
# Step 6: Install Monitoring Stack
# =============================================================================
echo ""
echo -e "${YELLOW}[6/7] Installing monitoring stack...${NC}"

if [ "$DRY_RUN" = false ]; then
    # Prometheus + Grafana
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
    helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
        -n monitoring --create-namespace \
        --set grafana.enabled=true \
        --set alertmanager.enabled=true \
        --wait --timeout 10m && echo -e "  ${GREEN}✓ Prometheus + Grafana${NC}"
fi

# =============================================================================
# Step 7: Deploy Applications via ArgoCD
# =============================================================================
echo ""
echo -e "${YELLOW}[7/7] Deploying applications via ArgoCD...${NC}"

if [ "$DRY_RUN" = false ]; then
    # Install ArgoCD
    kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
    kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/ha/install.yaml
    kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd

    # Deploy production apps
    ARGOCD_APPS="$ISA_CLOUD_DIR/deployments/argocd/apps/production"
    if [ -d "$ARGOCD_APPS" ]; then
        kubectl apply -f "$ARGOCD_APPS/" -n argocd
        echo -e "  ${GREEN}✓ ArgoCD applications deployed${NC}"
    fi
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo -e "${BLUE}=============================================="
echo "Production Environment Ready!"
echo "=============================================="
echo -e "${NC}"
echo "Cluster: $CLUSTER_NAME"
echo "Region: $REGION"
echo "Namespace: $NAMESPACE"
echo ""
echo "IMPORTANT POST-SETUP TASKS:"
echo "  1. Configure DNS for production endpoints"
echo "  2. Set up SSL certificates"
echo "  3. Configure backup schedules"
echo "  4. Set up alerting rules"
echo "  5. Review and apply network policies"
echo ""
echo "Monitoring:"
echo "  kubectl port-forward svc/prometheus-grafana -n monitoring 3000:80"
echo "  URL: http://localhost:3000 (admin/prom-operator)"
echo ""
echo "Get service endpoints:"
echo "  kubectl get svc -n $NAMESPACE"
echo "=============================================="
