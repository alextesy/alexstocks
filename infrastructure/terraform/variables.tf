variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "market-pulse"
}

variable "environment" {
  description = "Environment (staging/production)"
  type        = string
  default     = "production"
}

variable "vpc_id" {
  description = "VPC ID where ECS tasks will run (same as EC2/Postgres)"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for ECS tasks"
  type        = list(string)
}

variable "postgres_security_group_id" {
  description = "Security group ID for Postgres access"
  type        = string
}

variable "ecr_image_tag" {
  description = "ECR image tag to use"
  type        = string
  default     = "latest"
}

variable "task_cpu" {
  description = "Task CPU units (256 = 0.25 vCPU)"
  type        = number
  default     = 256
}

variable "task_memory" {
  description = "Task memory in MB"
  type        = number
  default     = 512
}

variable "sentiment_task_cpu" {
  description = "Sentiment analysis task CPU units (1024 = 1 vCPU)"
  type        = number
  default     = 1024
}

variable "sentiment_task_memory" {
  description = "Sentiment analysis task memory in MB (needs more for PyTorch models)"
  type        = number
  default     = 4096
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 3
}
