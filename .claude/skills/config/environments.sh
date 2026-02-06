#!/bin/bash
# =============================================================================
# Environment Configuration for isA Cloud Skills
# =============================================================================
# This file defines all environment-specific configurations.
# Source this file in any skill script: source "$(dirname "$0")/../../config/environments.sh"
#
# Environments:
#   - local:      Kind cluster for local development
#   - staging:    EKS/GKE staging cluster
#   - production: EKS/GKE production cluster
# =============================================================================

# -----------------------------------------------------------------------------
# Auto-detect Current Environment
# -----------------------------------------------------------------------------

detect_environment() {
    local current_context
    current_context=$(kubectl config current-context 2>/dev/null)

    if [[ "$current_context" == *"kind-isa-cloud-local"* ]]; then
        echo "local"
    elif [[ "$current_context" == *"isa-cloud-staging"* ]]; then
        echo "staging"
    elif [[ "$current_context" == *"isa-cloud-production"* ]]; then
        echo "production"
    else
        # Fallback: check namespace existence
        if kubectl get namespace isa-cloud-local &>/dev/null; then
            echo "local"
        elif kubectl get namespace isa-cloud-staging &>/dev/null; then
            echo "staging"
        elif kubectl get namespace isa-cloud-production &>/dev/null; then
            echo "production"
        else
            echo "unknown"
        fi
    fi
}

# -----------------------------------------------------------------------------
# Load Environment Configuration
# -----------------------------------------------------------------------------

load_environment() {
    local env_name="${1:-}"

    # Auto-detect if not specified
    if [ -z "$env_name" ]; then
        env_name=$(detect_environment)
    fi

    # Export common variables
    export ISA_ENV="$env_name"

    case "$env_name" in
        local)
            export CLUSTER_NAME="isa-cloud-local"
            export NAMESPACE="isa-cloud-local"
            export KUBE_CONTEXT="kind-isa-cloud-local"
            export CONSUL_URL="http://localhost:8500"
            export APISIX_ADMIN="http://localhost:9180"
            export APISIX_GATEWAY="http://localhost:9080"
            export APISIX_ADMIN_KEY="${APISIX_ADMIN_KEY:-edd1c9f034335f136f87ad84b625c8f1}"
            export POSTGRES_HOST="localhost"
            export POSTGRES_PORT="5432"
            export REDIS_HOST="localhost"
            export REDIS_PORT="6379"
            export MINIO_HOST="localhost"
            export MINIO_PORT="9000"
            ;;
        staging)
            export CLUSTER_NAME="isa-cloud-staging"
            export NAMESPACE="isa-cloud-staging"
            export KUBE_CONTEXT="arn:aws:eks:us-east-1:ACCOUNT:cluster/isa-cloud-staging"
            export CONSUL_URL="http://consul.isa-cloud-staging.svc:8500"
            export APISIX_ADMIN="http://apisix-admin.isa-cloud-staging.svc:9180"
            export APISIX_GATEWAY="http://apisix-gateway.isa-cloud-staging.svc:9080"
            export APISIX_ADMIN_KEY="${APISIX_ADMIN_KEY:-edd1c9f034335f136f87ad84b625c8f1}"
            export POSTGRES_HOST="postgresql.isa-cloud-staging.svc"
            export POSTGRES_PORT="5432"
            export REDIS_HOST="redis-master.isa-cloud-staging.svc"
            export REDIS_PORT="6379"
            export MINIO_HOST="minio.isa-cloud-staging.svc"
            export MINIO_PORT="9000"
            ;;
        production)
            export CLUSTER_NAME="isa-cloud-production"
            export NAMESPACE="isa-cloud-production"
            export KUBE_CONTEXT="arn:aws:eks:us-east-1:ACCOUNT:cluster/isa-cloud-production"
            export CONSUL_URL="http://consul.isa-cloud-production.svc:8500"
            export APISIX_ADMIN="http://apisix-admin.isa-cloud-production.svc:9180"
            export APISIX_GATEWAY="http://apisix-gateway.isa-cloud-production.svc:9080"
            export APISIX_ADMIN_KEY="${APISIX_ADMIN_KEY}"  # Must be set externally for production
            export POSTGRES_HOST="postgresql-ha-pgpool.isa-cloud-production.svc"
            export POSTGRES_PORT="5432"
            export REDIS_HOST="redis-cluster.isa-cloud-production.svc"
            export REDIS_PORT="6379"
            export MINIO_HOST="minio.isa-cloud-production.svc"
            export MINIO_PORT="9000"
            ;;
        *)
            echo "ERROR: Unknown environment: $env_name" >&2
            echo "Valid environments: local, staging, production" >&2
            return 1
            ;;
    esac

    return 0
}

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

