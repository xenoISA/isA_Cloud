# ============================================
# Storage Module - Outputs
# ============================================

# ============================================
# EFS Outputs
# ============================================
output "efs_file_system_id" {
  description = "ID of the EFS file system"
  value       = aws_efs_file_system.main.id
}

output "efs_file_system_arn" {
  description = "ARN of the EFS file system"
  value       = aws_efs_file_system.main.arn
}

output "efs_file_system_dns_name" {
  description = "DNS name of the EFS file system"
  value       = aws_efs_file_system.main.dns_name
}

output "efs_access_point_ids" {
  description = "Map of EFS access point names to IDs"
  value       = { for k, v in aws_efs_access_point.access_points : k => v.id }
}

output "efs_access_point_arns" {
  description = "Map of EFS access point names to ARNs"
  value       = { for k, v in aws_efs_access_point.access_points : k => v.arn }
}

output "efs_mount_target_ids" {
  description = "List of EFS mount target IDs"
  value       = aws_efs_mount_target.main[*].id
}

output "efs_mount_target_dns_names" {
  description = "List of EFS mount target DNS names"
  value       = aws_efs_mount_target.main[*].dns_name
}

# ============================================
# ECR Outputs
# ============================================
output "ecr_repository_urls" {
  description = "Map of ECR repository names to URLs"
  value       = { for k, v in aws_ecr_repository.repositories : k => v.repository_url }
}

output "ecr_repository_arns" {
  description = "Map of ECR repository names to ARNs"
  value       = { for k, v in aws_ecr_repository.repositories : k => v.arn }
}

output "ecr_repository_names" {
  description = "List of ECR repository names"
  value       = [for k, v in aws_ecr_repository.repositories : v.name]
}

# ============================================
# Convenience Outputs
# ============================================
output "ecr_login_command" {
  description = "Command to log in to ECR"
  value       = "aws ecr get-login-password --region ${data.aws_region.current.name} | docker login --username AWS --password-stdin ${data.aws_caller_identity.current.account_id}.dkr.ecr.${data.aws_region.current.name}.amazonaws.com"
}

output "account_id" {
  description = "AWS Account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "region" {
  description = "AWS Region"
  value       = data.aws_region.current.name
}
