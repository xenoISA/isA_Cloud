#!/bin/bash
# Production Infrastructure Deployment Script
# Usage: ./deploy.sh [all|component-name] [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRODUCTION_DIR="$(dirname "$SCRIPT_DIR")"
NAMESPACE="isa-cloud-production"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found. Please install kubectl."
        exit 1
    fi

    if ! command -v helm &> /dev/null; then
        log_error "helm not found. Please install helm."
        exit 1
    fi

    if ! command -v helmfile &> /dev/null; then
        log_warn "helmfile not found. Will use helm directly."
        USE_HELMFILE=false
    else
        USE_HELMFILE=true
    fi

    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster. Check your kubeconfig."
        exit 1
    fi

    log_success "Prerequisites check passed"
}

# Add Helm repositories
add_helm_repos() {
    log_info "Adding Helm repositories..."

    helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
    helm repo add nats https://nats-io.github.io/k8s/helm/charts/ 2>/dev/null || true
    helm repo add minio https://charts.min.io/ 2>/dev/null || true
    helm repo add qdrant https://qdrant.github.io/qdrant-helm/ 2>/dev/null || true
    helm repo add neo4j https://helm.neo4j.com/neo4j 2>/dev/null || true
    helm repo add emqx https://repos.emqx.io/charts 2>/dev/null || true

    helm repo update

    log_success "Helm repositories updated"
}

# Deploy storage classes
deploy_storage() {
    log_info "Deploying storage classes..."

    if [[ "$DRY_RUN" == "true" ]]; then
        kubectl apply -f "$PRODUCTION_DIR/storage/storage-classes.yaml" --dry-run=client
    else
        kubectl apply -f "$PRODUCTION_DIR/storage/storage-classes.yaml"
    fi

    log_success "Storage classes deployed"
}

# Deploy namespace and RBAC
deploy_namespace() {
    log_info "Deploying namespace and RBAC..."

    if [[ "$DRY_RUN" == "true" ]]; then
        kubectl apply -f "$PRODUCTION_DIR/namespace.yaml" --dry-run=client
    else
        kubectl apply -f "$PRODUCTION_DIR/namespace.yaml"
    fi

    log_success "Namespace and RBAC deployed"
}

# Generic Helm deploy function
deploy_helm_chart() {
    local name=$1
    local chart=$2
    local values_file=$3
    local extra_args=${4:-""}

    log_info "Deploying $name..."

    local cmd="helm upgrade --install $name $chart \
        --namespace $NAMESPACE \
        --values $PRODUCTION_DIR/helm/values/$values_file \
        --wait --timeout 10m \
        $extra_args"

    if [[ "$DRY_RUN" == "true" ]]; then
        cmd="$cmd --dry-run"
    fi

    eval $cmd

    log_success "$name deployed"
}

# Deploy PostgreSQL HA
deploy_postgresql() {
    log_info "Deploying PostgreSQL HA..."

    # Check if secrets exist
    if [[ "$DRY_RUN" != "true" ]]; then
        if ! kubectl get secret postgresql-credentials -n "$NAMESPACE" &> /dev/null; then
            log_warn "Creating PostgreSQL credentials secret..."
            read -sp "Enter PostgreSQL admin password: " PG_PASSWORD
            echo
            kubectl create secret generic postgresql-credentials \
                --namespace "$NAMESPACE" \
                --from-literal=postgres-password="$PG_PASSWORD" \
                --from-literal=replication-password="$PG_PASSWORD" \
                --from-literal=password="$PG_PASSWORD"
        fi
    fi

    deploy_helm_chart "postgresql" "bitnami/postgresql-ha" "postgresql-ha.yaml" \
        "--set global.postgresql.auth.existingSecret=postgresql-credentials"
}

# Deploy Redis Cluster
deploy_redis() {
    if [[ "$DRY_RUN" != "true" ]]; then
        if ! kubectl get secret redis-credentials -n "$NAMESPACE" &> /dev/null; then
            log_warn "Creating Redis credentials secret..."
            read -sp "Enter Redis password: " REDIS_PASSWORD
            echo
            kubectl create secret generic redis-credentials \
                --namespace "$NAMESPACE" \
                --from-literal=redis-password="$REDIS_PASSWORD"
        fi
    fi

    deploy_helm_chart "redis" "bitnami/redis-cluster" "redis-cluster.yaml" \
        "--set global.redis.existingSecret=redis-credentials"
}

# Deploy NATS JetStream
deploy_nats() {
    deploy_helm_chart "nats" "nats/nats" "nats-jetstream.yaml"
}

