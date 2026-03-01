# ============================================
# ECS Service Module
# ============================================
# Reusable ECS Fargate service with task definition,
# IAM roles, optional ALB target group, EFS volumes,
# service discovery, and auto-scaling.

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# ============================================
# IAM - Task Execution Role
# ============================================
resource "aws_iam_role" "execution" {
  name_prefix = "${var.project_name}-${var.environment}-${var.service_name}-exec-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-${var.service_name}-exec"
    Environment = var.environment
    Service     = var.service_name
  })
}

resource "aws_iam_role_policy_attachment" "execution_base" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy_attachment" "execution_secrets" {
  count = var.secrets_read_policy_arn != "" ? 1 : 0

  role       = aws_iam_role.execution.name
  policy_arn = var.secrets_read_policy_arn
}

# ============================================
# IAM - Task Role
# ============================================
resource "aws_iam_role" "task" {
  name_prefix = "${var.project_name}-${var.environment}-${var.service_name}-task-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-${var.service_name}-task"
    Environment = var.environment
    Service     = var.service_name
  })
}

# Allow ECS Exec for debugging
resource "aws_iam_role_policy" "task_exec" {
  name = "ecs-exec"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ssmmessages:CreateControlChannel",
        "ssmmessages:CreateDataChannel",
        "ssmmessages:OpenControlChannel",
        "ssmmessages:OpenDataChannel"
      ]
      Resource = "*"
    }]
  })
}

# ============================================
# Task Definition
# ============================================
resource "aws_ecs_task_definition" "main" {
  family                   = "${var.project_name}-${var.environment}-${var.service_name}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = var.service_name
    image     = var.container_image
    essential = true

    portMappings = [{
      containerPort = var.container_port
      protocol      = "tcp"
    }]

    environment = var.environment_variables
    secrets     = var.secrets

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = var.log_group_name
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = var.service_name
      }
    }

    mountPoints = var.efs_file_system_id != "" ? [{
      sourceVolume  = "efs-storage"
      containerPath = var.efs_mount_path
      readOnly      = false
    }] : []
  }])

  dynamic "volume" {
    for_each = var.efs_file_system_id != "" ? [1] : []
    content {
      name = "efs-storage"
      efs_volume_configuration {
        file_system_id     = var.efs_file_system_id
        transit_encryption = "ENABLED"

        dynamic "authorization_config" {
          for_each = var.efs_access_point_id != "" ? [1] : []
          content {
            access_point_id = var.efs_access_point_id
            iam             = "ENABLED"
          }
        }
      }
    }
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-${var.service_name}"
    Environment = var.environment
    Service     = var.service_name
  })
}

# ============================================
# Service Discovery (optional)
# ============================================
resource "aws_service_discovery_service" "main" {
  count = var.cloud_map_namespace_id != "" ? 1 : 0

  name = var.service_name

  dns_config {
    namespace_id = var.cloud_map_namespace_id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# ============================================
# ECS Service
# ============================================
resource "aws_ecs_service" "main" {
  name            = "${var.project_name}-${var.environment}-${var.service_name}"
  cluster         = var.cluster_id
  task_definition = aws_ecs_task_definition.main.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  enable_execute_command = true

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.security_group_id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = var.target_group_arn != "" ? [1] : []
    content {
      target_group_arn = var.target_group_arn
      container_name   = var.service_name
      container_port   = var.container_port
    }
  }

  dynamic "service_registries" {
    for_each = var.cloud_map_namespace_id != "" ? [1] : []
    content {
      registry_arn = aws_service_discovery_service.main[0].arn
    }
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-${var.service_name}"
    Environment = var.environment
    Service     = var.service_name
  })

  lifecycle {
    ignore_changes = [desired_count]
  }
}

# ============================================
# Auto Scaling (optional)
# ============================================
resource "aws_appautoscaling_target" "main" {
  count = var.enable_autoscaling ? 1 : 0

  max_capacity       = var.max_capacity
  min_capacity       = var.min_capacity
  resource_id        = "service/${var.cluster_name}/${aws_ecs_service.main.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "cpu" {
  count = var.enable_autoscaling ? 1 : 0

  name               = "${var.project_name}-${var.environment}-${var.service_name}-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.main[0].resource_id
  scalable_dimension = aws_appautoscaling_target.main[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.main[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = var.cpu_target_value
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
