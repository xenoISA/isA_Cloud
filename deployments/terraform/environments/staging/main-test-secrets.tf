# ============================================
# isA Cloud - Staging Environment
# ============================================
# Testing networking + ECS + storage + secrets modules

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ============================================
# Provider Configuration
# ============================================
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = var.project_name
      ManagedBy   = "Terraform"
      Repository  = "isA_Cloud"
    }
  }
}

# ============================================
# Data Sources
# ============================================
data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}

# ============================================
# Local Variables
# ============================================
locals {
  account_id = data.aws_caller_identity.current.account_id

  # Common tags
  common_tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# ============================================
# Module: Networking
# ============================================
module "networking" {
  source = "../../modules/networking"

  environment        = var.environment
  project_name       = var.project_name
  vpc_cidr           = var.vpc_cidr
  availability_zones = slice(data.aws_availability_zones.available.names, 0, 2)

  enable_ecr_endpoint            = true
  enable_s3_endpoint             = true
  enable_secretsmanager_endpoint = true
  enable_cloudwatch_endpoint     = true

  tags = local.common_tags
}

# ============================================
# Module: ECS Cluster
# ============================================
module "ecs_cluster" {
  source = "../../modules/ecs-cluster"

  cluster_name              = "${var.project_name}-${var.environment}"
  environment               = var.environment
  enable_container_insights = true
  enable_execute_command    = true

  tags = local.common_tags
}

# ============================================
# Module: Storage (EFS + ECR)
# ============================================
module "storage" {
  source = "../../modules/storage"

  environment  = var.environment
  project_name = var.project_name

  vpc_id                = module.networking.vpc_id
  private_subnet_ids    = module.networking.private_subnet_ids
  efs_security_group_id = module.networking.efs_security_group_id

  efs_access_points = [
    { name = "consul", path = "/consul" },
    { name = "redis", path = "/redis" },
    { name = "minio", path = "/minio" },
    { name = "nats", path = "/nats" },
    { name = "mosquitto", path = "/mosquitto" },
    { name = "loki", path = "/loki" },
    { name = "grafana", path = "/grafana" },
    { name = "duckdb", path = "/duckdb" },
  ]

  ecr_repositories = [
    "consul", "redis", "minio", "nats", "mosquitto", "loki", "grafana",
    "minio-grpc", "duckdb-grpc", "mqtt-grpc", "loki-grpc", "redis-grpc", "nats-grpc", "supabase-grpc",
    "gateway", "openresty",
    "agent", "model", "mcp", "user"
  ]

  tags = local.common_tags
}

# ============================================
# Module: Secrets Management
# ============================================
module "secrets" {
  source = "../../modules/secrets"

  environment  = var.environment
  project_name = var.project_name

  # Secrets configuration
  secrets = {
    database = {
      description = "Supabase database credentials"
      secret_data = {
        SUPABASE_URL              = var.supabase_url
        SUPABASE_ANON_KEY         = var.supabase_anon_key
        SUPABASE_SERVICE_ROLE_KEY = var.supabase_service_role_key
        DATABASE_PASSWORD         = var.database_password
      }
    }
    redis = {
      description = "Redis credentials"
      secret_data = {
        REDIS_PASSWORD = var.redis_password
      }
    }
    minio = {
      description = "MinIO credentials"
      secret_data = {
        MINIO_ROOT_USER     = var.minio_root_user
        MINIO_ROOT_PASSWORD = var.minio_root_password
      }
    }
    gateway = {
      description = "Gateway service secrets"
      secret_data = {
        JWT_SECRET = var.jwt_secret
      }
    }
    mcp = {
      description = "MCP service API keys"
      secret_data = {
        MCP_API_KEY      = var.mcp_api_key
        COMPOSIO_API_KEY = var.composio_api_key
        BRAVE_TOKEN      = var.brave_token
        NEO4J_PASSWORD   = var.neo4j_password
      }
    }
  }

  recovery_window_in_days = 7
  enable_rotation         = false

  tags = local.common_tags
}

# ============================================
# Outputs for Testing
# ============================================
output "vpc_id" {
  description = "VPC ID"
  value       = module.networking.vpc_id
}

output "cluster_name" {
  description = "ECS Cluster name"
  value       = module.ecs_cluster.cluster_name
}

output "efs_file_system_id" {
  description = "EFS File System ID"
  value       = module.storage.efs_file_system_id
}

output "secret_names" {
  description = "Secret names in Secrets Manager"
  value       = module.secrets.secret_names
}

output "secrets_read_policy_arn" {
  description = "IAM policy ARN for reading secrets"
  value       = module.secrets.secrets_read_policy_arn
}

output "monthly_cost_estimate" {
  description = "Estimated monthly cost for Secrets Manager"
  value       = "$${length(module.secrets.secret_names) * 0.40} USD/month for secrets storage"
}
