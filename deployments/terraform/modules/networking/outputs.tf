# ============================================
# Networking Module - Outputs
# ============================================

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC"
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "List of public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "List of private subnet IDs"
  value       = aws_subnet.private[*].id
}

output "alb_security_group_id" {
  description = "Security group ID for ALB"
  value       = aws_security_group.alb.id
}

output "ecs_tasks_security_group_id" {
  description = "Security group ID for ECS tasks"
  value       = aws_security_group.ecs_tasks.id
}

output "efs_security_group_id" {
  description = "Security group ID for EFS"
  value       = aws_security_group.efs.id
}

output "nat_gateway_ids" {
  description = "List of NAT Gateway IDs"
  value       = aws_nat_gateway.main[*].id
}

output "availability_zones" {
  description = "List of availability zones used"
  value       = var.availability_zones
}

output "cloud_map_namespace_id" {
  description = "Cloud Map namespace ID for service discovery"
  value       = aws_service_discovery_private_dns_namespace.main.id
}

output "cloud_map_namespace_name" {
  description = "Cloud Map namespace name"
  value       = aws_service_discovery_private_dns_namespace.main.name
}
