# ============================================
# Load Balancer Module - Outputs
# ============================================

output "alb_id" {
  description = "ALB ID"
  value       = aws_lb.main.id
}

output "alb_arn" {
  description = "ALB ARN"
  value       = aws_lb.main.arn
}

output "alb_dns_name" {
  description = "ALB DNS name"
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "ALB hosted zone ID for Route53 alias records"
  value       = aws_lb.main.zone_id
}

output "default_target_group_arn" {
  description = "Default target group ARN"
  value       = aws_lb_target_group.default.arn
}

output "http_listener_arn" {
  description = "HTTP listener ARN"
  value       = aws_lb_listener.http.arn
}

output "https_listener_arn" {
  description = "HTTPS listener ARN (empty if no certificate)"
  value       = length(aws_lb_listener.https) > 0 ? aws_lb_listener.https[0].arn : ""
}
