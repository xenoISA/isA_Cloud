#!/bin/bash
# =============================================================================
# ISA Platform - Deploy Services with Helm
# =============================================================================
# Deploys services to Kubernetes using Helm charts.
# Compatible with bash 3.2+ (macOS default)
#
# Usage:
#   ./deploy.sh mcp                    # Deploy MCP service
#   ./deploy.sh agent staging          # Deploy to staging namespace
#   ./deploy.sh model production v1.2.3 # Deploy specific version to production
#   ./deploy.sh user auth              # Deploy specific user microservice
#   ./deploy.sh user all               # Deploy all user microservices
#   ./deploy.sh all                    # Deploy all core services
#   ./deploy.sh list                   # List deployed services
#
# Prerequisites:
#   - kubectl configured for target cluster
#   - Helm 3 installed
#   - Images pushed to Harbor
# =============================================================================

set -e

# Configuration
ISA_ROOT="${ISA_ROOT:-$HOME/Documents/Fun/isA}"
CHARTS_DIR="${ISA_ROOT}/isA_Cloud/deployments/charts"
DEFAULT_NAMESPACE="isa-cloud-staging"
HARBOR_REGISTRY="harbor.local:30443"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# =============================================================================
# Service Path Lookup (bash 3.2 compatible)
# =============================================================================
get_user_service_port() {
    local service="$1"
    case "$service" in
        auth) echo "8201" ;;
        account) echo "8202" ;;
        profile) echo "8203" ;;
        preference) echo "8204" ;;
        notification) echo "8205" ;;
        subscription) echo "8206" ;;
        payment) echo "8207" ;;
        billing) echo "8208" ;;
        invoice) echo "8209" ;;
        usage) echo "8210" ;;
        quota) echo "8211" ;;
        rate-limit) echo "8212" ;;
        api-key) echo "8213" ;;
        oauth) echo "8214" ;;
        sso) echo "8215" ;;
        mfa) echo "8216" ;;
        session) echo "8217" ;;
        audit) echo "8218" ;;
        activity) echo "8219" ;;
        analytics) echo "8220" ;;
        report) echo "8221" ;;
        export) echo "8222" ;;
        import) echo "8223" ;;
        webhook) echo "8224" ;;
        integration) echo "8225" ;;
        team) echo "8226" ;;
        organization) echo "8227" ;;
        role) echo "8228" ;;
        permission) echo "8229" ;;
        invitation) echo "8249" ;;
        membership) echo "8250" ;;
        *) echo "" ;;
    esac
}

# All user services list
USER_SERVICES_LIST="auth account profile preference notification subscription payment billing invoice usage quota rate-limit api-key oauth sso mfa session audit activity analytics report export import webhook integration team organization role permission invitation membership"

# =============================================================================
# Generic Deploy Function
# =============================================================================
deploy_service() {
    local service_name="$1"
    local project_path="$2"
    local namespace="${3:-$DEFAULT_NAMESPACE}"
    local version="${4:-latest}"
    local env_suffix=""

    # Determine environment-specific values file
    if [[ "$namespace" == *"production"* ]]; then
        env_suffix="-production"
    elif [[ "$namespace" == *"staging"* ]]; then
        env_suffix="-staging"
    fi

    local values_file="${ISA_ROOT}/${project_path}/deployment/helm/values${env_suffix}.yaml"
    local base_values="${ISA_ROOT}/${project_path}/deployment/helm/values.yaml"

    log_info "Deploying ${service_name}:${version} to ${namespace}..."

    # Build helm command
    local helm_cmd="helm upgrade --install ${service_name}-service"
    helm_cmd="${helm_cmd} ${CHARTS_DIR}/isa-service"
    helm_cmd="${helm_cmd} -f ${base_values}"

    # Add environment-specific values if they exist
    if [[ -f "$values_file" && "$env_suffix" != "" ]]; then
        helm_cmd="${helm_cmd} -f ${values_file}"
    fi

    helm_cmd="${helm_cmd} --set image.tag=${version}"
    helm_cmd="${helm_cmd} --set namespace=${namespace}"
    helm_cmd="${helm_cmd} -n ${namespace}"
    helm_cmd="${helm_cmd} --create-namespace"
    helm_cmd="${helm_cmd} --wait"
    helm_cmd="${helm_cmd} --timeout 5m"

    eval $helm_cmd

    log_info "${service_name} service deployed successfully!"
    log_info "Check status: kubectl get pods -n ${namespace} -l app=${service_name}-service"
}

