# ============================================
# Networking Module - Input Variables
# ============================================

variable "environment" {
  description = "Environment name (staging, production)"
  type        = string
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
}

variable "enable_ecr_endpoint" {
  description = "Enable VPC endpoint for ECR"
  type        = bool
  default     = true
}

variable "enable_s3_endpoint" {
  description = "Enable VPC endpoint for S3"
  type        = bool
  default     = true
}

variable "enable_secretsmanager_endpoint" {
  description = "Enable VPC endpoint for Secrets Manager"
  type        = bool
  default     = true
}

variable "enable_cloudwatch_endpoint" {
  description = "Enable VPC endpoint for CloudWatch Logs"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default     = {}
}
