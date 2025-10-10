#!/bin/bash
# ============================================
# Build and Push Docker Images to ECR
# ============================================
# Source of truth: services.yaml
# This script builds Docker images for all services and pushes them to AWS ECR
#
# Usage:
#   ./build-and-push-ecr.sh <environment> [service]
#
# Examples:
#   ./build-and-push-ecr.sh staging              # Build and push all services
#   ./build-and-push-ecr.sh staging gateway      # Build and push only gateway
#   ./build-and-push-ecr.sh production mcp       # Build and push only mcp

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================
# Configuration
# ============================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOYMENTS_DIR="$(dirname "$SCRIPT_DIR")"
SERVICES_YAML="$DEPLOYMENTS_DIR/services.yaml"

# Check environment argument
ENVIRONMENT=${1:-staging}
SINGLE_SERVICE=$2

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}isA Platform - Build and Push to ECR${NC}"
echo -e "${BLUE}============================================${NC}"
echo -e "Environment: ${GREEN}$ENVIRONMENT${NC}"
echo ""

# ============================================
# Get AWS Account ID and Region
# ============================================
echo -e "${YELLOW}📋 Getting AWS account information...${NC}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region || echo "us-west-2")
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo -e "AWS Account ID: ${GREEN}$AWS_ACCOUNT_ID${NC}"
echo -e "AWS Region: ${GREEN}$AWS_REGION${NC}"
echo -e "ECR Registry: ${GREEN}$ECR_REGISTRY${NC}"
echo ""

# ============================================
# Login to ECR
# ============================================
echo -e "${YELLOW}🔐 Logging in to ECR...${NC}"
aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "$ECR_REGISTRY"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Successfully logged in to ECR${NC}"
    echo ""
else
    echo -e "${RED}✗ Failed to login to ECR${NC}"
    exit 1
fi

# ============================================
# Build and Push Functions
# ============================================

build_and_push_gateway() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}🏗️  Building Gateway Service...${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    cd "$DEPLOYMENTS_DIR/.."
    docker build --platform linux/amd64 -f deployments/dockerfiles/Dockerfile.gateway \
        -t isa-gateway:latest \
        -t ${ECR_REGISTRY}/isa-gateway:latest \
        -t ${ECR_REGISTRY}/isa-gateway:${ENVIRONMENT} .

    echo -e "${YELLOW}📤 Pushing Gateway to ECR...${NC}"
    docker push ${ECR_REGISTRY}/isa-gateway:latest
    docker push ${ECR_REGISTRY}/isa-gateway:${ENVIRONMENT}
    echo -e "${GREEN}✓ Gateway pushed successfully${NC}"
    echo ""
}

build_and_push_mcp() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}🏗️  Building MCP Service...${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    MCP_PATH="$DEPLOYMENTS_DIR/../../isA_MCP"
    if [ ! -d "$MCP_PATH" ]; then
        echo -e "${RED}✗ MCP repository not found at $MCP_PATH${NC}"
        return 1
    fi

    cd "$MCP_PATH"
    docker build --platform linux/amd64 -f deployment/Dockerfile.mcp \
        -t isa-mcp:latest \
        -t ${ECR_REGISTRY}/isa-mcp:latest \
        -t ${ECR_REGISTRY}/isa-mcp:${ENVIRONMENT} .

    echo -e "${YELLOW}📤 Pushing MCP to ECR...${NC}"
    docker push ${ECR_REGISTRY}/isa-mcp:latest
    docker push ${ECR_REGISTRY}/isa-mcp:${ENVIRONMENT}
    echo -e "${GREEN}✓ MCP pushed successfully${NC}"
    echo ""
}

build_and_push_model() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}🏗️  Building Model Service...${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    MODEL_PATH="$DEPLOYMENTS_DIR/../../isA_Model"
    if [ ! -d "$MODEL_PATH" ]; then
        echo -e "${RED}✗ Model repository not found at $MODEL_PATH${NC}"
        return 1
    fi

    cd "$MODEL_PATH"
    docker build --platform linux/amd64 -f deployment/Dockerfile.model \
        -t isa-model:latest \
        -t ${ECR_REGISTRY}/isa-model:latest \
        -t ${ECR_REGISTRY}/isa-model:${ENVIRONMENT} .

    echo -e "${YELLOW}📤 Pushing Model to ECR...${NC}"
    docker push ${ECR_REGISTRY}/isa-model:latest
    docker push ${ECR_REGISTRY}/isa-model:${ENVIRONMENT}
    echo -e "${GREEN}✓ Model pushed successfully${NC}"
    echo ""
}

build_and_push_agent() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}🏗️  Building Agent Service...${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    AGENT_PATH="$DEPLOYMENTS_DIR/../../isA_Agent"
    if [ ! -d "$AGENT_PATH" ]; then
        echo -e "${RED}✗ Agent repository not found at $AGENT_PATH${NC}"
        return 1
    fi

    cd "$AGENT_PATH"
    docker build --platform linux/amd64 -f deployment/Dockerfile.agent \
        -t isa-agent:latest \
        -t ${ECR_REGISTRY}/isa-agent:latest \
        -t ${ECR_REGISTRY}/isa-agent:${ENVIRONMENT} .

    echo -e "${YELLOW}📤 Pushing Agent to ECR...${NC}"
    docker push ${ECR_REGISTRY}/isa-agent:latest
    docker push ${ECR_REGISTRY}/isa-agent:${ENVIRONMENT}
    echo -e "${GREEN}✓ Agent pushed successfully${NC}"
    echo ""
}

