# ============================================
# ECS Service Module - Variables
# ============================================

variable "environment" {
  description = "Environment name (staging, production, dev)"
  type        = string
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "service_name" {
  description = "Name of the ECS service"
  type        = string
}

variable "cluster_id" {
  description = "ECS cluster ID"
  type        = string
}

variable "cluster_name" {
  description = "ECS cluster name"
  type        = string
}

# ============================================
# Container Configuration
# ============================================
variable "container_image" {
  description = "Docker image URI for the container"
  type        = string
}

variable "container_port" {
  description = "Port the container listens on"
  type        = number
}

variable "cpu" {
  description = "CPU units for the task (1 vCPU = 1024)"
  type        = number
  default     = 256
}

variable "memory" {
  description = "Memory in MiB for the task"
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "Desired number of running tasks"
  type        = number
  default     = 1
}

variable "environment_variables" {
  description = "Environment variables for the container"
  type = list(object({
    name  = string
    value = string
  }))
  default = []
}

variable "secrets" {
  description = "Secrets from Secrets Manager or SSM Parameter Store"
  type = list(object({
    name      = string
    valueFrom = string
  }))
  default = []
}

# ============================================
# Networking
# ============================================
variable "private_subnet_ids" {
  description = "Private subnet IDs for the service"
  type        = list(string)
}

variable "security_group_id" {
  description = "Security group ID for the ECS tasks"
  type        = string
}

# ============================================
# Load Balancer (optional)
# ============================================
variable "target_group_arn" {
  description = "ALB target group ARN (empty to skip LB registration)"
  type        = string
  default     = ""
}

# ============================================
# Storage (optional)
# ============================================
variable "efs_file_system_id" {
  description = "EFS file system ID for persistent storage (optional)"
  type        = string
  default     = ""
}

variable "efs_access_point_id" {
  description = "EFS access point ID (optional)"
  type        = string
  default     = ""
}

variable "efs_mount_path" {
  description = "Container path to mount EFS volume"
  type        = string
  default     = "/data"
}

# ============================================
# Service Discovery (optional)
# ============================================
variable "cloud_map_namespace_id" {
  description = "Cloud Map namespace ID for service discovery (optional)"
  type        = string
  default     = ""
}

# ============================================
# IAM
# ============================================
variable "secrets_read_policy_arn" {
  description = "IAM policy ARN for reading secrets (optional)"
  type        = string
  default     = ""
}

# ============================================
# Logging
# ============================================
variable "log_group_name" {
  description = "CloudWatch log group name"
  type        = string
}

# ============================================
# Auto Scaling (optional)
# ============================================
variable "enable_autoscaling" {
  description = "Enable ECS service auto-scaling"
  type        = bool
  default     = false
}

variable "min_capacity" {
  description = "Minimum number of tasks"
  type        = number
  default     = 1
}

variable "max_capacity" {
  description = "Maximum number of tasks"
  type        = number
  default     = 4
}

variable "cpu_target_value" {
  description = "Target CPU utilization for auto-scaling (percent)"
  type        = number
  default     = 70
}

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default     = {}
}
