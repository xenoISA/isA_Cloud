#!/bin/bash

# =============================================================================
# isA Platform - Service Build Script
# =============================================================================
# This script builds and pushes all service images to ECR
# Usage: ./build-services.sh [service-name] [environment]

set -e

# Configuration
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="812363383864"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
CLOUD_DIR="/Users/xenodennis/Documents/Fun/isA_Cloud"
DEPLOYMENTS_DIR="${CLOUD_DIR}/deployments"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Function to authenticate with ECR
authenticate_ecr() {
    log_info "Authenticating with ECR..."
    aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REGISTRY
    log_success "ECR authentication successful"
}

# Function to build a service
build_service() {
    local service_name=$1
    local service_dir=$2
    local dockerfile_path=$3
    local image_tag="${ECR_REGISTRY}/isa-${service_name}:latest"
    
    log_info "Building ${service_name} service..."
    
    # Create temporary requirements file in build context
    if [[ -f "${DEPLOYMENTS_DIR}/requirements/${service_name}-requirements.txt" ]]; then
        cp "${DEPLOYMENTS_DIR}/requirements/${service_name}-requirements.txt" "${service_dir}/requirements.txt"
        log_info "Copied requirements file to build context"
    else
        log_warning "No requirements file found for ${service_name}"
    fi
    
    # Build the image
    cd "$service_dir"
    docker build -f "$dockerfile_path" -t "$image_tag" .
    
    # Clean up temporary requirements file
    [[ -f "requirements.txt" ]] && rm requirements.txt
    
    log_success "Built ${service_name}: ${image_tag}"
    return 0
}

# Function to push a service image
push_service() {
    local service_name=$1
    local image_tag="${ECR_REGISTRY}/isa-${service_name}:latest"
    
    log_info "Pushing ${service_name} to ECR..."
    docker push "$image_tag"
    log_success "Pushed ${service_name}: ${image_tag}"
}

# Function to build all services
build_all_services() {
    local services=(
        "gateway:/Users/xenodennis/Documents/Fun/isA_Cloud:${DEPLOYMENTS_DIR}/dockerfiles/Dockerfile.gateway"
        "mcp:/Users/xenodennis/Documents/Fun/isA_MCP:${DEPLOYMENTS_DIR}/dockerfiles/services/Dockerfile.mcp"
        "model:/Users/xenodennis/Documents/Fun/isA_Model:${DEPLOYMENTS_DIR}/dockerfiles/services/Dockerfile.model"
        "agent:/Users/xenodennis/Documents/Fun/isA_Agent:${DEPLOYMENTS_DIR}/dockerfiles/services/Dockerfile.agent"
        "user:/Users/xenodennis/Documents/Fun/isA_user:${DEPLOYMENTS_DIR}/dockerfiles/services/Dockerfile.user"
    )
    
    authenticate_ecr
    
    for service_info in "${services[@]}"; do
        IFS=':' read -r service_name service_dir dockerfile_path <<< "$service_info"
        
        if [[ ! -d "$service_dir" ]]; then
            log_error "Service directory not found: $service_dir"
            continue
        fi
        
        if [[ ! -f "$dockerfile_path" ]]; then
            log_error "Dockerfile not found: $dockerfile_path"
            continue
        fi
        
        # Build service
        if build_service "$service_name" "$service_dir" "$dockerfile_path"; then
            # Push service
            push_service "$service_name"
        else
            log_error "Failed to build ${service_name}"
        fi
        
        echo ""
    done
}

# Function to build infrastructure services
build_infrastructure() {
    local infra_services=(
        "consul"
        "redis"
        "nats"
        "mosquitto"
        "loki"
        "grafana"
        "minio"
        "influxdb"
    )
    
    authenticate_ecr
    
    for service in "${infra_services[@]}"; do
        local dockerfile_path="${DEPLOYMENTS_DIR}/dockerfiles/Dockerfile.${service}"
        local image_tag="${ECR_REGISTRY}/isa-${service}:latest"
        
        if [[ ! -f "$dockerfile_path" ]]; then
            log_warning "Dockerfile not found: $dockerfile_path"
            continue
        fi
        
        log_info "Building ${service} infrastructure service..."
        cd "$DEPLOYMENTS_DIR"
        docker build -f "$dockerfile_path" -t "$image_tag" .
        
        log_info "Pushing ${service} to ECR..."
        docker push "$image_tag"
        log_success "Built and pushed ${service}: ${image_tag}"
        echo ""
    done
}

# Main script logic
case "${1:-all}" in
    "gateway"|"mcp"|"model"|"agent"|"user")
        authenticate_ecr
        # Build single service (implementation would go here)
        log_info "Building single service: $1"
        ;;
    "infra"|"infrastructure")
        build_infrastructure
        ;;
    "all"|"")
        log_info "Building all services..."
        build_all_services
        build_infrastructure
        ;;
    *)
        echo "Usage: $0 [service-name|infra|all]"
        echo "Services: gateway, mcp, model, agent, user"
        echo "Infrastructure: infra"
        echo "Default: all"
        exit 1
        ;;
esac

log_success "Build process completed!"