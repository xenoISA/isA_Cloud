#!/bin/bash
# =============================================================================
# ISA Platform - Deployment Validation Script
# =============================================================================
# Validates all deployment configurations before actual deployment.
#
# Usage:
#   ./validate.sh              # Run all validations
#   ./validate.sh helm         # Validate Helm charts only
#   ./validate.sh argocd       # Validate ArgoCD configs only
#   ./validate.sh kubernetes   # Validate K8s values only
#   ./validate.sh scripts      # Validate scripts only
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENTS_DIR="$(dirname "$SCRIPT_DIR")"
ISA_ROOT="$(dirname "$(dirname "$DEPLOYMENTS_DIR")")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

log_info() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[⚠]${NC} $1"; ((WARNINGS++)); }
log_error() { echo -e "${RED}[✗]${NC} $1"; ((ERRORS++)); }
log_section() { echo -e "\n${BLUE}=== $1 ===${NC}"; }

# =============================================================================
# Check Prerequisites
# =============================================================================
check_prerequisites() {
    log_section "Checking Prerequisites"

    # Check helm
    if command -v helm &>/dev/null; then
        log_info "Helm installed: $(helm version --short)"
    else
        log_error "Helm not installed"
    fi

    # Check kubectl
    if command -v kubectl &>/dev/null; then
        log_info "kubectl installed: $(kubectl version --client --short 2>/dev/null || kubectl version --client -o yaml | grep gitVersion | head -1)"
    else
        log_warn "kubectl not installed (needed for cluster operations)"
    fi

    # Check kind
    if command -v kind &>/dev/null; then
        log_info "Kind installed: $(kind version)"
    else
        log_warn "Kind not installed (needed for local cluster)"
    fi

    # Check argocd CLI
    if command -v argocd &>/dev/null; then
        log_info "ArgoCD CLI installed"
    else
        log_warn "ArgoCD CLI not installed (optional)"
    fi
}

# =============================================================================
# Validate Helm Charts
# =============================================================================
validate_helm_charts() {
    log_section "Validating Helm Charts"

    local chart_dir="${DEPLOYMENTS_DIR}/charts/isa-service"

    # Check chart exists
    if [[ ! -f "${chart_dir}/Chart.yaml" ]]; then
        log_error "Chart.yaml not found in ${chart_dir}"
        return
    fi

    # Lint chart
    if helm lint "${chart_dir}" &>/dev/null; then
        log_info "Helm lint passed: charts/isa-service"
    else
        log_error "Helm lint failed: charts/isa-service"
        helm lint "${chart_dir}" 2>&1 | head -20
    fi

    # Template dry-run
    if helm template test "${chart_dir}" &>/dev/null; then
        log_info "Helm template passed: charts/isa-service"
    else
        log_error "Helm template failed: charts/isa-service"
    fi
}

