#!/bin/bash

# ECS Fargate Peripheral Services Setup
# Creates all necessary peripheral services for isA Platform

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

# Get network config (same as main script)
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

# Get security group (created by main setup)
get_security_group() {
    print_info "Getting existing security group..."
    
    SG_NAME="isa-ecs-${ENVIRONMENT}"
    SG_ID=$(aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=$SG_NAME" \
        --query "SecurityGroups[0].GroupId" \
        --output text \
        --region $REGION)
    
    print_info "Security Group: $SG_ID"
}

# Create log groups for peripheral services
create_peripheral_log_groups() {
    local services=("nats" "redis" "consul" "neo4j" "influxdb" "postgresql")
    
    for service in "${services[@]}"; do
        print_info "Creating log group for $service..."
        aws logs create-log-group \
            --log-group-name "/ecs/isa-${service}" \
            --region $REGION 2>/dev/null || print_warn "Log group /ecs/isa-${service} already exists"
    done
}

# Register peripheral task definitions
register_peripheral_task_definitions() {
    print_info "Registering peripheral task definitions..."
    
    # NATS
    print_info "Registering NATS task definition..."
    aws ecs register-task-definition \
        --family "isa-nats" \
        --network-mode awsvpc \
        --requires-compatibilities FARGATE \
        --cpu "256" \
        --memory "512" \
        --execution-role-arn "arn:aws:iam::${ACCOUNT_ID}:role/ecsTaskExecutionRole" \
        --container-definitions "[{
            \"name\": \"nats\",
            \"image\": \"${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/isa-nats:latest\",
            \"essential\": true,
            \"portMappings\": [
                {\"containerPort\": 4222, \"protocol\": \"tcp\"},
                {\"containerPort\": 8222, \"protocol\": \"tcp\"},
                {\"containerPort\": 6222, \"protocol\": \"tcp\"}
            ],
            \"logConfiguration\": {
                \"logDriver\": \"awslogs\",
                \"options\": {
                    \"awslogs-group\": \"/ecs/isa-nats\",
                    \"awslogs-region\": \"${REGION}\",
                    \"awslogs-stream-prefix\": \"ecs\"
                }
            },
            \"environment\": [
                {\"name\": \"ENVIRONMENT\", \"value\": \"${ENVIRONMENT}\"}
            ]
        }]" \
        --region $REGION > /dev/null

    # Redis
    print_info "Registering Redis task definition..."
    aws ecs register-task-definition \
        --family "isa-redis" \
        --network-mode awsvpc \
        --requires-compatibilities FARGATE \
        --cpu "256" \
        --memory "512" \
        --execution-role-arn "arn:aws:iam::${ACCOUNT_ID}:role/ecsTaskExecutionRole" \
        --container-definitions "[{
            \"name\": \"redis\",
            \"image\": \"${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/isa-redis:latest\",
            \"essential\": true,
            \"portMappings\": [{\"containerPort\": 6379, \"protocol\": \"tcp\"}],
            \"logConfiguration\": {
                \"logDriver\": \"awslogs\",
                \"options\": {
                    \"awslogs-group\": \"/ecs/isa-redis\",
                    \"awslogs-region\": \"${REGION}\",
                    \"awslogs-stream-prefix\": \"ecs\"
                }
            },
            \"environment\": [
                {\"name\": \"ENVIRONMENT\", \"value\": \"${ENVIRONMENT}\"}
            ]
        }]" \
        --region $REGION > /dev/null

    # Consul
    print_info "Registering Consul task definition..."
    aws ecs register-task-definition \
        --family "isa-consul" \
        --network-mode awsvpc \
        --requires-compatibilities FARGATE \
        --cpu "512" \
        --memory "1024" \
        --execution-role-arn "arn:aws:iam::${ACCOUNT_ID}:role/ecsTaskExecutionRole" \
        --container-definitions "[{
            \"name\": \"consul\",
            \"image\": \"${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/isa-consul:latest\",
            \"essential\": true,
            \"portMappings\": [
                {\"containerPort\": 8500, \"protocol\": \"tcp\"},
                {\"containerPort\": 8600, \"protocol\": \"tcp\"},
                {\"containerPort\": 8300, \"protocol\": \"tcp\"}
            ],
            \"logConfiguration\": {
                \"logDriver\": \"awslogs\",
                \"options\": {
                    \"awslogs-group\": \"/ecs/isa-consul\",
                    \"awslogs-region\": \"${REGION}\",
                    \"awslogs-stream-prefix\": \"ecs\"
                }
            },
            \"environment\": [
                {\"name\": \"ENVIRONMENT\", \"value\": \"${ENVIRONMENT}\"}
            ]
        }]" \
        --region $REGION > /dev/null

    # Neo4j
    print_info "Registering Neo4j task definition..."
    aws ecs register-task-definition \
        --family "isa-neo4j" \
        --network-mode awsvpc \
        --requires-compatibilities FARGATE \
        --cpu "1024" \
        --memory "2048" \
        --execution-role-arn "arn:aws:iam::${ACCOUNT_ID}:role/ecsTaskExecutionRole" \
        --container-definitions "[{
            \"name\": \"neo4j\",
            \"image\": \"${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/isa-neo4j:latest\",
            \"essential\": true,
            \"portMappings\": [
                {\"containerPort\": 7474, \"protocol\": \"tcp\"},
                {\"containerPort\": 7687, \"protocol\": \"tcp\"}
            ],
            \"logConfiguration\": {
                \"logDriver\": \"awslogs\",
                \"options\": {
                    \"awslogs-group\": \"/ecs/isa-neo4j\",
                    \"awslogs-region\": \"${REGION}\",
                    \"awslogs-stream-prefix\": \"ecs\"
                }
            },
            \"environment\": [
                {\"name\": \"ENVIRONMENT\", \"value\": \"${ENVIRONMENT}\"}
            ]
        }]" \
        --region $REGION > /dev/null

    # InfluxDB
    print_info "Registering InfluxDB task definition..."
    aws ecs register-task-definition \
        --family "isa-influxdb" \
        --network-mode awsvpc \
        --requires-compatibilities FARGATE \
        --cpu "512" \
        --memory "1024" \
        --execution-role-arn "arn:aws:iam::${ACCOUNT_ID}:role/ecsTaskExecutionRole" \
        --container-definitions "[{
            \"name\": \"influxdb\",
            \"image\": \"${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/isa-influxdb:latest\",
            \"essential\": true,
            \"portMappings\": [{\"containerPort\": 8086, \"protocol\": \"tcp\"}],
            \"logConfiguration\": {
                \"logDriver\": \"awslogs\",
                \"options\": {
                    \"awslogs-group\": \"/ecs/isa-influxdb\",
                    \"awslogs-region\": \"${REGION}\",
                    \"awslogs-stream-prefix\": \"ecs\"
                }
            },
            \"environment\": [
                {\"name\": \"ENVIRONMENT\", \"value\": \"${ENVIRONMENT}\"}
            ]
        }]" \
        --region $REGION > /dev/null

    # PostgreSQL
    print_info "Registering PostgreSQL task definition..."
    aws ecs register-task-definition \
        --family "isa-postgresql" \
        --network-mode awsvpc \
        --requires-compatibilities FARGATE \
        --cpu "512" \
        --memory "1024" \
        --execution-role-arn "arn:aws:iam::${ACCOUNT_ID}:role/ecsTaskExecutionRole" \
        --container-definitions "[{
            \"name\": \"postgresql\",
            \"image\": \"${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/isa-postgresql:latest\",
            \"essential\": true,
            \"portMappings\": [{\"containerPort\": 5432, \"protocol\": \"tcp\"}],
            \"logConfiguration\": {
                \"logDriver\": \"awslogs\",
                \"options\": {
                    \"awslogs-group\": \"/ecs/isa-postgresql\",
                    \"awslogs-region\": \"${REGION}\",
                    \"awslogs-stream-prefix\": \"ecs\"
                }
            },
            \"environment\": [
                {\"name\": \"ENVIRONMENT\", \"value\": \"${ENVIRONMENT}\"}
            ]
        }]" \
        --region $REGION > /dev/null
}

