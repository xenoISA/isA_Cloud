#!/bin/bash
# =============================================================================
# ISA Platform - Staging Deployment Script
# =============================================================================
# Deploys the ISA Cloud platform to staging environment.
# Based on local/kind-deploy.sh patterns with Helm-based infrastructure.
#
# Usage:
#   ./deploy.sh infrastructure    # Deploy infrastructure services
#   ./deploy.sh services          # Sync ArgoCD application services
#   ./deploy.sh etcd              # Deploy etcd only
#   ./deploy.sh all               # Deploy everything
#   ./deploy.sh status            # Check deployment status
# =============================================================================

set -e

# Configuration
NAMESPACE="isa-cloud-staging"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VALUES_DIR="${SCRIPT_DIR}/../values"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"
TIMEOUT="8m"

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
    log_info "Current kubectl context: ${context}"

    # Create namespace if not exists
    if ! kubectl get namespace ${NAMESPACE} &>/dev/null; then
        log_info "Creating namespace ${NAMESPACE}..."
        kubectl create namespace ${NAMESPACE}
    fi

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

# Check required secrets
check_secrets() {
    log_step "Checking required secrets..."

    local required_secrets=("postgresql-secret" "redis-secret" "neo4j-secret" "minio-secret")
    local missing=0

    for secret in "${required_secrets[@]}"; do
        if ! kubectl get secret ${secret} -n ${NAMESPACE} &>/dev/null; then
            log_warn "Secret '${secret}' not found"
            missing=$((missing + 1))
        fi
    done

    if [ $missing -gt 0 ]; then
        log_warn "Missing ${missing} secrets. Apply secrets from: ../secrets/infrastructure-secrets.yaml"
        echo -e "${YELLOW}To apply secrets:${NC}"
        echo "  kubectl apply -f ${SCRIPT_DIR}/../secrets/infrastructure-secrets.yaml"
        echo ""
        read -p "Continue anyway? (yes/no): " response
        if [[ "$response" != "yes" ]]; then
            log_error "Deployment cancelled. Please create required secrets."
            exit 1
        fi
    fi
}

# Deploy etcd (APISIX dependency)
deploy_etcd() {
    log_step "Deploying etcd..."

    if [ -f "${MANIFESTS_DIR}/etcd.yaml" ]; then
        kubectl apply -f "${MANIFESTS_DIR}/etcd.yaml"
        log_info "Waiting for etcd to be ready..."
        kubectl wait --for=condition=ready pod -l app=etcd -n ${NAMESPACE} --timeout=120s || true
    else
        log_error "etcd manifest not found: ${MANIFESTS_DIR}/etcd.yaml"
        exit 1
    fi

    log_info "etcd deployed"
}

# Deploy infrastructure services
deploy_infrastructure() {
    log_info "Deploying staging infrastructure..."

    # 1. Deploy etcd first (APISIX dependency)
    deploy_etcd

    # 2. Deploy databases
    log_step "Deploying PostgreSQL..."
    helm upgrade --install postgresql bitnami/postgresql \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/postgresql.yaml \
        --wait --timeout ${TIMEOUT}

    log_step "Deploying Redis..."
    helm upgrade --install redis bitnami/redis \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/redis.yaml \
        --wait --timeout ${TIMEOUT}

    log_step "Deploying Neo4j..."
    helm upgrade --install neo4j neo4j/neo4j \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/neo4j.yaml \
        --wait --timeout ${TIMEOUT}

    # 3. Deploy object storage
    log_step "Deploying MinIO..."
    helm upgrade --install minio minio/minio \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/minio.yaml \
        --wait --timeout ${TIMEOUT}

    # 4. Deploy messaging
    log_step "Deploying NATS..."
    helm upgrade --install nats nats/nats \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/nats.yaml \
        --wait --timeout ${TIMEOUT}

    log_step "Deploying EMQX (MQTT)..."
    helm upgrade --install emqx emqx/emqx \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/emqx.yaml \
        --wait --timeout ${TIMEOUT}

    # 5. Deploy vector database
    log_step "Deploying Qdrant..."
    helm upgrade --install qdrant qdrant/qdrant \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/qdrant.yaml \
        --wait --timeout ${TIMEOUT}

    # 6. Deploy service discovery
    log_step "Deploying Consul..."
    helm upgrade --install consul hashicorp/consul \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/consul.yaml \
        --wait --timeout ${TIMEOUT}

    # 7. Deploy API Gateway
    log_step "Deploying APISIX..."
    helm upgrade --install apisix apisix/apisix \
        -n ${NAMESPACE} \
        -f ${VALUES_DIR}/apisix.yaml \
        --wait --timeout ${TIMEOUT}

    # 8. Apply consul-apisix sync cronjob
    log_step "Applying Consul-APISIX sync CronJob..."
    if [ -f "${MANIFESTS_DIR}/consul-apisix-sync.yaml" ]; then
        kubectl apply -f "${MANIFESTS_DIR}/consul-apisix-sync.yaml"
    fi

    log_info "Infrastructure deployment complete!"
}

