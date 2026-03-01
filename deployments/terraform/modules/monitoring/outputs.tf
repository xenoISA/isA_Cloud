# ============================================
# Monitoring Module - Outputs
# ============================================

output "log_group_name" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.ecs.name
}

output "log_group_arn" {
  description = "CloudWatch log group ARN"
  value       = aws_cloudwatch_log_group.ecs.arn
}

output "sns_topic_arn" {
  description = "SNS topic ARN for alarm notifications"
  value       = length(aws_sns_topic.alarms) > 0 ? aws_sns_topic.alarms[0].arn : ""
}

output "dashboard_name" {
  description = "CloudWatch dashboard name"
  value       = length(aws_cloudwatch_dashboard.main) > 0 ? aws_cloudwatch_dashboard.main[0].dashboard_name : ""
}

output "cpu_alarm_arn" {
  description = "CPU high alarm ARN"
  value       = length(aws_cloudwatch_metric_alarm.cpu_high) > 0 ? aws_cloudwatch_metric_alarm.cpu_high[0].arn : ""
}

output "memory_alarm_arn" {
  description = "Memory high alarm ARN"
  value       = length(aws_cloudwatch_metric_alarm.memory_high) > 0 ? aws_cloudwatch_metric_alarm.memory_high[0].arn : ""
}
