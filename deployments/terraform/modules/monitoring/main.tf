# ============================================
# Monitoring Module
# ============================================
# CloudWatch log groups, alarms, SNS notifications,
# and optional dashboard for ECS cluster monitoring.

data "aws_region" "current" {}

# ============================================
# CloudWatch Log Group
# ============================================
resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.project_name}-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-ecs-logs"
    Environment = var.environment
  })
}

# ============================================
# SNS Topic for Alarm Notifications
# ============================================
resource "aws_sns_topic" "alarms" {
  count = var.enable_alarms ? 1 : 0

  name = "${var.project_name}-${var.environment}-alarms"

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-alarms"
    Environment = var.environment
  })
}

resource "aws_sns_topic_subscription" "email" {
  count = var.enable_alarms ? length(var.alarm_email_endpoints) : 0

  topic_arn = aws_sns_topic.alarms[0].arn
  protocol  = "email"
  endpoint  = var.alarm_email_endpoints[count.index]
}

# ============================================
# CloudWatch Alarms - ECS Cluster
# ============================================
resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-cpu-high"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = var.alarm_evaluation_periods
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = var.alarm_period
  statistic           = "Average"
  threshold           = var.cpu_alarm_threshold
  alarm_description   = "ECS cluster CPU utilization above ${var.cpu_alarm_threshold}%"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = var.cluster_name
  }

  alarm_actions = [aws_sns_topic.alarms[0].arn]
  ok_actions    = [aws_sns_topic.alarms[0].arn]

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-cpu-high"
    Environment = var.environment
  })
}

resource "aws_cloudwatch_metric_alarm" "memory_high" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-memory-high"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = var.alarm_evaluation_periods
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = var.alarm_period
  statistic           = "Average"
  threshold           = var.memory_alarm_threshold
  alarm_description   = "ECS cluster memory utilization above ${var.memory_alarm_threshold}%"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = var.cluster_name
  }

  alarm_actions = [aws_sns_topic.alarms[0].arn]
  ok_actions    = [aws_sns_topic.alarms[0].arn]

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-memory-high"
    Environment = var.environment
  })
}

# ============================================
# CloudWatch Dashboard (optional)
# ============================================
resource "aws_cloudwatch_dashboard" "main" {
  count = var.enable_dashboard ? 1 : 0

  dashboard_name = "${var.project_name}-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "ECS CPU Utilization"
          metrics = [["AWS/ECS", "CPUUtilization", "ClusterName", var.cluster_name]]
          period  = 300
          stat    = "Average"
          region  = data.aws_region.current.name
          view    = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "ECS Memory Utilization"
          metrics = [["AWS/ECS", "MemoryUtilization", "ClusterName", var.cluster_name]]
          period  = 300
          stat    = "Average"
          region  = data.aws_region.current.name
          view    = "timeSeries"
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 6
        width  = 24
        height = 6
        properties = {
          title  = "ECS Application Logs"
          query  = "SOURCE '${aws_cloudwatch_log_group.ecs.name}' | fields @timestamp, @message | sort @timestamp desc | limit 50"
          region = data.aws_region.current.name
          view   = "table"
        }
      }
    ]
  })
}
