#!/bin/bash
# =============================================================================
# ISA Platform - Production Deployment Script
# =============================================================================
# IMPORTANT: This script requires manual approval for each step.
# Production deployments should go through CI/CD pipeline (ArgoCD).
#
# Usage:
#   ./deploy.sh infrastructure    # Deploy HA infrastructure
#   ./deploy.sh services          # Deploy application services (ArgoCD)
#   ./deploy.sh mlplatform        # Deploy ML platform (Ray, MLflow, JupyterHub)
#   ./deploy.sh etcd              # Deploy etcd cluster only
#   ./deploy.sh all               # Deploy everything (with confirmations)
#   ./deploy.sh status            # Check deployment status
#   ./deploy.sh rollback <name>   # Rollback a Helm release
# =============================================================================

set -e

# Configuration
NAMESPACE="isa-cloud-production"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VALUES_DIR="${SCRIPT_DIR}/../values"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"
TIMEOUT="10m"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $1"; }

confirm() {
    echo -e "${YELLOW}[CONFIRM]${NC} $1"
    read -p "Type 'yes' to continue: " response
    if [[ "$response" != "yes" ]]; then
        log_error "Deployment cancelled"
        exit 1
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check kubectl
    if ! command -v kubectl &>/dev/null; then
        log_error "kubectl not found. Please install kubectl."
        exit 1
    fi

    # Check helm
    if ! command -v helm &>/dev/null; then
        log_error "Helm not found. Please install Helm."
        exit 1
    fi

    # Check kubectl context
    local context=$(kubectl config current-context)
    log_warn "Current kubectl context: ${context}"
    confirm "Are you deploying to the correct PRODUCTION cluster?"

    # Check namespace exists
    if ! kubectl get namespace ${NAMESPACE} &>/dev/null; then
        log_info "Creating namespace ${NAMESPACE}..."
        kubectl create namespace ${NAMESPACE}
    fi

    # Check secrets exist
    local required_secrets=("postgresql-secret" "redis-secret" "neo4j-secret" "minio-secret")
    for secret in "${required_secrets[@]}"; do
        if ! kubectl get secret ${secret} -n ${NAMESPACE} &>/dev/null; then
            log_error "Required secret '${secret}' not found in ${NAMESPACE}"
            log_error "Please create secrets before deploying. See secrets/infrastructure-secrets.yaml"
            exit 1
        fi
    done

    log_info "Prerequisites check passed"
}

# Setup Helm repositories
setup_helm_repos() {
    log_step "Setting up Helm repositories..."

    local repos=(
        "bitnami https://charts.bitnami.com/bitnami"
        "hashicorp https://helm.releases.hashicorp.com"
        "apisix https://charts.apiseven.com"
        "nats https://nats-io.github.io/k8s/helm/charts"
        "qdrant https://qdrant.github.io/qdrant-helm"
        "emqx https://repos.emqx.io/charts"
        "minio https://charts.min.io"
        "neo4j https://helm.neo4j.com/neo4j"
        "kuberay https://ray-project.github.io/kuberay-helm"
    )

    for repo in "${repos[@]}"; do
        local name=$(echo $repo | cut -d' ' -f1)
        local url=$(echo $repo | cut -d' ' -f2)
        if ! helm repo list | grep -q "^${name}"; then
            helm repo add ${name} ${url}
        fi
    done

    helm repo update
    log_info "Helm repositories configured"
}

