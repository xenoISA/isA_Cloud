#!/bin/bash
# =============================================================================
# ISA Platform - Production Deployment Script
# =============================================================================
# IMPORTANT: This script requires manual approval for each step.
# Production deployments should go through CI/CD pipeline (ArgoCD).
#
# Usage:
#   ./deploy.sh secrets            # Deploy Vault + ESO (run first!)
#   ./deploy.sh infrastructure    # Deploy HA infrastructure
#   ./deploy.sh services          # Deploy application services (ArgoCD)
#   ./deploy.sh mlplatform        # Deploy ML platform (Ray, MLflow, JupyterHub)
#   ./deploy.sh gpu               # Deploy GPU inference (NVIDIA Operator, vLLM, Triton, Ray GPU)
#   ./deploy.sh data              # Deploy Big Data platform (Ray Data, Dagster, streaming ETL)
#   ./deploy.sh runtime           # Deploy Agent Runtime (KVM, Ignite, cloud_os, pool_manager)
#   ./deploy.sh etcd              # Deploy etcd cluster only
#   ./deploy.sh all               # Deploy everything (with confirmations)
#   ./deploy.sh status            # Check deployment status
#   ./deploy.sh rollback <name>   # Rollback a Helm release
#
# Provider & Sizing Flags (optional — apply to any command):
#   --provider <name>    Select storage profile (infotrend, aws, generic)
#   --nodes <count>      Select resource profile (3, 5, etc.)
#   --skip-preflight     Skip pre-flight verification checks
# =============================================================================

set -e

# Configuration
NAMESPACE="isa-cloud-production"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VALUES_DIR="${SCRIPT_DIR}/../values"
MANIFESTS_DIR="${SCRIPT_DIR}/../manifests"
PROFILES_DIR="${SCRIPT_DIR}/../profiles"
TIMEOUT="10m"

# Provider & sizing (set via flags, see parse_global_flags)
PROVIDER=""
NODE_COUNT=""
SKIP_PREFLIGHT=false

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

# Parse global flags (--provider, --nodes, --skip-preflight)
# Called from main() before dispatching to subcommands
parse_global_flags() {
    local args=()
    while [[ $# -gt 0 ]]; do
        case $1 in
            --provider)       PROVIDER="$2"; shift 2 ;;
            --nodes)          NODE_COUNT="$2"; shift 2 ;;
            --skip-preflight) SKIP_PREFLIGHT=true; shift ;;
            *)                args+=("$1"); shift ;;
        esac
    done
    # Return remaining args
    REMAINING_ARGS=("${args[@]}")
}

# Build Helm --values flags for a component
# Usage: helm upgrade --install ... $(helm_values postgresql-ha)
# Returns: -f values/postgresql-ha.yaml [-f profiles/3-node/postgresql-ha.yaml]
helm_values() {
    local component="$1"
    local flags="-f ${VALUES_DIR}/${component}.yaml"

    # Apply node-count profile override if it exists
    if [[ -n "$NODE_COUNT" ]]; then
        local node_override="${PROFILES_DIR}/${NODE_COUNT}-node/${component}.yaml"
        if [[ -f "$node_override" ]]; then
            flags="${flags} -f ${node_override}"
            log_info "Applying ${NODE_COUNT}-node override for ${component}"
        fi
    fi

    echo "$flags"
}

# Resolve storage class from provider profile
# Usage: resolve_storage block => "infotrend-block" (or "" for default)
resolve_storage() {
    local tier="$1"
    if [[ -n "$PROVIDER" ]]; then
        local profile_file="${PROFILES_DIR}/${PROVIDER}.yaml"
        if [[ -f "$profile_file" ]]; then
            local sc
            sc=$(grep "^  ${tier}:" "$profile_file" | sed 's/^.*: *//' | tr -d '"' | tr -d "'")
            echo "$sc"
            return
        fi
    fi
    echo ""
}