# Create peripheral ECS services
create_peripheral_services() {
    local services=("nats" "redis" "consul" "neo4j" "influxdb" "postgresql")
    
    for service in "${services[@]}"; do
        print_info "Creating ECS service for $service..."
        
        # Check if service exists
        if aws ecs describe-services \
            --cluster $CLUSTER_NAME \
            --services "isa-${service}" \
            --region $REGION 2>/dev/null | grep -q "isa-${service}"; then
            print_warn "Service isa-${service} already exists"
            continue
        fi
        
        aws ecs create-service \
            --cluster $CLUSTER_NAME \
            --service-name "isa-${service}" \
            --task-definition "isa-${service}" \
            --desired-count 1 \
            --launch-type FARGATE \
            --network-configuration "awsvpcConfiguration={
                subnets=[${SUBNET_LIST}],
                securityGroups=[${SG_ID}],
                assignPublicIp=ENABLED
            }" \
            --region $REGION > /dev/null
        
        print_info "✓ Created service isa-${service} with 1 instance"
    done
}

# Main execution
main() {
    print_info "=== ECS Fargate Peripheral Services Setup for $ENVIRONMENT ==="
    
    # Get network config
    get_network_config
    get_security_group
    
    # Create log groups
    create_peripheral_log_groups
    
    # Register task definitions
    register_peripheral_task_definitions
    
    # Create services
    print_info "Creating peripheral ECS services..."
    create_peripheral_services
    
    print_info "===================================="
    print_info "✅ Peripheral services setup complete!"
    print_info "===================================="
    print_info ""
    print_info "Peripheral services deployed:"
    print_info "  - isa-nats (Message Queue)"
    print_info "  - isa-redis (Cache)"
    print_info "  - isa-consul (Service Discovery)"
    print_info "  - isa-neo4j (Graph Database)"
    print_info "  - isa-influxdb (Time Series DB)"
    print_info "  - isa-postgresql (Relational DB)"
    print_info ""
    print_info "To check service status:"
    print_info "  aws ecs list-services --cluster $CLUSTER_NAME"
    print_info ""
    print_info "To scale services:"
    print_info "  aws ecs update-service --cluster $CLUSTER_NAME --service isa-nats --desired-count 2"
}

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    print_error "AWS CLI not found. Please install it first."
    exit 1
fi

# Run main
main