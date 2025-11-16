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

data "aws_secretsmanager_secret" "slack_bot_token" {
  name = "${var.project_name}/slack-bot-token"
}

data "aws_secretsmanager_secret" "slack_default_channel" {
  name = "${var.project_name}/slack-default-channel"
}

data "aws_secretsmanager_secret" "slack_users_channel" {
  name = "${var.project_name}/slack-users-channel"
}

data "aws_secretsmanager_secret" "slack_reddit_channel" {
  name = "${var.project_name}/slack-reddit-channel"
}

data "aws_secretsmanager_secret" "openai_api_key" {
  name = "${var.project_name}/openai-api-key"
}

data "aws_secretsmanager_secret" "email_from_address" {
  name = "${var.project_name}/email-from-address"
}

data "aws_secretsmanager_secret" "aws_ses_region" {
  name = "${var.project_name}/aws-ses-region"
}

data "aws_secretsmanager_secret" "test_email_recipient" {
  name = "${var.project_name}/test-email-recipient"
}