# Run pre-flight checks
run_preflight() {
    if [[ "$SKIP_PREFLIGHT" == true ]]; then
        log_warn "Pre-flight checks skipped (--skip-preflight)"
        return 0
    fi

    if [[ -x "${SCRIPT_DIR}/preflight.sh" ]]; then
        local pf_args=""
        [[ -n "$PROVIDER" ]] && pf_args="${pf_args} --provider ${PROVIDER}"
        [[ -n "$NODE_COUNT" ]] && pf_args="${pf_args} --nodes ${NODE_COUNT}"

        log_step "Running pre-flight checks..."
        "${SCRIPT_DIR}/preflight.sh" ${pf_args} || {
            log_error "Pre-flight checks failed. Fix errors above or use --skip-preflight to bypass."
            exit 1
        }
    fi
}

# Run post-deploy health check
run_healthcheck() {
    if [[ -x "${SCRIPT_DIR}/health-check.sh" ]]; then
        log_step "Running post-deploy health check..."
        "${SCRIPT_DIR}/health-check.sh" --quick || {
            log_warn "Some health checks failed. Review output above."
        }
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

    # Check secrets exist (created by Vault + ESO, or manually)
    local required_secrets=("postgresql-secret" "redis-secret" "neo4j-secret" "minio-secret")
    for secret in "${required_secrets[@]}"; do
        if ! kubectl get secret ${secret} -n ${NAMESPACE} &>/dev/null; then
            log_error "Required secret '${secret}' not found in ${NAMESPACE}"
            log_error "Ensure Vault + ESO are deployed and secrets are seeded."
            log_error "Run: ./vault-init.sh (first time) or ./vault-init.sh status (check)"
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
        "external-secrets https://charts.external-secrets.io"
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

# Deploy Vault + External Secrets Operator
deploy_secrets() {
    log_info "Deploying secret management (Vault + ESO)..."
    confirm "This will deploy HashiCorp Vault and External Secrets Operator. Continue?"

    setup_helm_repos

    # 1. Deploy Vault HA
    log_step "Deploying HashiCorp Vault (HA with Consul backend)..."
    helm upgrade --install vault hashicorp/vault \
        -n ${NAMESPACE} \
        $(helm_values vault) \
        --wait --timeout ${TIMEOUT}

    # 2. Deploy External Secrets Operator
    log_step "Deploying External Secrets Operator..."
    helm upgrade --install external-secrets external-secrets/external-secrets \
        -n external-secrets --create-namespace \
        $(helm_values external-secrets) \
        --wait --timeout ${TIMEOUT}

    # 3. Apply ClusterSecretStore and ExternalSecret CRs
    log_step "Applying ClusterSecretStore and ExternalSecret manifests..."
    kubectl apply -f "${MANIFESTS_DIR}/cluster-secret-store.yaml"
    kubectl apply -f "${MANIFESTS_DIR}/external-secrets.yaml"

    log_info "Secret management deployed!"
    log_warn "If this is the first deployment, run: ./vault-init.sh"
    log_warn "This will initialize Vault, unseal it, and seed secrets."
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
        $(helm_values postgresql-ha) \
        --wait --timeout ${TIMEOUT}

    # 3. Redis Cluster
    log_step "Deploying Redis cluster..."
    helm upgrade --install redis bitnami/redis-cluster \
        -n ${NAMESPACE} \
        $(helm_values redis-cluster) \
        --wait --timeout ${TIMEOUT}

    # 4. Neo4j Cluster
    log_step "Deploying Neo4j cluster..."
    helm upgrade --install neo4j neo4j/neo4j \
        -n ${NAMESPACE} \
        $(helm_values neo4j-cluster) \
        --wait --timeout ${TIMEOUT}

    # 5. MinIO Distributed
    log_step "Deploying MinIO distributed..."
    helm upgrade --install minio minio/minio \
        -n ${NAMESPACE} \
        $(helm_values minio-distributed) \
        --wait --timeout ${TIMEOUT}

    # 6. NATS JetStream
    log_step "Deploying NATS JetStream cluster..."
    helm upgrade --install nats nats/nats \
        -n ${NAMESPACE} \
        $(helm_values nats-jetstream) \
        --wait --timeout ${TIMEOUT}

    # 7. Qdrant Distributed
    log_step "Deploying Qdrant distributed..."
    helm upgrade --install qdrant qdrant/qdrant \
        -n ${NAMESPACE} \
        $(helm_values qdrant-distributed) \
        --wait --timeout ${TIMEOUT}

    # 8. EMQX Cluster
    log_step "Deploying EMQX MQTT cluster..."
    helm upgrade --install emqx emqx/emqx \
        -n ${NAMESPACE} \
        $(helm_values emqx-cluster) \
        --wait --timeout ${TIMEOUT}

    # 9. Consul Cluster
    log_step "Deploying Consul cluster..."
    helm upgrade --install consul hashicorp/consul \
        -n ${NAMESPACE} \
        $(helm_values consul) \
        --wait --timeout ${TIMEOUT}

    # 10. APISIX
    log_step "Deploying APISIX..."
    helm upgrade --install apisix apisix/apisix \
        -n ${NAMESPACE} \
        $(helm_values apisix) \
        --wait --timeout ${TIMEOUT}

    # 11. Apply Consul-APISIX sync CronJob
    log_step "Applying Consul-APISIX sync CronJob..."
    if [ -f "${MANIFESTS_DIR}/consul-apisix-sync.yaml" ]; then
        kubectl apply -f "${MANIFESTS_DIR}/consul-apisix-sync.yaml"
    fi

    log_info "Infrastructure deployment complete!"
    run_healthcheck
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
        $(helm_values kuberay-operator) \
        --wait --timeout ${TIMEOUT}

    # Wait for operator to be ready
    log_info "Waiting for KubeRay operator..."
    kubectl wait --for=condition=available deployment/kuberay-operator -n ${NAMESPACE} --timeout=120s || true

    # 2. Ray Cluster
    log_step "Deploying Ray Cluster..."
    helm upgrade --install ray-cluster kuberay/ray-cluster \
        -n ${NAMESPACE} \
        $(helm_values ray-cluster) \
        --wait --timeout ${TIMEOUT}

    # 3. MLflow
    log_step "Deploying MLflow..."
    if [ -f "${VALUES_DIR}/mlflow.yaml" ]; then
        helm upgrade --install mlflow bitnami/mlflow \
            -n ${NAMESPACE} \
            $(helm_values mlflow) \
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
            $(helm_values jupyterhub) \
            --wait --timeout ${TIMEOUT}
    fi

    log_info "ML Platform deployment complete!"
}

# Deploy GPU inference infrastructure
deploy_gpu() {
    log_info "Deploying GPU inference infrastructure..."
    confirm "This will deploy NVIDIA GPU Operator and inference engines. Continue?"

    setup_helm_repos

    # Add NVIDIA Helm repo
    if ! helm repo list | grep -q "^nvidia"; then
        helm repo add nvidia https://helm.ngc.nvidia.com/nvidia
    fi
    helm repo update

    # 1. NVIDIA GPU Operator
    log_step "Deploying NVIDIA GPU Operator..."
    helm upgrade --install gpu-operator nvidia/gpu-operator \
        -n gpu-operator --create-namespace \
        $(helm_values nvidia-gpu-operator) \
        --wait --timeout ${TIMEOUT}

    # Wait for GPU device plugin
    log_info "Waiting for GPU device plugin to be ready..."
    kubectl wait --for=condition=ready pod -l app=nvidia-device-plugin-daemonset -n gpu-operator --timeout=300s || {
        log_warn "GPU device plugin not ready yet — may need driver installation"
    }

    # 2. Apply GPU node labels
    log_step "Applying GPU node configuration..."
    kubectl apply -f "${MANIFESTS_DIR}/gpu/gpu-node-labels.yaml"

    # 3. Create model cache PVCs
    log_step "Creating model cache PVCs..."
    kubectl apply -f "${MANIFESTS_DIR}/gpu/model-cache-pvc.yaml"

    # 4. Pre-pull models
    log_step "Running model pre-pull job..."
    kubectl apply -f "${MANIFESTS_DIR}/gpu/model-prepull-job.yaml"
    log_info "Model download started in background (check: kubectl logs job/model-prepull-vllm -n ${NAMESPACE})"

    # 5. Deploy vLLM
    log_step "Deploying vLLM inference engine..."
    helm upgrade --install vllm oci://ghcr.io/vllm-project/helm-charts/vllm \
        -n ${NAMESPACE} \
        $(helm_values vllm) \
        --wait --timeout 15m || {
        # Fallback: deploy as raw manifest if no Helm chart
        log_warn "vLLM Helm chart not available, deploying via values as reference..."
    }

    # 6. Deploy Triton
    log_step "Deploying Triton Inference Server..."
    helm upgrade --install triton nvidia/triton-inference-server \
        -n ${NAMESPACE} \
        $(helm_values triton) \
        --wait --timeout ${TIMEOUT} 2>/dev/null || {
        log_warn "Triton Helm chart not available, skipping..."
    }

    # 7. Deploy Ray GPU cluster
    log_step "Deploying Ray GPU cluster..."
    helm upgrade --install ray-gpu kuberay/ray-cluster \
        -n ${NAMESPACE} \
        $(helm_values ray-gpu-cluster) \
        --wait --timeout ${TIMEOUT}

    # 8. Apply monitoring
    log_step "Applying GPU monitoring dashboards and alerts..."
    kubectl apply -f "${MANIFESTS_DIR}/gpu/gpu-grafana-dashboard.yaml"

    log_info "GPU infrastructure deployment complete!"
    run_healthcheck
}

# Deploy Big Data platform
deploy_data() {
    log_info "Deploying Big Data platform..."
    confirm "This will deploy Ray Data, Dagster, streaming ETL, and isA_Data. Continue?"

    setup_helm_repos

    # Add Dagster Helm repo
    if ! helm repo list | grep -q "^dagster"; then
        helm repo add dagster https://dagster-io.github.io/helm
    fi
    helm repo update

    # 1. Ray Data cluster (CPU workers)
    log_step "Deploying Ray Data cluster..."
    helm upgrade --install ray-data kuberay/ray-cluster \
        -n ${NAMESPACE} \
        $(helm_values ray-data-cluster) \
        --wait --timeout ${TIMEOUT}

    # 2. Dagster orchestrator
    log_step "Deploying Dagster orchestrator..."
    helm upgrade --install dagster dagster/dagster \
        -n ${NAMESPACE} \
        $(helm_values dagster) \
        --wait --timeout ${TIMEOUT}

    # 3. Streaming ETL pipeline
    log_step "Deploying streaming ETL pipeline..."
    kubectl apply -f "${MANIFESTS_DIR}/data/streaming-etl-deployment.yaml"

    # 4. isA_Data service
    log_step "Deploying isA_Data service..."
    helm upgrade --install isa-data isa-service/isa-service \
        -n ${NAMESPACE} \
        $(helm_values isa-data) \
        --wait --timeout ${TIMEOUT} 2>/dev/null || {
        log_warn "isa-service chart not available, skipping Helm deploy..."
    }

    # 5. Apply monitoring
    log_step "Applying data platform monitoring..."
    kubectl apply -f "${MANIFESTS_DIR}/data/data-grafana-dashboard.yaml"

    log_info "Big Data platform deployment complete!"
    run_healthcheck
}

# Deploy Agent Runtime platform
deploy_runtime() {
    log_info "Deploying Agent Runtime platform..."
    confirm "This will deploy KVM/Ignite, container-service, cloud_os, and pool_manager. Continue?"

    setup_helm_repos

    # 1. KVM device plugin DaemonSet
    log_step "Deploying KVM device plugin..."
    kubectl apply -f "${MANIFESTS_DIR}/runtime/kvm-daemonset.yaml"
    log_info "Waiting for KVM device plugin..."
    kubectl wait --for=condition=ready pod -l app=kvm-device-plugin -n ${NAMESPACE} --timeout=120s || {
        log_warn "KVM device plugin not ready — check /dev/kvm on nodes"
    }

    # 2. Ignite manager DaemonSet
    log_step "Deploying Ignite manager..."
    kubectl apply -f "${MANIFESTS_DIR}/runtime/ignite-daemonset.yaml"

    # 3. Container service (gRPC backend)
    log_step "Deploying container-service gRPC backend..."
    helm upgrade --install container-service isa-service/isa-service \
        -n ${NAMESPACE} \
        $(helm_values container-service) \
        --wait --timeout ${TIMEOUT} 2>/dev/null || {
        log_warn "isa-service chart not available, skipping Helm deploy..."
    }

    # 4. Cloud OS
    log_step "Deploying cloud_os..."
    helm upgrade --install cloud-os isa-service/isa-service \
        -n ${NAMESPACE} \
        $(helm_values cloud-os) \
        --wait --timeout ${TIMEOUT} 2>/dev/null || {
        log_warn "isa-service chart not available, skipping Helm deploy..."
    }

    # 5. Pool Manager
    log_step "Deploying pool_manager..."
    helm upgrade --install pool-manager isa-service/isa-service \
        -n ${NAMESPACE} \
        $(helm_values pool-manager) \
        --wait --timeout ${TIMEOUT} 2>/dev/null || {
        log_warn "isa-service chart not available, skipping Helm deploy..."
    }

    # 6. VM image build job
    log_step "Deploying VM image pipeline..."
    kubectl apply -f "${MANIFESTS_DIR}/runtime/vm-image-pipeline.yaml"

    # 7. Apply monitoring
    log_step "Applying runtime monitoring..."
    kubectl apply -f "${MANIFESTS_DIR}/runtime/runtime-grafana-dashboard.yaml"

    log_info "Agent Runtime deployment complete!"
    run_healthcheck
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

    deploy_secrets
    check_prerequisites
    deploy_infrastructure
    deploy_mlplatform
    deploy_gpu
    deploy_data
    deploy_runtime
    deploy_services

    log_info "Full production deployment complete!"
    check_status
}

# Usage
usage() {
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  secrets           Deploy Vault + External Secrets Operator"
    echo "  infrastructure    Deploy HA infrastructure (etcd, PostgreSQL, Redis, etc.)"
    echo "  services          Deploy application services via ArgoCD"
    echo "  mlplatform        Deploy ML platform (Ray, MLflow, JupyterHub)"
    echo "  etcd              Deploy etcd HA cluster only"
    echo "  gpu               Deploy GPU inference (NVIDIA Operator, vLLM, Triton, Ray GPU)"
    echo "  data              Deploy Big Data platform (Ray Data, Dagster, streaming ETL)"
    echo "  runtime           Deploy Agent Runtime (KVM, Ignite, cloud_os, pool_manager)"
    echo "  all               Deploy everything (infrastructure + ML + services)"
    echo "  status            Check deployment status"
    echo "  rollback <name>   Rollback a Helm release"
    echo ""
    echo "Flags:"
    echo "  --provider <name>    Storage profile (infotrend, aws, generic)"
    echo "  --nodes <count>      Resource profile (3, 5, etc.)"
    echo "  --skip-preflight     Skip pre-flight verification"
    echo ""
    echo "Examples:"
    echo "  $0 status                                     # Check current status"
    echo "  $0 infrastructure                             # Deploy (default profile)"
    echo "  $0 infrastructure --provider infotrend --nodes 3  # Infotrend 3-node"
    echo "  $0 all --provider aws --nodes 5               # AWS 5-node cluster"
    echo "  $0 rollback postgresql                        # Rollback PostgreSQL"
    echo ""
    echo "NOTE: Production deployments require explicit confirmation."
    echo "      For routine deployments, use ArgoCD GitOps workflow."
}

# Main
main() {
    # Parse global flags first (--provider, --nodes, --skip-preflight)
    parse_global_flags "$@"
    set -- "${REMAINING_ARGS[@]}"

    local command="${1:-}"
    shift || true

    # Log provider/node config if set
    [[ -n "$PROVIDER" ]] && log_info "Provider profile: ${PROVIDER}"
    [[ -n "$NODE_COUNT" ]] && log_info "Node count profile: ${NODE_COUNT}-node"

    case "${command}" in
        secrets)
            deploy_secrets
            ;;
        infrastructure)
            run_preflight
            check_prerequisites
            deploy_infrastructure
            ;;
        services)
            deploy_services
            ;;
        mlplatform)
            run_preflight
            check_prerequisites
            deploy_mlplatform
            ;;
        etcd)
            check_prerequisites
            setup_helm_repos
            deploy_etcd
            ;;
        gpu)
            run_preflight
            check_prerequisites
            deploy_gpu
            ;;
        data)
            run_preflight
            check_prerequisites
            deploy_data
            ;;
        runtime)
            run_preflight
            check_prerequisites
            deploy_runtime
            ;;
        all)
            run_preflight
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
