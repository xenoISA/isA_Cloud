# ============================================
# isA Cloud - Dev Environment
# ============================================
# Cost-optimized configuration: single AZ, minimal resources,
# no deletion protection, short log retention.

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

  common_tags = {
    Environment = var.environment
    Project     = var.project_name
  }

  # Dev service configuration — minimal resources
  services = {
    # Infrastructure services (minimum viable)
    consul    = { port = 8500, cpu = 256, memory = 512 }
    redis     = { port = 6379, cpu = 256, memory = 512 }
    minio     = { port = 9000, cpu = 512, memory = 1024 }
    nats      = { port = 4222, cpu = 256, memory = 512 }
    mosquitto = { port = 1883, cpu = 256, memory = 512 }

    # Gateway layer
    gateway = { port = 8000, cpu = 512, memory = 1024 }

    # Application services (minimal)
    agent = { port = 8080, cpu = 1024, memory = 2048 }
    model = { port = 8082, cpu = 2048, memory = 4096 }
    mcp   = { port = 8081, cpu = 1024, memory = 2048 }
    user  = { port = 8201, cpu = 2048, memory = 4096 }
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

  # Disable VPC endpoints to save cost in dev
  enable_ecr_endpoint            = false
  enable_s3_endpoint             = true
  enable_secretsmanager_endpoint = false
  enable_cloudwatch_endpoint     = false

  tags = local.common_tags
}

# ============================================
# Module: ECS Cluster
# ============================================
module "ecs_cluster" {
  source = "../../modules/ecs-cluster"

  cluster_name              = "${var.project_name}-${var.environment}"
  environment               = var.environment
  enable_container_insights = false

  tags = local.common_tags
}

# ============================================
# Module: Storage (EFS, ECR)
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
  ]

  # Fewer ECR repos in dev — only core services
  ecr_repositories = [
    "consul", "redis", "minio", "nats",
    "gateway",
    "agent", "model", "mcp", "user"
  ]

  ecr_lifecycle_policy_days = 3

  tags = local.common_tags
}

# ============================================
# Module: Secrets Management
# ============================================
module "secrets" {
  source = "../../modules/secrets"

  environment  = var.environment
  project_name = var.project_name

  recovery_window_in_days = 0

  secrets = {
    database = {
      description = "Database credentials (dev)"
      secret_data = {
        SUPABASE_URL              = var.supabase_url
        SUPABASE_ANON_KEY         = var.supabase_anon_key
        SUPABASE_SERVICE_ROLE_KEY = var.supabase_service_role_key
        DATABASE_PASSWORD         = var.database_password
      }
    }
    redis = {
      description = "Redis credentials (dev)"
      secret_data = {
        REDIS_PASSWORD = var.redis_password
      }
    }
    minio = {
      description = "MinIO credentials (dev)"
      secret_data = {
        MINIO_ROOT_USER     = var.minio_root_user
        MINIO_ROOT_PASSWORD = var.minio_root_password
      }
    }
    gateway = {
      description = "Gateway service secrets (dev)"
      secret_data = {
        JWT_SECRET = var.jwt_secret
      }
    }
  }

  tags = local.common_tags
}

# ============================================
# Module: Load Balancer
# ============================================
module "load_balancer" {
  source = "../../modules/load-balancer"

  environment  = var.environment
  project_name = var.project_name

  vpc_id                = module.networking.vpc_id
  public_subnet_ids     = module.networking.public_subnet_ids
  alb_security_group_id = module.networking.alb_security_group_id

  enable_deletion_protection = false

  tags = local.common_tags
}

# ============================================
# Module: Monitoring
# ============================================
module "monitoring" {
  source = "../../modules/monitoring"

  environment  = var.environment
  project_name = var.project_name
  cluster_name = module.ecs_cluster.cluster_name

  enable_alarms      = false
  log_retention_days = 7
  enable_dashboard   = false

  tags = local.common_tags
}
