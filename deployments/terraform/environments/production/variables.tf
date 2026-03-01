# ============================================
# isA Cloud - Production Environment Variables
# ============================================

# ============================================
# General Configuration
# ============================================
variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "isa-cloud"
}

# ============================================
# Networking Configuration
# ============================================
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.1.0.0/16"
}

# ============================================
# Database Secrets (Supabase)
# ============================================
variable "supabase_url" {
  description = "Supabase project URL"
  type        = string
  sensitive   = true
}

variable "supabase_anon_key" {
  description = "Supabase anonymous key"
  type        = string
  sensitive   = true
}

variable "supabase_service_role_key" {
  description = "Supabase service role key"
  type        = string
  sensitive   = true
}

variable "database_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

# ============================================
# Infrastructure Secrets
# ============================================
variable "redis_password" {
  description = "Redis password"
  type        = string
  sensitive   = true
}

variable "minio_root_user" {
  description = "MinIO root user"
  type        = string
  sensitive   = true
}

variable "minio_root_password" {
  description = "MinIO root password"
  type        = string
  sensitive   = true
}

# ============================================
# Application Secrets
# ============================================
variable "jwt_secret" {
  description = "JWT secret for gateway"
  type        = string
  sensitive   = true
}

variable "mcp_api_key" {
  description = "MCP API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "composio_api_key" {
  description = "Composio API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "brave_token" {
  description = "Brave search API token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "neo4j_password" {
  description = "Neo4j database password"
  type        = string
  sensitive   = true
  default     = ""
}

variable "stripe_secret_key" {
  description = "Stripe API secret key for payments"
  type        = string
  sensitive   = true
  default     = ""
}

variable "stripe_webhook_secret" {
  description = "Stripe webhook secret"
  type        = string
  sensitive   = true
  default     = ""
}

# ============================================
# SSL/TLS Configuration
# ============================================
variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS (required for production)"
  type        = string
}

# ============================================
# Monitoring Configuration
# ============================================
variable "alarm_email_endpoints" {
  description = "Email addresses for CloudWatch alarms"
  type        = list(string)
}
