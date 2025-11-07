# ============================================
# isA Cloud - Staging Environment
# ============================================
# Main Terraform configuration for ECS deployment
#
# This file orchestrates all modules for the staging environment

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

  # Service configuration
  services = {
    # Infrastructure services
    consul    = { port = 8500, cpu = 512, memory = 1024 }
    redis     = { port = 6379, cpu = 512, memory = 1024 }
    minio     = { port = 9000, cpu = 1024, memory = 2048 }
    nats      = { port = 4222, cpu = 512, memory = 1024 }
    mosquitto = { port = 1883, cpu = 256, memory = 512 }
    loki      = { port = 3100, cpu = 512, memory = 1024 }
    grafana   = { port = 3000, cpu = 256, memory = 512 }

    # gRPC services
    minio_grpc    = { port = 50051, cpu = 256, memory = 512 }
    duckdb_grpc   = { port = 50052, cpu = 256, memory = 512 }
    mqtt_grpc     = { port = 50053, cpu = 256, memory = 512 }
    loki_grpc     = { port = 50054, cpu = 256, memory = 512 }
    redis_grpc    = { port = 50055, cpu = 256, memory = 512 }
    nats_grpc     = { port = 50056, cpu = 256, memory = 512 }
    supabase_grpc = { port = 50057, cpu = 256, memory = 512 }

    # Gateway layer
    gateway   = { port = 8000, cpu = 1024, memory = 2048 }
    openresty = { port = 80, cpu = 512, memory = 1024 }

    # Application services
    agent = { port = 8080, cpu = 2048, memory = 4096 }
    model = { port = 8082, cpu = 4096, memory = 8192 }
    mcp   = { port = 8081, cpu = 2048, memory = 4096 }
    user  = { port = 8201, cpu = 4096, memory = 8192 }
  }
}

# ============================================
# Module: Networking (VPC, Subnets, Security Groups)
# ============================================
module "networking" {
  source = "../../modules/networking"

  environment        = var.environment
  project_name       = var.project_name
  vpc_cidr           = var.vpc_cidr
  availability_zones = slice(data.aws_availability_zones.available.names, 0, 2)

  # Enable VPC endpoints to reduce NAT costs
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

  cluster_name = "${var.project_name}-${var.environment}"
  environment  = var.environment

  # Enable Container Insights for monitoring
  enable_container_insights = true

  tags = local.common_tags
}

# ============================================
# Module: Storage (EFS, ECR)
# ============================================
module "storage" {
  source = "../../modules/storage"

  environment  = var.environment
  project_name = var.project_name

  # VPC configuration for EFS
  vpc_id                = module.networking.vpc_id
  private_subnet_ids    = module.networking.private_subnet_ids
  efs_security_group_id = module.networking.efs_security_group_id

  # EFS access points for stateful services
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

  # ECR repositories for all services
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

  tags = local.common_tags
}

# ============================================
# Module: Load Balancer (ALB for public access)
# ============================================
module "load_balancer" {
  source = "../../modules/load-balancer"

  environment  = var.environment
  project_name = var.project_name

  vpc_id                = module.networking.vpc_id
  public_subnet_ids     = module.networking.public_subnet_ids
  alb_security_group_id = module.networking.alb_security_group_id

  # SSL certificate ARN (optional - can be added later)
  # certificate_arn = var.certificate_arn

  tags = local.common_tags
}

# ============================================
# Module: Monitoring (CloudWatch)
# ============================================
module "monitoring" {
  source = "../../modules/monitoring"

  environment  = var.environment
  project_name = var.project_name
  cluster_name = module.ecs_cluster.cluster_name

  # Alarm configuration
  enable_alarms         = true
  alarm_email_endpoints = var.alarm_email_endpoints

  tags = local.common_tags
}

# ============================================
# Outputs - See outputs.tf for all output definitions
# ============================================