# =============================================================================
# Core Service Deploy Functions
# =============================================================================
deploy_mcp() {
    deploy_service "mcp" "isA_MCP" "$@"
}

deploy_model() {
    deploy_service "model" "isA_Model" "$@"
}

deploy_agent() {
    deploy_service "agent" "isA_Agent" "$@"
}

deploy_data() {
    deploy_service "data" "isA_Data" "$@"
}

# =============================================================================
# OS Service Deploy Functions
# =============================================================================
deploy_web_services() {
    deploy_service "web-services" "isA_OS/os_services/web_services" "$@"
}

deploy_cloud_os() {
    deploy_service "cloud-os" "isA_OS/os_services/cloud_os" "$@"
}

deploy_python_repl() {
    deploy_service "python-repl" "isA_OS/os_services/python_repl" "$@"
}

deploy_pool_manager() {
    deploy_service "pool-manager" "isA_OS/os_services/pool_manager" "$@"
}

# =============================================================================
# User Microservice Deploy Functions
# =============================================================================
deploy_user_service() {
    local service_name="$1"
    local namespace="${2:-$DEFAULT_NAMESPACE}"
    local version="${3:-latest}"

    local port=$(get_user_service_port "$service_name")
    if [[ -z "$port" ]]; then
        log_error "Unknown user service: ${service_name}"
        log_info "Available services: ${USER_SERVICES_LIST}"
        exit 1
    fi

    deploy_service "user-${service_name}" "isA_user/services/${service_name}_service" "$namespace" "$version"
}

deploy_all_user_services() {
    local namespace="${1:-$DEFAULT_NAMESPACE}"
    local version="${2:-latest}"

    log_info "Deploying all user microservices to ${namespace}..."
    for service_name in $USER_SERVICES_LIST; do
        deploy_user_service "$service_name" "$namespace" "$version"
    done
    log_info "All user microservices deployed!"
}

list_user_services() {
    echo "Available user microservices:"
    for svc in $USER_SERVICES_LIST; do
        local port=$(get_user_service_port "$svc")
        echo "  ${svc} (port ${port})"
    done
}

# =============================================================================
# Deploy All Services
# =============================================================================
deploy_all_core() {
    local namespace="${1:-$DEFAULT_NAMESPACE}"
    local version="${2:-latest}"

    log_info "Deploying all core services to ${namespace}..."
    deploy_mcp "$namespace" "$version"
    deploy_model "$namespace" "$version"
    deploy_agent "$namespace" "$version"
    deploy_data "$namespace" "$version"
    log_info "All core services deployed!"
}

deploy_all_os() {
    local namespace="${1:-$DEFAULT_NAMESPACE}"
    local version="${2:-latest}"

    log_info "Deploying all OS services to ${namespace}..."
    deploy_web_services "$namespace" "$version"
    deploy_cloud_os "$namespace" "$version"
    deploy_python_repl "$namespace" "$version"
    deploy_pool_manager "$namespace" "$version"
    log_info "All OS services deployed!"
}

deploy_all() {
    local namespace="${1:-$DEFAULT_NAMESPACE}"
    local version="${2:-latest}"

    deploy_all_core "$namespace" "$version"
    deploy_all_os "$namespace" "$version"
    log_info "All services deployed!"
}

# =============================================================================
# Utility Functions
# =============================================================================
list_services() {
    local namespace="${1:-$DEFAULT_NAMESPACE}"

    log_info "Helm releases in ${namespace}:"
    helm list -n "${namespace}"

    echo ""
    log_info "Running pods:"
    kubectl get pods -n "${namespace}" -o wide

    echo ""
    log_info "Services:"
    kubectl get svc -n "${namespace}"

    echo ""
    log_info "HPA status:"
    kubectl get hpa -n "${namespace}" 2>/dev/null || echo "No HPA configured"
}

rollback() {
    local service="${1}"
    local namespace="${2:-$DEFAULT_NAMESPACE}"

    if [ -z "${service}" ]; then
        log_error "Service name required"
        exit 1
    fi

    log_info "Rolling back ${service} in ${namespace}..."
    helm rollback "${service}" -n "${namespace}"
    log_info "Rollback complete"
}

