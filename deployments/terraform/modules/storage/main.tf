# ============================================
# Storage Module - Main Configuration
# ============================================
# Creates EFS file system and ECR repositories

# ============================================
# EFS File System
# ============================================
resource "aws_efs_file_system" "main" {
  creation_token = "${var.project_name}-${var.environment}-efs"
  encrypted      = true

  performance_mode = "generalPurpose"
  throughput_mode  = "bursting"

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }

  lifecycle_policy {
    transition_to_primary_storage_class = "AFTER_1_ACCESS"
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-efs"
    }
  )
}

# ============================================
# EFS Mount Targets (one per subnet/AZ)
# ============================================
resource "aws_efs_mount_target" "main" {
  count = length(var.private_subnet_ids)

  file_system_id  = aws_efs_file_system.main.id
  subnet_id       = var.private_subnet_ids[count.index]
  security_groups = [var.efs_security_group_id]
}

# ============================================
# EFS Access Points
# ============================================
resource "aws_efs_access_point" "access_points" {
  for_each = { for ap in var.efs_access_points : ap.name => ap }

  file_system_id = aws_efs_file_system.main.id

  posix_user {
    gid = 1000
    uid = 1000
  }

  root_directory {
    path = each.value.path

    creation_info {
      owner_gid   = 1000
      owner_uid   = 1000
      permissions = "755"
    }
  }

  tags = merge(
    var.tags,
    {
      Name    = "${var.project_name}-${var.environment}-${each.key}"
      Service = each.key
    }
  )
}

# ============================================
# ECR Repositories
# ============================================
resource "aws_ecr_repository" "repositories" {
  for_each = toset(var.ecr_repositories)

  name                 = "${var.project_name}/${each.value}"
  image_tag_mutability = var.ecr_image_tag_mutability

  image_scanning_configuration {
    scan_on_push = var.ecr_scan_on_push
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(
    var.tags,
    {
      Name    = "${var.project_name}-${var.environment}-${each.value}"
      Service = each.value
    }
  )
}

# ============================================
# ECR Lifecycle Policies
# ============================================
resource "aws_ecr_lifecycle_policy" "policies" {
  for_each = toset(var.ecr_repositories)

  repository = aws_ecr_repository.repositories[each.value].name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "staging", "production"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Remove untagged images after ${var.ecr_lifecycle_policy_days} days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.ecr_lifecycle_policy_days
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ============================================
# Data Sources
# ============================================
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
