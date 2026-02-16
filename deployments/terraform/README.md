# isA Cloud - Terraform Infrastructure

This directory contains Terraform configurations for deploying isA Cloud platform to AWS ECS.

## Directory Structure

```
terraform/
├── environments/
│   └── staging/           # Staging environment configuration
│       ├── main.tf        # Root module orchestration
│       ├── variables.tf   # Variable definitions
│       ├── terraform.tfvars # Variable values (gitignored)
│       ├── backend.tf     # S3 backend configuration
│       └── outputs.tf     # Output values
│
└── modules/               # Reusable Terraform modules
    ├── networking/        # VPC, subnets, security groups
    ├── ecs-cluster/       # ECS cluster configuration
    ├── ecs-service/       # Reusable ECS service module
    ├── load-balancer/     # ALB/NLB configuration
    ├── storage/           # EFS, ECR repositories
    ├── secrets/           # AWS Secrets Manager
    └── monitoring/        # CloudWatch dashboards, alarms
```

## Prerequisites

1. **AWS CLI configured** with appropriate credentials
2. **Terraform >= 1.5.0** installed
3. **Docker** for building and pushing images
4. **S3 bucket** for Terraform state (see setup below)

## Initial Setup

### 1. Create Terraform State Backend

Before running Terraform, create the S3 bucket and DynamoDB table for state management:

```bash
# Create S3 bucket for state storage
aws s3 mb s3://isa-cloud-terraform-state-staging --region us-east-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket isa-cloud-terraform-state-staging \
  --versioning-configuration Status=Enabled

# Create DynamoDB table for state locking
aws dynamodb create-table \
  --table-name isa-cloud-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### 2. Configure Variables

```bash
cd environments/staging

# Copy example file
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
vim terraform.tfvars
```

### 3. Initialize Terraform

```bash
terraform init
```

## Deployment Workflow

### Phase 1: Foundation (Week 1)

Deploy core infrastructure:

```bash
# Preview changes
terraform plan

# Apply infrastructure
terraform apply -target=module.networking
terraform apply -target=module.ecs_cluster
terraform apply -target=module.storage
terraform apply -target=module.secrets
terraform apply -target=module.load_balancer
terraform apply -target=module.monitoring
```

### Phase 2: Infrastructure Services (Week 2)

Deploy Consul, Redis, NATS, MinIO, etc.

```bash
# Push images to ECR first
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

docker tag staging-isa-consul:amd64 <account>.dkr.ecr.us-east-1.amazonaws.com/isa-cloud/consul:staging
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/isa-cloud/consul:staging

# Deploy services (to be added in next steps)
# terraform apply -target=module.consul_service
```

### Phase 3+: Services

Deploy gRPC services, gateway, and applications incrementally.

## Common Commands

```bash
# View current state
terraform show

# List all resources
terraform state list

# View specific resource
terraform state show module.networking.aws_vpc.main

# View outputs
terraform output

# Destroy everything (CAREFUL!)
terraform destroy

# Format code
terraform fmt -recursive

# Validate configuration
terraform validate
```

## Important Notes

### User Service Deployment

The user service is **ONE container running 20 microservices** via Supervisor:
- Ports: 8201-8230
- CPU: 4096 (4 vCPU)
- Memory: 8192 MB (8 GB)
- EFS mount for logs

All microservices:
1. auth_service (8201)
2. account_service (8202)
3. session_service (8203)
4. authorization_service (8204)
5. audit_service (8205)
6. notification_service (8206)
7. payment_service (8207)
8. wallet_service (8208)
9. storage_service (8209)
10. order_service (8210)
11. task_service (8211)
12. organization_service (8212)
13. invitation_service (8213)
14. vault_service (8214)
15. product_service (8215)
16. billing_service (8216)
17. device_service (8220)
18. ota_service (8221)
19. telemetry_service (8225)
20. event_service (8230)

### Service Discovery Strategy

- **Consul** runs in ECS and is registered with **AWS Cloud Map**
- All other services discover each other through Consul
- Cloud Map DNS: `consul.isa-cloud.local` → Consul ECS task
- No code changes needed in existing services!

### MinIO S3 Compatibility

MinIO is **100% S3-compatible**:
- Uses standard S3 API (`minio-go/v7`)
- Can be replaced with AWS S3 by changing endpoint
- Current deployment uses EFS for persistence

## Cost Optimization

- Use Fargate Spot for dev/staging (70% savings)
- Right-size task CPU/Memory
- Enable VPC endpoints to reduce NAT costs
- Review CloudWatch logs retention

## Security

- All secrets stored in AWS Secrets Manager
- `terraform.tfvars` is gitignored
- IAM roles follow least privilege principle
- Services communicate via private subnets

## Troubleshooting

### State Lock Issues

If Terraform is stuck with a state lock:

```bash
# List locks
aws dynamodb scan --table-name isa-cloud-terraform-locks

# Force unlock (if safe)
terraform force-unlock <LOCK-ID>
```

### ECS Task Not Starting

```bash
# Check task status
aws ecs describe-tasks --cluster isa-cloud-staging --tasks <task-id>

# Check logs
aws logs tail /ecs/isa-cloud-staging/<service-name> --follow
```

## Next Steps

1. Complete module implementations (networking, ecs-cluster, etc.)
2. Add ECS service modules for each service tier
3. Implement deployment scripts
4. Set up CI/CD pipeline
