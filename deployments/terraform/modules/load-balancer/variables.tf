# ============================================
# Load Balancer Module - Variables
# ============================================

variable "environment" {
  description = "Environment name (staging, production, dev)"
  type        = string
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID for the ALB"
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnet IDs for the ALB"
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group ID for the ALB"
  type        = string
}

variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS listener (optional)"
  type        = string
  default     = ""
}

variable "idle_timeout" {
  description = "ALB idle timeout in seconds"
  type        = number
  default     = 60
}

variable "enable_deletion_protection" {
  description = "Enable ALB deletion protection"
  type        = bool
  default     = false
}

variable "health_check_path" {
  description = "Default target group health check path"
  type        = string
  default     = "/health"
}

variable "health_check_interval" {
  description = "Health check interval in seconds"
  type        = number
  default     = 30
}

variable "health_check_timeout" {
  description = "Health check timeout in seconds"
  type        = number
  default     = 5
}

variable "healthy_threshold" {
  description = "Number of consecutive successes before healthy"
  type        = number
  default     = 3
}

variable "unhealthy_threshold" {
  description = "Number of consecutive failures before unhealthy"
  type        = number
  default     = 3
}

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default     = {}
}