build_and_push_user() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}🏗️  Building User Microservices Base Image...${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    USER_PATH="$DEPLOYMENTS_DIR/../../isA_user"
    if [ ! -d "$USER_PATH" ]; then
        echo -e "${RED}✗ User repository not found at $USER_PATH${NC}"
        return 1
    fi

    cd "$USER_PATH"
    docker build --platform linux/amd64 -f deployment/docker/Dockerfile.user \
        -t isa-user:latest \
        -t ${ECR_REGISTRY}/isa-user:latest \
        -t ${ECR_REGISTRY}/isa-user:${ENVIRONMENT} .

    echo -e "${YELLOW}📤 Pushing User base image to ECR...${NC}"
    docker push ${ECR_REGISTRY}/isa-user:latest
    docker push ${ECR_REGISTRY}/isa-user:${ENVIRONMENT}
    echo -e "${GREEN}✓ User base image pushed successfully${NC}"
    echo ""
}

build_and_push_infrastructure() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}🏗️  Building Infrastructure Services...${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    cd "$DEPLOYMENTS_DIR"

    # Redis
    echo -e "${YELLOW}Building Redis...${NC}"
    docker build --platform linux/amd64 -f dockerfiles/Dockerfile.redis -t ${ECR_REGISTRY}/isa-redis:latest .
    docker push ${ECR_REGISTRY}/isa-redis:latest

    # Consul
    echo -e "${YELLOW}Building Consul...${NC}"
    docker build --platform linux/amd64 -f dockerfiles/Dockerfile.consul -t ${ECR_REGISTRY}/isa-consul:latest .
    docker push ${ECR_REGISTRY}/isa-consul:latest

    # NATS
    echo -e "${YELLOW}Building NATS...${NC}"
    docker build --platform linux/amd64 -f dockerfiles/Dockerfile.nats -t ${ECR_REGISTRY}/isa-nats:latest .
    docker push ${ECR_REGISTRY}/isa-nats:latest

    # InfluxDB
    echo -e "${YELLOW}Building InfluxDB...${NC}"
    docker build --platform linux/amd64 -f dockerfiles/Dockerfile.influxdb -t ${ECR_REGISTRY}/isa-influxdb:latest .
    docker push ${ECR_REGISTRY}/isa-influxdb:latest

    # Mosquitto
    echo -e "${YELLOW}Building Mosquitto...${NC}"
    docker build --platform linux/amd64 -f dockerfiles/Dockerfile.mosquitto -t ${ECR_REGISTRY}/isa-mosquitto:latest .
    docker push ${ECR_REGISTRY}/isa-mosquitto:latest

    # Loki
    echo -e "${YELLOW}Building Loki...${NC}"
    docker build --platform linux/amd64 -f dockerfiles/Dockerfile.loki -t ${ECR_REGISTRY}/isa-loki:latest .
    docker push ${ECR_REGISTRY}/isa-loki:latest

    # Grafana
    echo -e "${YELLOW}Building Grafana...${NC}"
    docker build --platform linux/amd64 -f dockerfiles/Dockerfile.grafana -t ${ECR_REGISTRY}/isa-grafana:latest .
    docker push ${ECR_REGISTRY}/isa-grafana:latest

    echo -e "${GREEN}✓ Infrastructure services pushed successfully${NC}"
    echo ""
}

# ============================================
# Main Build Process
# ============================================

if [ -n "$SINGLE_SERVICE" ]; then
    # Build single service
    case $SINGLE_SERVICE in
        gateway)
            build_and_push_gateway
            ;;
        mcp)
            build_and_push_mcp
            ;;
        model)
            build_and_push_model
            ;;
        agent)
            build_and_push_agent
            ;;
        user)
            build_and_push_user
            ;;
        infrastructure)
            build_and_push_infrastructure
            ;;
        *)
            echo -e "${RED}✗ Unknown service: $SINGLE_SERVICE${NC}"
            echo -e "Valid services: gateway, mcp, model, agent, user, infrastructure"
            exit 1
            ;;
    esac
else
    # Build all services
    build_and_push_gateway
    build_and_push_mcp
    build_and_push_model
    build_and_push_agent
    build_and_push_user
    build_and_push_infrastructure
fi

# ============================================
# Summary
# ============================================
echo -e "${BLUE}============================================${NC}"
echo -e "${GREEN}✓ Build and Push Complete!${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo -e "Images are now available in ECR:"
echo -e "  ${ECR_REGISTRY}"
echo ""
echo -e "Next steps:"
echo -e "  1. cd terraform/environments/${ENVIRONMENT}"
echo -e "  2. terraform init"
echo -e "  3. terraform plan"
echo -e "  4. terraform apply"
echo ""