# =============================================================================
# Validate Kubernetes Values Files
# =============================================================================
validate_kubernetes_values() {
    log_section "Validating Kubernetes Values Files"

    local environments=("local" "staging" "production")

    for env in "${environments[@]}"; do
        local values_dir="${DEPLOYMENTS_DIR}/kubernetes/${env}/values"

        if [[ ! -d "$values_dir" ]]; then
            log_warn "Values directory not found: kubernetes/${env}/values"
            continue
        fi

        local count=$(ls -1 "${values_dir}"/*.yaml 2>/dev/null | wc -l)
        if [[ $count -gt 0 ]]; then
            log_info "Found ${count} values files in kubernetes/${env}/values"

            # Validate YAML syntax
            for file in "${values_dir}"/*.yaml; do
                if python3 -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null; then
                    :
                else
                    log_error "Invalid YAML: ${file}"
                fi
            done
        else
            log_warn "No values files in kubernetes/${env}/values"
        fi
    done
}

# =============================================================================
# Validate ArgoCD Configurations
# =============================================================================
validate_argocd() {
    log_section "Validating ArgoCD Configurations"

    # Check applications
    local apps_dir="${DEPLOYMENTS_DIR}/argocd/applications"
    if [[ -d "$apps_dir" ]]; then
        for file in "${apps_dir}"/*.yaml; do
            if [[ -f "$file" ]]; then
                # Check YAML syntax
                if python3 -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null; then
                    log_info "Valid YAML: $(basename $file)"
                else
                    log_error "Invalid YAML: $(basename $file)"
                fi

                # Check for required fields
                if grep -q "kind: Application" "$file"; then
                    :
                else
                    log_warn "Missing 'kind: Application' in $(basename $file)"
                fi
            fi
        done
    fi

    # Check app-of-apps structure
    local envs=("dev" "staging" "production")
    for env in "${envs[@]}"; do
        local env_apps="${DEPLOYMENTS_DIR}/argocd/apps/${env}"
        if [[ -d "$env_apps" ]]; then
            local count=$(ls -1 "${env_apps}"/*.yaml 2>/dev/null | wc -l)
            log_info "ArgoCD apps/${env}: ${count} files"

            # Validate each file
            for file in "${env_apps}"/*.yaml; do
                if [[ -f "$file" ]]; then
                    if python3 -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null; then
                        :
                    else
                        log_error "Invalid YAML: argocd/apps/${env}/$(basename $file)"
                    fi
                fi
            done
        else
            log_error "Missing ArgoCD apps directory: apps/${env}"
        fi
    done
}

# =============================================================================
# Validate Scripts
# =============================================================================
validate_scripts() {
    log_section "Validating Scripts"

    # Check deploy.sh
    local deploy_script="${DEPLOYMENTS_DIR}/scripts/deploy.sh"
    if [[ -f "$deploy_script" ]]; then
        if bash -n "$deploy_script" 2>/dev/null; then
            log_info "Syntax OK: scripts/deploy.sh"
        else
            log_error "Syntax error: scripts/deploy.sh"
        fi

        if [[ -x "$deploy_script" ]]; then
            log_info "Executable: scripts/deploy.sh"
        else
            log_warn "Not executable: scripts/deploy.sh (run: chmod +x)"
        fi
    else
        log_error "Missing: scripts/deploy.sh"
    fi

    # Check build-and-push.sh
    local build_script="${DEPLOYMENTS_DIR}/scripts/build-and-push.sh"
    if [[ -f "$build_script" ]]; then
        if bash -n "$build_script" 2>/dev/null; then
            log_info "Syntax OK: scripts/build-and-push.sh"
        else
            log_error "Syntax error: scripts/build-and-push.sh"
        fi
    else
        log_warn "Missing: scripts/build-and-push.sh"
    fi

    # Check local scripts
    local local_scripts="${DEPLOYMENTS_DIR}/kubernetes/local/scripts"
    if [[ -d "$local_scripts" ]]; then
        for script in "${local_scripts}"/*.sh; do
            if [[ -f "$script" ]]; then
                if bash -n "$script" 2>/dev/null; then
                    log_info "Syntax OK: kubernetes/local/scripts/$(basename $script)"
                else
                    log_error "Syntax error: kubernetes/local/scripts/$(basename $script)"
                fi
            fi
        done
    fi

    # Check production scripts
    local prod_scripts="${DEPLOYMENTS_DIR}/kubernetes/production/scripts"
    if [[ -d "$prod_scripts" ]]; then
        for script in "${prod_scripts}"/*.sh; do
            if [[ -f "$script" ]]; then
                if bash -n "$script" 2>/dev/null; then
                    log_info "Syntax OK: kubernetes/production/scripts/$(basename $script)"
                else
                    log_error "Syntax error: kubernetes/production/scripts/$(basename $script)"
                fi
            fi
        done
    fi
}

# =============================================================================
# Validate Service Helm Values
# =============================================================================
validate_service_values() {
    log_section "Validating Service Helm Values"

    local services=(
        "isA_MCP"
        "isA_Model"
        "isA_Agent"
        "isA_Data"
        "isA_OS/os_services/web_services"
        "isA_OS/os_services/cloud_os"
        "isA_OS/os_services/python_repl"
        "isA_OS/os_services/pool_manager"
    )

    for service in "${services[@]}"; do
        local helm_dir="${ISA_ROOT}/${service}/deployment/helm"

        if [[ -d "$helm_dir" ]]; then
            local files=$(ls -1 "${helm_dir}"/*.yaml 2>/dev/null | wc -l)
            if [[ $files -gt 0 ]]; then
                log_info "Found ${files} Helm values in ${service}/deployment/helm"

                # Validate each file
                for file in "${helm_dir}"/*.yaml; do
                    if python3 -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null; then
                        :
                    else
                        log_error "Invalid YAML: ${service}/deployment/helm/$(basename $file)"
                    fi
                done
            else
                log_warn "No Helm values in ${service}/deployment/helm"
            fi
        else
            log_warn "Missing Helm dir: ${service}/deployment/helm"
        fi
    done
}

# =============================================================================
# Validate Secrets Templates
# =============================================================================
validate_secrets() {
    log_section "Validating Secrets Templates"

    local envs=("staging" "production")

    for env in "${envs[@]}"; do
        local secrets_dir="${DEPLOYMENTS_DIR}/kubernetes/${env}/secrets"

        if [[ -d "$secrets_dir" ]]; then
            for file in "${secrets_dir}"/*.yaml; do
                if [[ -f "$file" ]]; then
                    # Check YAML syntax
                    if python3 -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null; then
                        log_info "Valid template: kubernetes/${env}/secrets/$(basename $file)"
                    else
                        log_error "Invalid YAML: kubernetes/${env}/secrets/$(basename $file)"
                    fi

                    # Check for placeholder values (shouldn't be real secrets)
                    if grep -q "REPLACE" "$file"; then
                        log_info "Contains placeholders (good): $(basename $file)"
                    else
                        log_warn "No placeholders found in $(basename $file) - ensure no real secrets!"
                    fi
                fi
            done
        else
            log_warn "Missing secrets directory: kubernetes/${env}/secrets"
        fi
    done
}

# =============================================================================
# Check Directory Structure
# =============================================================================
validate_structure() {
    log_section "Validating Directory Structure"

    local required_dirs=(
        "argocd/applications"
        "argocd/apps/dev"
        "argocd/apps/staging"
        "argocd/apps/production"
        "argocd/bootstrap"
        "charts/isa-service"
        "charts/isa-service/templates"
        "kubernetes/local/values"
        "kubernetes/local/scripts"
        "kubernetes/staging/values"
        "kubernetes/staging/secrets"
        "kubernetes/production/values"
        "kubernetes/production/scripts"
        "kubernetes/production/secrets"
        "scripts"
        "terraform"
    )

    for dir in "${required_dirs[@]}"; do
        if [[ -d "${DEPLOYMENTS_DIR}/${dir}" ]]; then
            log_info "Directory exists: ${dir}"
        else
            log_error "Missing directory: ${dir}"
        fi
    done
}

# =============================================================================
# Summary
# =============================================================================
print_summary() {
    log_section "Validation Summary"

    echo ""
    if [[ $ERRORS -eq 0 && $WARNINGS -eq 0 ]]; then
        echo -e "${GREEN}All validations passed!${NC}"
    else
        echo -e "Errors: ${RED}${ERRORS}${NC}"
        echo -e "Warnings: ${YELLOW}${WARNINGS}${NC}"
    fi

    echo ""
    if [[ $ERRORS -gt 0 ]]; then
        echo -e "${RED}Please fix errors before deploying.${NC}"
        exit 1
    elif [[ $WARNINGS -gt 0 ]]; then
        echo -e "${YELLOW}Warnings found. Review before deploying.${NC}"
        exit 0
    else
        echo -e "${GREEN}Ready to deploy!${NC}"
        exit 0
    fi
}

# =============================================================================
# Main
# =============================================================================
main() {
    local command="${1:-all}"

    echo -e "${BLUE}"
    echo "=============================================="
    echo "  ISA Platform - Deployment Validation"
    echo "=============================================="
    echo -e "${NC}"

    case "${command}" in
        helm)
            check_prerequisites
            validate_helm_charts
            ;;
        argocd)
            validate_argocd
            ;;
        kubernetes|k8s)
            validate_kubernetes_values
            validate_secrets
            ;;
        scripts)
            validate_scripts
            ;;
        services)
            validate_service_values
            ;;
        structure)
            validate_structure
            ;;
        all|"")
            check_prerequisites
            validate_structure
            validate_helm_charts
            validate_kubernetes_values
            validate_argocd
            validate_scripts
            validate_service_values
            validate_secrets
            ;;
        *)
            echo "Usage: $0 [helm|argocd|kubernetes|scripts|services|structure|all]"
            exit 1
            ;;
    esac

    print_summary
}

main "$@"
