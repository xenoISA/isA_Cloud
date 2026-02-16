# ============================================
# ECS Cluster Module - Outputs
# ============================================

output "cluster_id" {
  description = "ID of the ECS cluster"
  value       = aws_ecs_cluster.main.id
}

output "cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "cluster_arn" {
  description = "ARN of the ECS cluster"
  value       = aws_ecs_cluster.main.arn
}

output "capacity_providers" {
  description = "List of capacity providers for the cluster"
  value       = aws_ecs_cluster_capacity_providers.main.capacity_providers
}
