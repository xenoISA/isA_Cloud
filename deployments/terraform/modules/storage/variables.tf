# ============================================
# Storage Module - Input Variables
# ============================================

variable "environment" {
  description = "Environment name (staging, production)"
  type        = string
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID for EFS mount targets"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for EFS mount targets"
  type        = list(string)
}

variable "efs_security_group_id" {
  description = "Security group ID for EFS"
  type        = string
}

variable "efs_access_points" {
  description = "List of EFS access points to create"
  type = list(object({
    name = string
    path = string
  }))
  default = []
}

variable "ecr_repositories" {
  description = "List of ECR repository names to create"
  type        = list(string)
  default     = []
}

variable "ecr_image_tag_mutability" {
  description = "Image tag mutability setting for ECR repositories"
  type        = string
  default     = "MUTABLE"
}

variable "ecr_scan_on_push" {
  description = "Enable image scanning on push"
  type        = bool
  default     = true
}

variable "ecr_lifecycle_policy_days" {
  description = "Number of days to keep untagged images"
  type        = number
  default     = 7
}

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default     = {}
}