# Deploy etcd HA cluster
deploy_etcd() {
    log_step "Deploying etcd HA cluster..."

    if [ -f "${MANIFESTS_DIR}/etcd.yaml" ]; then
        kubectl apply -f "${MANIFESTS_DIR}/etcd.yaml"
        log_info "Waiting for etcd cluster to be ready..."
        kubectl wait --for=condition=ready pod -l app=etcd -n ${NAMESPACE} --timeout=180s || true

        # Verify cluster health
        local etcd_pod=$(kubectl get pods -n ${NAMESPACE} -l app=etcd -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
        if [ -n "$etcd_pod" ]; then
            log_info "Checking etcd cluster health..."
            kubectl exec -n ${NAMESPACE} ${etcd_pod} -- etcdctl endpoint health --cluster || log_warn "etcd cluster health check failed"
        fi
    else
        log_error "etcd manifest not found: ${MANIFESTS_DIR}/etcd.yaml"
        exit 1
    fi

    log_info "etcd HA cluster deployed"
}

# Deploy HA infrastructure
deploy_infrastructure() {
    log_info "Deploying HA infrastructure to production..."
    confirm "This will deploy production infrastructure with HA configuration. Continue?"

    setup_helm_repos

    # 1. Deploy etcd first (APISIX dependency)
    deploy_etcd

    # 2. PostgreSQL HA
    log_step "Deploying PostgreSQL HA cluster..."
    helm upgrade --install postgresql bitnami/postgresql-ha \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/postgresql-ha.yaml \
        --wait --timeout ${TIMEOUT}

    # 3. Redis Cluster
    log_step "Deploying Redis cluster..."
    helm upgrade --install redis bitnami/redis-cluster \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/redis-cluster.yaml \
        --wait --timeout ${TIMEOUT}

    # 4. Neo4j Cluster
    log_step "Deploying Neo4j cluster..."
    helm upgrade --install neo4j neo4j/neo4j \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/neo4j-cluster.yaml \
        --wait --timeout ${TIMEOUT}

    # 5. MinIO Distributed
    log_step "Deploying MinIO distributed..."
    helm upgrade --install minio minio/minio \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/minio-distributed.yaml \
        --wait --timeout ${TIMEOUT}

    # 6. NATS JetStream
    log_step "Deploying NATS JetStream cluster..."
    helm upgrade --install nats nats/nats \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/nats-jetstream.yaml \
        --wait --timeout ${TIMEOUT}

    # 7. Qdrant Distributed
    log_step "Deploying Qdrant distributed..."
    helm upgrade --install qdrant qdrant/qdrant \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/qdrant-distributed.yaml \
        --wait --timeout ${TIMEOUT}

    # 8. EMQX Cluster
    log_step "Deploying EMQX MQTT cluster..."
    helm upgrade --install emqx emqx/emqx \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/emqx-cluster.yaml \
        --wait --timeout ${TIMEOUT}

    # 9. Consul Cluster
    log_step "Deploying Consul cluster..."
    helm upgrade --install consul hashicorp/consul \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/consul.yaml \
        --wait --timeout ${TIMEOUT}

    # 10. APISIX
    log_step "Deploying APISIX..."
    helm upgrade --install apisix apisix/apisix \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/apisix.yaml \
        --wait --timeout ${TIMEOUT}

    # 11. Apply Consul-APISIX sync CronJob
    log_step "Applying Consul-APISIX sync CronJob..."
    if [ -f "${MANIFESTS_DIR}/consul-apisix-sync.yaml" ]; then
        kubectl apply -f "${MANIFESTS_DIR}/consul-apisix-sync.yaml"
    fi

    log_info "Infrastructure deployment complete!"
}

# Deploy ML Platform
deploy_mlplatform() {
    log_info "Deploying ML Platform..."
    confirm "This will deploy Ray, MLflow, and JupyterHub. Continue?"

    setup_helm_repos

    # 1. KubeRay Operator
    log_step "Deploying KubeRay Operator..."
    helm upgrade --install kuberay-operator kuberay/kuberay-operator \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/kuberay-operator.yaml \
        --wait --timeout ${TIMEOUT}

    # Wait for operator to be ready
    log_info "Waiting for KubeRay operator..."
    kubectl wait --for=condition=available deployment/kuberay-operator -n ${NAMESPACE} --timeout=120s || true

    # 2. Ray Cluster
    log_step "Deploying Ray Cluster..."
    helm upgrade --install ray-cluster kuberay/ray-cluster \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/ray-cluster.yaml \
        --wait --timeout ${TIMEOUT}

    # 3. MLflow
    log_step "Deploying MLflow..."
    if [ -f "${VALUES_DIR}/mlflow.yaml" ]; then
        helm upgrade --install mlflow bitnami/mlflow \
            -n ${NAMESPACE} \
            -f ${VALUES_DIR}/mlflow.yaml \
            --wait --timeout ${TIMEOUT} 2>/dev/null || {
            log_warn "MLflow Helm chart not available, skipping..."
        }
    fi

    # 4. JupyterHub
    log_step "Deploying JupyterHub..."
    if [ -f "${VALUES_DIR}/jupyterhub.yaml" ]; then
        helm repo add jupyterhub https://jupyterhub.github.io/helm-chart/ 2>/dev/null || true
        helm repo update
        helm upgrade --install jupyterhub jupyterhub/jupyterhub \
            -n ${NAMESPACE} \
            -f ${VALUES_DIR}/jupyterhub.yaml \
            --wait --timeout ${TIMEOUT}
    fi

    log_info "ML Platform deployment complete!"
}

# Deploy application services via ArgoCD
deploy_services() {
    log_info "Deploying application services via ArgoCD..."

    if ! command -v argocd &>/dev/null; then
        log_error "argocd CLI not found. Please install it or use the ArgoCD UI."
        log_info "To install: brew install argocd"
        exit 1
    fi

    # Check ArgoCD connection
    if ! argocd app list &>/dev/null; then
        log_error "Cannot connect to ArgoCD. Please login first: argocd login <server>"
        exit 1
    fi

    # List production applications
    local apps=$(argocd app list -o name 2>/dev/null | grep -E "production" || true)

    if [ -z "$apps" ]; then
        log_warn "No production ArgoCD applications found."
        return
    fi

    echo -e "\n${BLUE}Production applications:${NC}"
    echo "$apps"
    echo ""

    # Dry-run first
    log_step "Running dry-run sync..."
    for app in $apps; do
        echo -e "\n${CYAN}Dry-run: ${app}${NC}"
        argocd app diff ${app} --refresh 2>/dev/null || true
    done

    confirm "Review the changes above. Proceed with sync?"

    # Actual sync
    for app in $apps; do
        log_step "Syncing ${app}..."
        argocd app sync ${app} --prune --force
    done

    log_info "ArgoCD sync complete"
}

# Check status (enhanced)
check_status() {
    log_info "Checking production deployment status..."

    echo -e "\n${BLUE}=== Namespace ===${NC}"
    kubectl get namespace ${NAMESPACE} 2>/dev/null || echo "Namespace not found"

    echo -e "\n${BLUE}=== Helm Releases ===${NC}"
    helm list -n ${NAMESPACE}

    echo -e "\n${BLUE}=== Pod Status ===${NC}"
    kubectl get pods -n ${NAMESPACE} -o wide

    echo -e "\n${BLUE}=== Services ===${NC}"
    kubectl get svc -n ${NAMESPACE}

    echo -e "\n${BLUE}=== PVCs ===${NC}"
    kubectl get pvc -n ${NAMESPACE}

    echo -e "\n${BLUE}=== Pod Disruption Budgets ===${NC}"
    kubectl get pdb -n ${NAMESPACE} 2>/dev/null || echo "No PDBs configured"

    echo -e "\n${BLUE}=== HPA Status ===${NC}"
    kubectl get hpa -n ${NAMESPACE} 2>/dev/null || echo "No HPA configured"

    echo -e "\n${BLUE}=== ArgoCD Applications ===${NC}"
    if command -v argocd &>/dev/null; then
        argocd app list 2>/dev/null | grep -E "production|${NAMESPACE}" || echo "No ArgoCD applications found"
    else
        echo "argocd CLI not installed"
    fi

    echo -e "\n${BLUE}=== Recent Events (warnings) ===${NC}"
    kubectl get events -n ${NAMESPACE} --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | tail -10 || echo "No warning events"
}

# Rollback
rollback() {
    local release="$1"
    if [[ -z "$release" ]]; then
        log_error "Release name required"
        echo "Usage: $0 rollback <release-name>"
        echo ""
        echo "Available releases:"
        helm list -n ${NAMESPACE} --short
        exit 1
    fi

    # Show current and previous revisions
    echo -e "\n${BLUE}Release history for ${release}:${NC}"
    helm history ${release} -n ${NAMESPACE} | tail -5

    confirm "Rolling back ${release} in PRODUCTION. This may cause downtime. Continue?"

    helm rollback ${release} -n ${NAMESPACE}
    log_info "Rollback complete. Check status with: $0 status"
}

# Deploy all
deploy_all() {
    log_info "Starting full production deployment..."
    confirm "This will deploy ALL components to PRODUCTION. Are you absolutely sure?"

    check_prerequisites
    deploy_infrastructure
    deploy_mlplatform
    deploy_services

    log_info "Full production deployment complete!"
    check_status
}

# Usage
usage() {
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  infrastructure    Deploy HA infrastructure (etcd, PostgreSQL, Redis, etc.)"
    echo "  services          Deploy application services via ArgoCD"
    echo "  mlplatform        Deploy ML platform (Ray, MLflow, JupyterHub)"
    echo "  etcd              Deploy etcd HA cluster only"
    echo "  all               Deploy everything (infrastructure + ML + services)"
    echo "  status            Check deployment status"
    echo "  rollback <name>   Rollback a Helm release"
    echo ""
    echo "Examples:"
    echo "  $0 status                    # Check current status"
    echo "  $0 infrastructure            # Deploy databases and messaging"
    echo "  $0 mlplatform                # Deploy ML components"
    echo "  $0 rollback postgresql       # Rollback PostgreSQL"
    echo ""
    echo "NOTE: Production deployments require explicit confirmation."
    echo "      For routine deployments, use ArgoCD GitOps workflow."
}

# Main
main() {
    local command="${1:-}"
    shift || true

    case "${command}" in
        infrastructure)
            check_prerequisites
            deploy_infrastructure
            ;;
        services)
            deploy_services
            ;;
        mlplatform)
            check_prerequisites
            deploy_mlplatform
            ;;
        etcd)
            check_prerequisites
            setup_helm_repos
            deploy_etcd
            ;;
        all)
            deploy_all
            ;;
        status)
            check_status
            ;;
        rollback)
            rollback "$@"
            ;;
        -h|--help)
            usage
            ;;
        "")
            usage
            ;;
        *)
            log_error "Unknown command: ${command}"
            usage
            exit 1
            ;;
    esac
}

main "$@"
