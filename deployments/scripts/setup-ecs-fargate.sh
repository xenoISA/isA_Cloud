#!/bin/bash

# ECS Fargate Infrastructure Setup
# Creates all necessary resources for deployment

set -e

# Configuration
REGION="us-east-1"
ACCOUNT_ID="812363383864"
ENVIRONMENT=${1:-staging}
CLUSTER_NAME="isa-platform-cluster-${ENVIRONMENT}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create IAM roles
setup_iam_roles() {
    print_info "Setting up IAM roles..."
    
    # ECS Task Execution Role
    aws iam create-role \
        --role-name ecsTaskExecutionRole \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }' \
        --region $REGION 2>/dev/null || print_warn "ecsTaskExecutionRole already exists"
    
    aws iam attach-role-policy \
        --role-name ecsTaskExecutionRole \
        --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy \
        --region $REGION 2>/dev/null || true
}

# Create CloudWatch Log Groups
create_log_groups() {
    local services=("gateway" "mcp" "model" "agent" "user-base")
    if [ "$ENVIRONMENT" != "production" ]; then
        services+=("blockchain")
    fi
    
    for service in "${services[@]}"; do
        print_info "Creating log group for $service..."
        aws logs create-log-group \
            --log-group-name "/ecs/isa-${service}" \
            --region $REGION 2>/dev/null || print_warn "Log group /ecs/isa-${service} already exists"
    done
}

# Get default VPC and subnets
get_network_config() {
    print_info "Getting network configuration..."
    
    VPC_ID=$(aws ec2 describe-vpcs \
        --filters "Name=is-default,Values=true" \
        --query "Vpcs[0].VpcId" \
        --output text \
        --region $REGION)
    
    SUBNETS=$(aws ec2 describe-subnets \
        --filters "Name=vpc-id,Values=$VPC_ID" \
        --query "Subnets[*].SubnetId" \
        --output text \
        --region $REGION)
    
    SUBNET_LIST=$(echo $SUBNETS | tr ' ' ',')
    
    print_info "VPC: $VPC_ID"
    print_info "Subnets: $SUBNET_LIST"
}

# Create or get security group
setup_security_group() {
    print_info "Setting up security group..."
    
    SG_NAME="isa-ecs-${ENVIRONMENT}"
    
    # Try to create, ignore if exists
    SG_ID=$(aws ec2 create-security-group \
        --group-name $SG_NAME \
        --description "Security group for isA ECS services" \
        --vpc-id $VPC_ID \
        --query "GroupId" \
        --output text \
        --region $REGION 2>/dev/null || \
        aws ec2 describe-security-groups \
            --filters "Name=group-name,Values=$SG_NAME" \
            --query "SecurityGroups[0].GroupId" \
            --output text \
            --region $REGION)
    
    # Add ingress rules
    aws ec2 authorize-security-group-ingress \
        --group-id $SG_ID \
        --protocol tcp \
        --port 0-65535 \
        --cidr 0.0.0.0/0 \
        --region $REGION 2>/dev/null || true
    
    print_info "Security Group: $SG_ID"
}

# Register task definition
register_task_definition() {
    local service=$1
    local cpu=$2
    local memory=$3
    local port=$4
    
    print_info "Registering task definition for $service..."
    
    aws ecs register-task-definition \
        --family "isa-${service}" \
        --network-mode awsvpc \
        --requires-compatibilities FARGATE \
        --cpu "$cpu" \
        --memory "$memory" \
        --execution-role-arn "arn:aws:iam::${ACCOUNT_ID}:role/ecsTaskExecutionRole" \
        --container-definitions "[{
            \"name\": \"${service}\",
            \"image\": \"${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/isa-${service}:latest\",
            \"essential\": true,
            \"portMappings\": [{
                \"containerPort\": ${port},
                \"protocol\": \"tcp\"
            }],
            \"logConfiguration\": {
                \"logDriver\": \"awslogs\",
                \"options\": {
                    \"awslogs-group\": \"/ecs/isa-${service}\",
                    \"awslogs-region\": \"${REGION}\",
                    \"awslogs-stream-prefix\": \"ecs\"
                }
            },
            \"environment\": [
                {\"name\": \"ENVIRONMENT\", \"value\": \"${ENVIRONMENT}\"},
                {\"name\": \"PORT\", \"value\": \"${port}\"}
            ]
        }]" \
        --region $REGION > /dev/null
}

# Create ECS service
create_ecs_service() {
    local service=$1
    
    print_info "Creating ECS service for $service..."
    
    # Check if service exists
    if aws ecs describe-services \
        --cluster $CLUSTER_NAME \
        --services "isa-${service}" \
        --region $REGION 2>/dev/null | grep -q "isa-${service}"; then
        print_warn "Service isa-${service} already exists"
        return
    fi
    
    aws ecs create-service \
        --cluster $CLUSTER_NAME \
        --service-name "isa-${service}" \
        --task-definition "isa-${service}" \
        --desired-count 0 \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={
            subnets=[${SUBNET_LIST}],
            securityGroups=[${SG_ID}],
            assignPublicIp=ENABLED
        }" \
        --region $REGION > /dev/null
    
    print_info "✓ Created service isa-${service} (initially scaled to 0)"
}

# Main execution
main() {
    print_info "=== ECS Fargate Setup for $ENVIRONMENT ==="
    
    # Setup IAM
    setup_iam_roles
    
    # Create log groups
    create_log_groups
    
    # Get network config
    get_network_config
    setup_security_group
    
    # Register task definitions
    print_info "Registering task definitions..."
    register_task_definition "gateway" "256" "512" "8000"
    register_task_definition "mcp" "512" "1024" "8081"
    register_task_definition "model" "1024" "2048" "8082"
    register_task_definition "agent" "512" "1024" "8083"
    register_task_definition "user-base" "512" "1024" "8201"
    
    if [ "$ENVIRONMENT" != "production" ]; then
        register_task_definition "blockchain" "512" "1024" "8545"
    fi
    
    # Create services
    print_info "Creating ECS services..."
    create_ecs_service "gateway"
    create_ecs_service "mcp"
    create_ecs_service "model"
    create_ecs_service "agent"
    create_ecs_service "user-base"
    
    if [ "$ENVIRONMENT" != "production" ]; then
        create_ecs_service "blockchain"
    fi
    
    print_info "==================================="
    print_info "✅ ECS Fargate setup complete!"
    print_info "==================================="
    print_info ""
    print_info "Services created (scaled to 0):"
    print_info "  - isa-gateway"
    print_info "  - isa-mcp"
    print_info "  - isa-model"
    print_info "  - isa-agent"
    print_info "  - isa-user-base"
    [ "$ENVIRONMENT" != "production" ] && print_info "  - isa-blockchain"
    print_info ""
    print_info "To deploy a service, first push Docker image then:"
    print_info "  aws ecs update-service --cluster $CLUSTER_NAME --service isa-gateway --desired-count 1"
    print_info ""
    print_info "To stop a service (save money):"
    print_info "  aws ecs update-service --cluster $CLUSTER_NAME --service isa-gateway --desired-count 0"
}

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI not found. Please install it first."
    exit 1
fi

# Run main
main