# Deploy MinIO Distributed
deploy_minio() {
    if [[ "$DRY_RUN" != "true" ]]; then
        if ! kubectl get secret minio-credentials -n "$NAMESPACE" &> /dev/null; then
            log_warn "Creating MinIO credentials secret..."
            read -p "Enter MinIO root user: " MINIO_USER
            read -sp "Enter MinIO root password: " MINIO_PASSWORD
            echo
            kubectl create secret generic minio-credentials \
                --namespace "$NAMESPACE" \
                --from-literal=rootUser="$MINIO_USER" \
                --from-literal=rootPassword="$MINIO_PASSWORD"
        fi
    fi

    deploy_helm_chart "minio" "minio/minio" "minio-distributed.yaml" \
        "--set existingSecret=minio-credentials"
}

# Deploy Qdrant Distributed
deploy_qdrant() {
    deploy_helm_chart "qdrant" "qdrant/qdrant" "qdrant-distributed.yaml"
}

# Deploy Neo4j Cluster
deploy_neo4j() {
    if [[ "$DRY_RUN" != "true" ]]; then
        if ! kubectl get secret neo4j-credentials -n "$NAMESPACE" &> /dev/null; then
            log_warn "Creating Neo4j credentials secret..."
            read -sp "Enter Neo4j password: " NEO4J_PASSWORD
            echo
            kubectl create secret generic neo4j-credentials \
                --namespace "$NAMESPACE" \
                --from-literal=NEO4J_AUTH="neo4j/$NEO4J_PASSWORD"
        fi
    fi

    deploy_helm_chart "neo4j" "neo4j/neo4j" "neo4j-cluster.yaml" \
        "--set neo4j.passwordFromSecret=neo4j-credentials"
}

# Deploy EMQX Cluster
deploy_emqx() {
    if [[ "$DRY_RUN" != "true" ]]; then
        if ! kubectl get secret emqx-credentials -n "$NAMESPACE" &> /dev/null; then
            log_warn "Creating EMQX credentials secret..."
            COOKIE=$(openssl rand -hex 32)
            read -sp "Enter EMQX dashboard password: " EMQX_PASSWORD
            echo
            kubectl create secret generic emqx-credentials \
                --namespace "$NAMESPACE" \
                --from-literal=cookie="$COOKIE" \
                --from-literal=dashboard-password="$EMQX_PASSWORD"
        fi
    fi

    deploy_helm_chart "emqx" "emqx/emqx" "emqx-cluster.yaml" \
        "--set emqxConfig.EMQX_NODE__COOKIE=\$(kubectl get secret emqx-credentials -n $NAMESPACE -o jsonpath='{.data.cookie}' | base64 -d)"
}

# Deploy all components
deploy_all() {
    deploy_storage
    deploy_namespace

    log_info "Waiting for namespace to be ready..."
    sleep 5

    deploy_postgresql
    deploy_redis
    deploy_nats
    deploy_minio
    deploy_qdrant
    deploy_neo4j
    deploy_emqx

    log_success "All components deployed successfully!"
}

# Show deployment status
show_status() {
    log_info "Deployment Status:"
    echo
    kubectl get pods -n "$NAMESPACE" -o wide
    echo
    kubectl get pvc -n "$NAMESPACE"
    echo
    kubectl get svc -n "$NAMESPACE"
}

# Main entry point
main() {
    DRY_RUN="false"
    COMPONENT="${1:-all}"

    # Parse arguments
    for arg in "$@"; do
        case $arg in
            --dry-run)
                DRY_RUN="true"
                log_warn "Running in dry-run mode"
                ;;
        esac
    done

    check_prerequisites
    add_helm_repos

    case "$COMPONENT" in
        all)
            deploy_all
            ;;
        storage)
            deploy_storage
            ;;
        namespace)
            deploy_namespace
            ;;
        postgresql|postgres|pg)
            deploy_postgresql
            ;;
        redis)
            deploy_redis
            ;;
        nats)
            deploy_nats
            ;;
        minio)
            deploy_minio
            ;;
        qdrant)
            deploy_qdrant
            ;;
        neo4j)
            deploy_neo4j
            ;;
        emqx|mqtt)
            deploy_emqx
            ;;
        status)
            show_status
            ;;
        *)
            log_error "Unknown component: $COMPONENT"
            echo "Usage: $0 [all|storage|namespace|postgresql|redis|nats|minio|qdrant|neo4j|emqx|status] [--dry-run]"
            exit 1
            ;;
    esac

    if [[ "$COMPONENT" != "status" && "$DRY_RUN" != "true" ]]; then
        show_status
    fi
}

main "$@"