# Deploy application services via ArgoCD
deploy_services() {
    log_info "Deploying application services..."

    if ! command -v argocd &>/dev/null; then
        log_warn "argocd CLI not found. Skipping ArgoCD sync."
        log_info "To deploy services, use: argocd app sync <app-name>"
        return
    fi

    log_step "Syncing ArgoCD applications..."

    # List available applications
    local apps=$(argocd app list -o name 2>/dev/null | grep -E "staging" || true)

    if [ -z "$apps" ]; then
        log_warn "No staging ArgoCD applications found."
        return
    fi

    echo "Available staging applications:"
    echo "$apps"
    echo ""

    read -p "Sync all staging applications? (yes/no): " response
    if [[ "$response" == "yes" ]]; then
        for app in $apps; do
            log_step "Syncing ${app}..."
            argocd app sync ${app} --prune
        done
        log_info "ArgoCD sync complete"
    else
        log_info "Skipping ArgoCD sync"
    fi
}

# Check deployment status
check_status() {
    log_info "Checking staging deployment status..."

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

    echo -e "\n${BLUE}=== Recent Events (warnings) ===${NC}"
    kubectl get events -n ${NAMESPACE} --field-selector type=Warning --sort-by='.lastTimestamp' 2>/dev/null | tail -10 || echo "No warning events"
}

# Deploy all
deploy_all() {
    log_info "Starting full staging deployment..."
    echo ""

    check_prerequisites
    setup_helm_repos
    check_secrets
    deploy_infrastructure
    deploy_services

    echo ""
    log_info "Full deployment complete!"
    echo ""
    check_status
}

# Interactive mode
interactive_mode() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}ISA Cloud - Staging Deployment${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo "Deployment options:"
    echo "  1) Full deployment (infrastructure + services)"
    echo "  2) Infrastructure only (etcd, databases, messaging, gateway)"
    echo "  3) Services only (ArgoCD sync)"
    echo "  4) etcd only"
    echo "  5) Check status"
    echo ""
    read -p "Select option (1-5): " choice

    case $choice in
        1)
            deploy_all
            ;;
        2)
            check_prerequisites
            setup_helm_repos
            check_secrets
            deploy_infrastructure
            ;;
        3)
            deploy_services
            ;;
        4)
            check_prerequisites
            deploy_etcd
            ;;
        5)
            check_status
            ;;
        *)
            log_error "Invalid option"
            exit 1
            ;;
    esac
}

# Usage
usage() {
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  infrastructure    Deploy infrastructure (etcd, databases, messaging, gateway)"
    echo "  services          Sync ArgoCD application services"
    echo "  etcd              Deploy etcd only"
    echo "  all               Deploy everything"
    echo "  status            Check deployment status"
    echo ""
    echo "Interactive mode:"
    echo "  $0                Run without arguments for interactive menu"
}

# Main
main() {
    local command="${1:-}"

    case "${command}" in
        infrastructure)
            check_prerequisites
            setup_helm_repos
            check_secrets
            deploy_infrastructure
            ;;
        services)
            deploy_services
            ;;
        etcd)
            check_prerequisites
            deploy_etcd
            ;;
        all)
            deploy_all
            ;;
        status)
            check_status
            ;;
        -h|--help)
            usage
            ;;
        "")
            interactive_mode
            ;;
        *)
            log_error "Unknown command: ${command}"
            usage
            exit 1
            ;;
    esac
}

main "$@"
