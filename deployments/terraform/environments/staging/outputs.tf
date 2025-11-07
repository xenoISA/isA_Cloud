# ============================================
# isA Cloud - Staging Environment Outputs
# ============================================

output "account_id" {
  description = "AWS Account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "region" {
  description = "AWS Region"
  value       = var.aws_region
}

# ============================================
# Networking Outputs
# ============================================
output "vpc_id" {
  description = "VPC ID"
  value       = module.networking.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = module.networking.public_subnet_ids
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = module.networking.private_subnet_ids
}

# ============================================
# ECS Outputs
# ============================================
output "ecs_cluster_name" {
  description = "ECS Cluster name"
  value       = module.ecs_cluster.cluster_name
}

output "ecs_cluster_arn" {
  description = "ECS Cluster ARN"
  value       = module.ecs_cluster.cluster_arn
}

# ============================================
# Storage Outputs
# ============================================
output "efs_file_system_id" {
  description = "EFS File System ID"
  value       = module.storage.efs_file_system_id
}

output "efs_access_point_ids" {
  description = "EFS Access Point IDs for each service"
  value       = module.storage.efs_access_point_ids
}

output "ecr_repository_urls" {
  description = "ECR repository URLs for pushing Docker images"
  value       = module.storage.ecr_repository_urls
}

# ============================================
# Load Balancer Outputs
# ============================================
output "alb_dns_name" {
  description = "ALB DNS name for accessing the application"
  value       = module.load_balancer.alb_dns_name
}

output "alb_zone_id" {
  description = "ALB Zone ID for Route53 alias records"
  value       = module.load_balancer.alb_zone_id
}

output "alb_arn" {
  description = "ALB ARN"
  value       = module.load_balancer.alb_arn
}

# ============================================
# Secrets Outputs
# ============================================
output "secrets_arns" {
  description = "ARNs of secrets in Secrets Manager"
  value       = module.secrets.secret_arns
  sensitive   = true
}

# ============================================
# Service Discovery Outputs
# ============================================
output "cloud_map_namespace_id" {
  description = "Cloud Map namespace ID for service discovery"
  value       = module.networking.cloud_map_namespace_id
}

output "cloud_map_namespace_name" {
  description = "Cloud Map namespace name"
  value       = module.networking.cloud_map_namespace_name
}

# ============================================
# Quick Access Commands
# ============================================
output "ecr_login_command" {
  description = "Command to log in to ECR"
  value       = "aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
}

output "ecs_exec_command_example" {
  description = "Example command to exec into a running container"
  value       = "aws ecs execute-command --cluster ${module.ecs_cluster.cluster_name} --task <TASK-ID> --container <CONTAINER-NAME> --interactive --command '/bin/bash'"
}

output "application_url" {
  description = "Application URL (via ALB)"
  value       = "http://${module.load_balancer.alb_dns_name}"
}
