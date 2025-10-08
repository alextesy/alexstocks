# Data sources to get the actual secret ARNs (with random suffixes)
data "aws_secretsmanager_secret" "postgres_url" {
  name = "${var.project_name}/postgres-url"
}

data "aws_secretsmanager_secret" "reddit_client_id" {
  name = "${var.project_name}/reddit-client-id"
}

data "aws_secretsmanager_secret" "reddit_client_secret" {
  name = "${var.project_name}/reddit-client-secret"
}

data "aws_secretsmanager_secret" "reddit_user_agent" {
  name = "${var.project_name}/reddit-user-agent"
}
