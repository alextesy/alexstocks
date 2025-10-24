# ECS Cluster for job tasks
resource "aws_ecs_cluster" "jobs" {
  name = "${var.project_name}-jobs"

  setting {
    name  = "containerInsights"
    value = "disabled"
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-jobs-cluster"
  })
}

# Attach Fargate capacity providers to cluster
resource "aws_ecs_cluster_capacity_providers" "jobs" {
  cluster_name = aws_ecs_cluster.jobs.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 1
    base              = 0
  }
}

# Security Group for ECS tasks
resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-tasks"
  description = "Security group for ECS job tasks"
  vpc_id      = var.vpc_id

  # Allow outbound traffic (for pulling images, accessing APIs, etc.)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-ecs-tasks-sg"
  })
}

# Allow ECS tasks to connect to Postgres
resource "aws_security_group_rule" "ecs_to_postgres" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs_tasks.id
  security_group_id        = var.postgres_security_group_id
  description              = "Allow ECS tasks to connect to Postgres"
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "reddit_scraper" {
  name              = "/ecs/${var.project_name}-jobs/reddit-scraper"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "sentiment_analysis" {
  name              = "/ecs/${var.project_name}-jobs/sentiment-analysis"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "daily_status" {
  name              = "/ecs/${var.project_name}-jobs/daily-status"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "stock_price_collector" {
  name              = "/ecs/${var.project_name}-jobs/stock-price-collector"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

# ECS Task Definition: Reddit Scraper
resource "aws_ecs_task_definition" "reddit_scraper" {
  family                   = "${var.project_name}-reddit-scraper"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "reddit-scraper"
    image     = "${local.ecr_repository_url}:${var.ecr_image_tag}"
    essential = true

    command = [
      "python", "-m", "ingest.reddit_scraper_cli",
      "--mode", "incremental"
    ]

    environment = [
      {
        name  = "ENVIRONMENT"
        value = var.environment
      }
    ]

    secrets = [
      {
        name      = "POSTGRES_URL"
        valueFrom = data.aws_secretsmanager_secret.postgres_url.arn
      },
      {
        name      = "REDDIT_CLIENT_ID"
        valueFrom = data.aws_secretsmanager_secret.reddit_client_id.arn
      },
      {
        name      = "REDDIT_CLIENT_SECRET"
        valueFrom = data.aws_secretsmanager_secret.reddit_client_secret.arn
      },
      {
        name      = "REDDIT_USER_AGENT"
        valueFrom = data.aws_secretsmanager_secret.reddit_user_agent.arn
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.reddit_scraper.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    stopTimeout = 120
  }])

  tags = local.common_tags
}

# ECS Task Definition: Sentiment Analysis
resource "aws_ecs_task_definition" "sentiment_analysis" {
  family                   = "${var.project_name}-sentiment-analysis"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.sentiment_task_cpu
  memory                   = var.sentiment_task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "sentiment-analysis"
    image     = "${local.ecr_repository_url}:${var.ecr_image_tag}"
    essential = true

    command = [
      "python", "jobs/analyze_sentiment.py",
      "--source", "reddit",
      "--max-workers", "2"
    ]

    environment = [
      {
        name  = "ENVIRONMENT"
        value = var.environment
      }
    ]

    secrets = [
      {
        name      = "POSTGRES_URL"
        valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${local.account_id}:secret:${var.project_name}/postgres-url"
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.sentiment_analysis.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    stopTimeout = 120
  }])

  tags = local.common_tags
}

# ECS Task Definition: Daily Status Check
resource "aws_ecs_task_definition" "daily_status" {
  family                   = "${var.project_name}-daily-status"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "daily-status"
    image     = "${local.ecr_repository_url}:${var.ecr_image_tag}"
    essential = true

    command = [
      "python", "-m", "ingest.reddit_scraper_cli",
      "--mode", "status"
    ]

    environment = [
      {
        name  = "ENVIRONMENT"
        value = var.environment
      }
    ]

    secrets = [
      {
        name      = "POSTGRES_URL"
        valueFrom = data.aws_secretsmanager_secret.postgres_url.arn
      },
      {
        name      = "REDDIT_CLIENT_ID"
        valueFrom = data.aws_secretsmanager_secret.reddit_client_id.arn
      },
      {
        name      = "REDDIT_CLIENT_SECRET"
        valueFrom = data.aws_secretsmanager_secret.reddit_client_secret.arn
      },
      {
        name      = "REDDIT_USER_AGENT"
        valueFrom = data.aws_secretsmanager_secret.reddit_user_agent.arn
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.daily_status.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    stopTimeout = 60
  }])

  tags = local.common_tags
}

# ECS Task Definition: Stock Price Collector
resource "aws_ecs_task_definition" "stock_price_collector" {
  family                   = "${var.project_name}-stock-price-collector"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "stock-price-collector"
    image     = "${local.ecr_repository_url}:${var.ecr_image_tag}"
    essential = true

    command = [
      "python", "jobs/stock_price_collector.py"
    ]

    environment = [
      {
        name  = "ENVIRONMENT"
        value = var.environment
      }
    ]

    secrets = [
      {
        name      = "POSTGRES_URL"
        valueFrom = data.aws_secretsmanager_secret.postgres_url.arn
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.stock_price_collector.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    stopTimeout = 60
  }])

  tags = local.common_tags
}

# Outputs
output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.jobs.name
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.jobs.arn
}

output "reddit_scraper_task_definition_arn" {
  description = "Reddit scraper task definition ARN"
  value       = aws_ecs_task_definition.reddit_scraper.arn
}

output "sentiment_analysis_task_definition_arn" {
  description = "Sentiment analysis task definition ARN"
  value       = aws_ecs_task_definition.sentiment_analysis.arn
}

output "daily_status_task_definition_arn" {
  description = "Daily status task definition ARN"
  value       = aws_ecs_task_definition.daily_status.arn
}

output "stock_price_collector_task_definition_arn" {
  description = "Stock price collector task definition ARN"
  value       = aws_ecs_task_definition.stock_price_collector.arn
}