uninstall() {
    local service="${1}"
    local namespace="${2:-$DEFAULT_NAMESPACE}"

    if [ -z "${service}" ]; then
        log_error "Service name required"
        exit 1
    fi

    log_warn "Uninstalling ${service} from ${namespace}..."
    helm uninstall "${service}" -n "${namespace}"
    log_info "Service uninstalled"
}

logs() {
    local service="${1}"
    local namespace="${2:-$DEFAULT_NAMESPACE}"

    if [ -z "${service}" ]; then
        log_error "Service name required"
        exit 1
    fi

    kubectl logs -f -l "app=${service}" -n "${namespace}" --all-containers
}

# =============================================================================
# Usage
# =============================================================================
usage() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Core Services:"
    echo "  mcp [namespace] [version]        Deploy MCP service (port 8081)"
    echo "  model [namespace] [version]      Deploy Model service (port 8082)"
    echo "  agent [namespace] [version]      Deploy Agent service (port 8080)"
    echo "  data [namespace] [version]       Deploy Data service (port 8084)"
    echo ""
    echo "OS Services:"
    echo "  web-services [ns] [ver]          Deploy Web Services (port 8083)"
    echo "  cloud-os [ns] [ver]              Deploy Cloud OS (port 8086)"
    echo "  python-repl [ns] [ver]           Deploy Python REPL (port 8085)"
    echo "  pool-manager [ns] [ver]          Deploy Pool Manager (port 8090)"
    echo ""
    echo "User Microservices:"
    echo "  user <service> [ns] [ver]        Deploy specific user microservice"
    echo "  user all [ns] [ver]              Deploy ALL user microservices"
    echo "  user list                        List available user microservices"
    echo ""
    echo "Batch Commands:"
    echo "  all [namespace] [version]        Deploy ALL core + OS services"
    echo "  all-core [ns] [ver]              Deploy all core services"
    echo "  all-os [ns] [ver]                Deploy all OS services"
    echo ""
    echo "Management:"
    echo "  list [namespace]                 List deployed services"
    echo "  rollback <service> [namespace]   Rollback a service"
    echo "  uninstall <service> [namespace]  Uninstall a service"
    echo "  logs <service> [namespace]       Stream service logs"
    echo ""
    echo "Examples:"
    echo "  $0 mcp                           # Deploy MCP to staging"
    echo "  $0 agent isa-cloud-production v1.2.3"
    echo "  $0 user auth                     # Deploy auth user service"
    echo "  $0 user all                      # Deploy all user microservices"
    echo "  $0 all                           # Deploy all core + OS services"
    echo "  $0 list                          # List all services"
    echo "  $0 rollback mcp-service          # Rollback MCP"
}

# =============================================================================
# Main
# =============================================================================
main() {
    local command="${1:-}"
    shift || true

    case "${command}" in
        # Core services
        mcp)
            deploy_mcp "$@"
            ;;
        model)
            deploy_model "$@"
            ;;
        agent)
            deploy_agent "$@"
            ;;
        data)
            deploy_data "$@"
            ;;
        # OS services
        web-services)
            deploy_web_services "$@"
            ;;
        cloud-os)
            deploy_cloud_os "$@"
            ;;
        python-repl)
            deploy_python_repl "$@"
            ;;
        pool-manager)
            deploy_pool_manager "$@"
            ;;
        # User microservices
        user)
            local subcmd="${1:-}"
            shift || true
            case "${subcmd}" in
                all)
                    deploy_all_user_services "$@"
                    ;;
                list)
                    list_user_services
                    ;;
                "")
                    log_error "User service name required"
                    echo "Usage: $0 user <service-name|all|list>"
                    exit 1
                    ;;
                *)
                    deploy_user_service "$subcmd" "$@"
                    ;;
            esac
            ;;
        # Batch commands
        all)
            deploy_all "$@"
            ;;
        all-core)
            deploy_all_core "$@"
            ;;
        all-os)
            deploy_all_os "$@"
            ;;
        # Management
        list)
            list_services "$@"
            ;;
        rollback)
            rollback "$@"
            ;;
        uninstall)
            uninstall "$@"
            ;;
        logs)
            logs "$@"
            ;;
        -h|--help|"")
            usage
            exit 0
            ;;
        *)
            log_error "Unknown command: ${command}"
            usage
            exit 1
            ;;
    esac
}

main "$@"
