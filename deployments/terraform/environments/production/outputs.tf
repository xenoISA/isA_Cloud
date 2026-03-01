# ============================================
# isA Cloud - Production Environment Outputs
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

output "ecr_repository_urls" {
  description = "ECR repository URLs"
  value       = module.storage.ecr_repository_urls
}

# ============================================
# Load Balancer Outputs
# ============================================
output "alb_dns_name" {
  description = "ALB DNS name"
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
# Monitoring Outputs
# ============================================
output "log_group_name" {
  description = "CloudWatch log group name"
  value       = module.monitoring.log_group_name
}

output "sns_topic_arn" {
  description = "SNS alarm topic ARN"
  value       = module.monitoring.sns_topic_arn
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
# Quick Access Commands
# ============================================
output "application_url" {
  description = "Application URL (via ALB)"
  value       = "https://${module.load_balancer.alb_dns_name}"
}
