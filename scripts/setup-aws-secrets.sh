#!/bin/bash
set -e

# Setup AWS Secrets Manager secrets for Market Pulse ECS jobs
# This script creates the required secrets in AWS Secrets Manager

echo "🔐 Setting up AWS Secrets Manager secrets for Market Pulse"
echo "==========================================================="
echo ""

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ Error: AWS CLI is not configured or credentials are invalid"
    echo "Run: aws configure"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_REGION:-us-east-1}

echo "✅ AWS Account: $ACCOUNT_ID"
echo "✅ Region: $REGION"
echo ""

# Function to create or update secret
create_or_update_secret() {
    local SECRET_NAME=$1
    local SECRET_VALUE=$2

    if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$REGION" &> /dev/null; then
        echo "🔄 Updating existing secret: $SECRET_NAME"
        aws secretsmanager put-secret-value \
            --secret-id "$SECRET_NAME" \
            --secret-string "$SECRET_VALUE" \
            --region "$REGION" > /dev/null
    else
        echo "✨ Creating new secret: $SECRET_NAME"
        aws secretsmanager create-secret \
            --name "$SECRET_NAME" \
            --secret-string "$SECRET_VALUE" \
            --region "$REGION" > /dev/null
    fi
}

# Load .env if it exists (safely parse only valid variables)
if [ -f .env ]; then
    echo "📁 Loading values from .env file..."
    # Only load lines that look like VAR=value
    set -a
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ $key =~ ^#.*$ ]] && continue
        [[ -z $key ]] && continue
        # Only export if it looks like a valid variable name
        if [[ $key =~ ^[A-Z_][A-Z0-9_]*$ ]]; then
            export "$key=$value"
        fi
    done < .env
    set +a
else
    echo "⚠️  No .env file found. You'll need to enter values manually."
fi

echo ""
echo "Please provide the following values:"
echo "====================================="

# Postgres URL
if [ -z "$POSTGRES_URL" ]; then
    read -p "Postgres URL (postgresql://user:pass@host:5432/db): " POSTGRES_URL
fi
echo "Postgres URL: ${POSTGRES_URL:0:30}..." # Show only first 30 chars for security

# Reddit Client ID
if [ -z "$REDDIT_CLIENT_ID" ]; then
    read -p "Reddit Client ID: " REDDIT_CLIENT_ID
fi
echo "Reddit Client ID: ${REDDIT_CLIENT_ID:0:10}..."

# Reddit Client Secret
if [ -z "$REDDIT_CLIENT_SECRET" ]; then
    read -s -p "Reddit Client Secret: " REDDIT_CLIENT_SECRET
    echo ""
fi
echo "Reddit Client Secret: [hidden]"

# Reddit User Agent
if [ -z "$REDDIT_USER_AGENT" ]; then
    read -p "Reddit User Agent (default: market-pulse/1.0): " REDDIT_USER_AGENT
    REDDIT_USER_AGENT=${REDDIT_USER_AGENT:-market-pulse/1.0}
fi
echo "Reddit User Agent: $REDDIT_USER_AGENT"

echo ""
echo "Creating secrets in AWS Secrets Manager..."
echo "==========================================="

# Create all secrets
create_or_update_secret "market-pulse/postgres-url" "$POSTGRES_URL"
create_or_update_secret "market-pulse/reddit-client-id" "$REDDIT_CLIENT_ID"
create_or_update_secret "market-pulse/reddit-client-secret" "$REDDIT_CLIENT_SECRET"
create_or_update_secret "market-pulse/reddit-user-agent" "$REDDIT_USER_AGENT"

echo ""
echo "✅ All secrets created successfully!"
echo ""
echo "Next steps:"
echo "1. Configure terraform.tfvars with your VPC/subnet/security group IDs"
echo "2. Run: make tf-init"
echo "3. Run: make tf-plan"
echo "4. Run: make tf-apply"
echo ""
echo "See docs/ECS_MIGRATION_GUIDE.md for detailed instructions."
