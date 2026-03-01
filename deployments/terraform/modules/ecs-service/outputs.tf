# ============================================
# ECS Service Module - Outputs
# ============================================

output "service_id" {
  description = "ECS service ID"
  value       = aws_ecs_service.main.id
}

output "service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.main.name
}

output "task_definition_arn" {
  description = "Task definition ARN"
  value       = aws_ecs_task_definition.main.arn
}

output "task_definition_family" {
  description = "Task definition family"
  value       = aws_ecs_task_definition.main.family
}

output "execution_role_arn" {
  description = "Task execution role ARN"
  value       = aws_iam_role.execution.arn
}

output "task_role_arn" {
  description = "Task role ARN"
  value       = aws_iam_role.task.arn
}

output "service_discovery_arn" {
  description = "Service discovery ARN (empty if not enabled)"
  value       = length(aws_service_discovery_service.main) > 0 ? aws_service_discovery_service.main[0].arn : ""
}
