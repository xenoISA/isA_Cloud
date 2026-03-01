# ============================================
# Monitoring Module - Variables
# ============================================

variable "environment" {
  description = "Environment name (staging, production, dev)"
  type        = string
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "cluster_name" {
  description = "ECS cluster name for CloudWatch metrics"
  type        = string
}

variable "enable_alarms" {
  description = "Enable CloudWatch alarms"
  type        = bool
  default     = true
}

variable "alarm_email_endpoints" {
  description = "Email addresses for alarm notifications"
  type        = list(string)
  default     = []
}

variable "log_retention_days" {
  description = "CloudWatch log group retention in days"
  type        = number
  default     = 30
}

variable "cpu_alarm_threshold" {
  description = "CPU utilization alarm threshold (percent)"
  type        = number
  default     = 80
}

variable "memory_alarm_threshold" {
  description = "Memory utilization alarm threshold (percent)"
  type        = number
  default     = 80
}

variable "alarm_evaluation_periods" {
  description = "Number of periods to evaluate before alarming"
  type        = number
  default     = 3
}

variable "alarm_period" {
  description = "Alarm evaluation period in seconds"
  type        = number
  default     = 300
}

variable "enable_dashboard" {
  description = "Create CloudWatch dashboard"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default     = {}
}
