# EventBridge Scheduler: Reddit Scraper (every 15 minutes)
resource "aws_scheduler_schedule" "reddit_scraper" {
  name       = "${var.project_name}-reddit-scraper"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(15 minutes)"

  target {
    arn      = aws_ecs_cluster.jobs.arn
    role_arn = aws_iam_role.eventbridge_scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.reddit_scraper.arn
      platform_version    = "LATEST"

      network_configuration {
        subnets          = var.private_subnet_ids
        security_groups  = [aws_security_group.ecs_tasks.id]
        assign_public_ip = true  # Set to true for public subnets (no NAT Gateway)
      }

      # Enable Fargate Spot for cost savings
      capacity_provider_strategy {
        capacity_provider = "FARGATE_SPOT"
        weight            = 1
        base              = 0
      }
    }

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }

    dead_letter_config {
      arn = aws_sqs_queue.reddit_scraper_dlq.arn
    }
  }

  description = "Run Reddit scraper every 15 minutes"
}

# EventBridge Scheduler: Sentiment Analysis (every 15 minutes)
resource "aws_scheduler_schedule" "sentiment_analysis" {
  name       = "${var.project_name}-sentiment-analysis"
  group_name = "default"
  state      = "DISABLED"  # Disabled - now triggered by Reddit scraper completion event

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(15 minutes)"

  target {
    arn      = aws_ecs_cluster.jobs.arn
    role_arn = aws_iam_role.eventbridge_scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.sentiment_analysis.arn
      platform_version    = "LATEST"

      network_configuration {
        subnets          = var.private_subnet_ids
        security_groups  = [aws_security_group.ecs_tasks.id]
        assign_public_ip = true  # Set to true for public subnets (no NAT Gateway)
      }

      # Enable Fargate Spot for cost savings
      capacity_provider_strategy {
        capacity_provider = "FARGATE_SPOT"
        weight            = 1
        base              = 0
      }
    }

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }

    dead_letter_config {
      arn = aws_sqs_queue.sentiment_analysis_dlq.arn
    }
  }

  description = "Run sentiment analysis every 15 minutes"
}

# EventBridge Scheduler: Daily Status (daily at 4:00 UTC)
resource "aws_scheduler_schedule" "daily_status" {
  name       = "${var.project_name}-daily-status"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "cron(0 4 * * ? *)"

  target {
    arn      = aws_ecs_cluster.jobs.arn
    role_arn = aws_iam_role.eventbridge_scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.daily_status.arn
      platform_version    = "LATEST"

      network_configuration {
        subnets          = var.private_subnet_ids
        security_groups  = [aws_security_group.ecs_tasks.id]
        assign_public_ip = true  # Set to true for public subnets (no NAT Gateway)
      }

      # Enable Fargate Spot for cost savings
      capacity_provider_strategy {
        capacity_provider = "FARGATE_SPOT"
        weight            = 1
        base              = 0
      }
    }

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }

    dead_letter_config {
      arn = aws_sqs_queue.daily_status_dlq.arn
    }
  }

  description = "Run daily status check at 4:00 UTC"
}

# Dead Letter Queues for failed task invocations
resource "aws_sqs_queue" "reddit_scraper_dlq" {
  name                      = "${var.project_name}-reddit-scraper-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = local.common_tags
}

resource "aws_sqs_queue" "sentiment_analysis_dlq" {
  name                      = "${var.project_name}-sentiment-analysis-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = local.common_tags
}

resource "aws_sqs_queue" "daily_status_dlq" {
  name                      = "${var.project_name}-daily-status-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = local.common_tags
}

# IAM policy to allow EventBridge to send messages to SQS DLQs
resource "aws_sqs_queue_policy" "reddit_scraper_dlq" {
  queue_url = aws_sqs_queue.reddit_scraper_dlq.url

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "scheduler.amazonaws.com"
      }
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.reddit_scraper_dlq.arn
    }]
  })
}

resource "aws_sqs_queue_policy" "sentiment_analysis_dlq" {
  queue_url = aws_sqs_queue.sentiment_analysis_dlq.url

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "scheduler.amazonaws.com"
      }
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.sentiment_analysis_dlq.arn
    }]
  })
}

resource "aws_sqs_queue_policy" "daily_status_dlq" {
  queue_url = aws_sqs_queue.daily_status_dlq.url

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "scheduler.amazonaws.com"
      }
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.daily_status_dlq.arn
    }]
  })
}

# Outputs
output "reddit_scraper_schedule_name" {
  description = "Reddit scraper schedule name"
  value       = aws_scheduler_schedule.reddit_scraper.name
}

output "sentiment_analysis_schedule_name" {
  description = "Sentiment analysis schedule name"
  value       = aws_scheduler_schedule.sentiment_analysis.name
}

output "daily_status_schedule_name" {
  description = "Daily status schedule name"
  value       = aws_scheduler_schedule.daily_status.name
}