# Print current environment configuration
print_environment() {
    echo "=============================================="
    echo "Current Environment: $ISA_ENV"
    echo "=============================================="
    echo "Cluster:        $CLUSTER_NAME"
    echo "Namespace:      $NAMESPACE"
    echo "Kube Context:   $KUBE_CONTEXT"
    echo "Consul URL:     $CONSUL_URL"
    echo "APISIX Admin:   $APISIX_ADMIN"
    echo "APISIX Gateway: $APISIX_GATEWAY"
    echo "PostgreSQL:     $POSTGRES_HOST:$POSTGRES_PORT"
    echo "Redis:          $REDIS_HOST:$REDIS_PORT"
    echo "MinIO:          $MINIO_HOST:$MINIO_PORT"
    echo "=============================================="
}

# Verify kubectl connection
verify_connection() {
    if ! kubectl cluster-info &>/dev/null; then
        echo "ERROR: Cannot connect to Kubernetes cluster" >&2
        return 1
    fi

    if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
        echo "ERROR: Namespace '$NAMESPACE' does not exist" >&2
        return 1
    fi

    return 0
}

# Get pod name by label selectors (tries multiple common patterns)
get_pod() {
    local component="$1"
    local pod=""

    # Common label patterns for each component
    case "$component" in
        postgresql|postgres)
            pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            [ -z "$pod" ] && pod=$(kubectl get pods -n "$NAMESPACE" -l app=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            ;;
        redis)
            pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            [ -z "$pod" ] && pod=$(kubectl get pods -n "$NAMESPACE" -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            ;;
        qdrant)
            pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=qdrant -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            [ -z "$pod" ] && pod=$(kubectl get pods -n "$NAMESPACE" -l app=qdrant -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            ;;
        neo4j)
            pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=neo4j -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            [ -z "$pod" ] && pod=$(kubectl get pods -n "$NAMESPACE" -l app=neo4j -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            ;;
        minio)
            pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=minio -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            [ -z "$pod" ] && pod=$(kubectl get pods -n "$NAMESPACE" -l app=minio -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            ;;
        consul)
            pod=$(kubectl get pods -n "$NAMESPACE" -l app=consul,component=server -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            [ -z "$pod" ] && pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=consul -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            ;;
        nats)
            pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=nats -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            [ -z "$pod" ] && pod=$(kubectl get pods -n "$NAMESPACE" -l app=nats -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            ;;
        apisix)
            pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=apisix -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            [ -z "$pod" ] && pod=$(kubectl get pods -n "$NAMESPACE" -l app=apisix -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            ;;
        etcd)
            pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=etcd -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            [ -z "$pod" ] && pod=$(kubectl get pods -n "$NAMESPACE" -l app=etcd -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
            ;;
    esac

    echo "$pod"
}

# Get service name by component
get_service() {
    local component="$1"
    local svc=""

    svc=$(kubectl get svc -n "$NAMESPACE" -l "app.kubernetes.io/name=$component" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    [ -z "$svc" ] && svc=$(kubectl get svc -n "$NAMESPACE" -l "app=$component" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    [ -z "$svc" ] && svc="$component"  # Fallback to component name

    echo "$svc"
}

# -----------------------------------------------------------------------------
# Auto-load if sourced with environment argument
# -----------------------------------------------------------------------------

# If this script is sourced with an explicit environment argument, load it
# Only load if argument is a known environment (not flags like --dry-run)
if [[ "$1" =~ ^(local|staging|production)$ ]]; then
    load_environment "$1"
fi
