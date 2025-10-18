# Task Chaining: Trigger sentiment analysis when Reddit scraper completes

# EventBridge Rule: Detect when Reddit scraper task completes successfully
resource "aws_cloudwatch_event_rule" "reddit_scraper_completed" {
  name        = "${var.project_name}-reddit-scraper-completed"
  description = "Trigger sentiment analysis when Reddit scraper completes successfully"

  event_pattern = jsonencode({
    source      = ["aws.ecs"]
    detail-type = ["ECS Task State Change"]
    detail = {
      clusterArn = [aws_ecs_cluster.jobs.arn]
      lastStatus = ["STOPPED"]
      taskDefinitionArn = [{
        prefix = "${aws_ecs_task_definition.reddit_scraper.arn_without_revision}:"
      }]
      stopCode = ["EssentialContainerExited"]
      containers = {
        exitCode = [0] # Only trigger on successful completion (exit code 0)
      }
    }
  })

  tags = local.common_tags
}

# EventBridge Target: Launch sentiment analysis task
resource "aws_cloudwatch_event_target" "trigger_sentiment" {
  rule      = aws_cloudwatch_event_rule.reddit_scraper_completed.name
  target_id = "TriggerSentimentAnalysis"
  arn       = aws_ecs_cluster.jobs.arn
  role_arn  = aws_iam_role.eventbridge_ecs.arn

  ecs_target {
    task_definition_arn = aws_ecs_task_definition.sentiment_analysis.arn
    platform_version    = "LATEST"

    network_configuration {
      subnets          = var.private_subnet_ids
      security_groups  = [aws_security_group.ecs_tasks.id]
      assign_public_ip = true
    }

    capacity_provider_strategy {
      capacity_provider = "FARGATE_SPOT"
      weight            = 1
    }
  }
}

# IAM Role for EventBridge to trigger ECS tasks (task chaining)
resource "aws_iam_role" "eventbridge_ecs" {
  name = "${var.project_name}-eventbridge-ecs"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
    }]
  })

  tags = local.common_tags
}

# IAM Policy: Allow EventBridge to run ECS tasks
resource "aws_iam_role_policy" "eventbridge_ecs_run_task" {
  name = "${var.project_name}-eventbridge-ecs-run-task"
  role = aws_iam_role.eventbridge_ecs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "ecs:RunTask"
        Resource = [
          aws_ecs_task_definition.sentiment_analysis.arn_without_revision,
          "${aws_ecs_task_definition.sentiment_analysis.arn_without_revision}:*"
        ]
      },
      {
        Effect = "Allow"
        Action = "iam:PassRole"
        Resource = [
          aws_iam_role.ecs_task_execution.arn,
          aws_iam_role.ecs_task.arn
        ]
      }
    ]
  })
}
