# ============================================
# isA Cloud - Dev Environment Outputs
# ============================================

output "account_id" {
  description = "AWS Account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "region" {
  description = "AWS Region"
  value       = var.aws_region
}

output "vpc_id" {
  description = "VPC ID"
  value       = module.networking.vpc_id
}

output "ecs_cluster_name" {
  description = "ECS Cluster name"
  value       = module.ecs_cluster.cluster_name
}

output "ecr_repository_urls" {
  description = "ECR repository URLs"
  value       = module.storage.ecr_repository_urls
}

output "alb_dns_name" {
  description = "ALB DNS name"
  value       = module.load_balancer.alb_dns_name
}

output "application_url" {
  description = "Application URL (via ALB)"
  value       = "http://${module.load_balancer.alb_dns_name}"
}
