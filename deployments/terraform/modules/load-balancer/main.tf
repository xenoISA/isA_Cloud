# ============================================
# Load Balancer Module
# ============================================
# Application Load Balancer with HTTP/HTTPS listeners,
# default target group, and optional SSL termination.

# ============================================
# Application Load Balancer
# ============================================
resource "aws_lb" "main" {
  name               = "${var.project_name}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  idle_timeout                     = var.idle_timeout
  enable_deletion_protection       = var.enable_deletion_protection
  enable_cross_zone_load_balancing = true

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-alb"
    Environment = var.environment
  })
}

# ============================================
# Default Target Group
# ============================================
resource "aws_lb_target_group" "default" {
  name        = "${var.project_name}-${var.environment}-default-tg"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    path                = var.health_check_path
    port                = "traffic-port"
    protocol            = "HTTP"
    interval            = var.health_check_interval
    timeout             = var.health_check_timeout
    healthy_threshold   = var.healthy_threshold
    unhealthy_threshold = var.unhealthy_threshold
    matcher             = "200-299"
  }

  deregistration_delay = 30

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-default-tg"
    Environment = var.environment
  })

  lifecycle {
    create_before_destroy = true
  }
}

# ============================================
# HTTP Listener
# ============================================
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  # If HTTPS is configured, redirect HTTP to HTTPS
  # Otherwise, forward to default target group
  dynamic "default_action" {
    for_each = var.certificate_arn != "" ? [1] : []
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }

  dynamic "default_action" {
    for_each = var.certificate_arn == "" ? [1] : []
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.default.arn
    }
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-http-listener"
  })
}

# ============================================
# HTTPS Listener (optional - only if certificate provided)
# ============================================
resource "aws_lb_listener" "https" {
  count = var.certificate_arn != "" ? 1 : 0

  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.default.arn
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-https-listener"
  })
}
