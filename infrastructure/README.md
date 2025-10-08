# Infrastructure

AWS infrastructure for Market Pulse ECS Fargate cron jobs.

## Quick Start

```bash
# 1. Configure variables
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
vim terraform.tfvars  # Fill in your AWS values

# 2. Initialize Terraform
make tf-init

# 3. Preview changes
make tf-plan

# 4. Deploy infrastructure
make tf-apply
```

## What Gets Created

- **ECR Repository**: `market-pulse-jobs` (container registry)
- **ECS Cluster**: `market-pulse-jobs`
- **Task Definitions**: 3 tasks (scraper, sentiment, status)
- **EventBridge Schedules**: 3 schedules (every 15 min + daily)
- **CloudWatch Log Groups**: 3 log groups with 7-day retention
- **IAM Roles**: Task execution, task runtime, EventBridge scheduler
- **SQS Queues**: 3 dead-letter queues for failed invocations
- **Security Groups**: ECS task security group with Postgres access

## Required Variables

See [terraform.tfvars.example](terraform/terraform.tfvars.example) for all variables.

**Critical values to obtain:**

```bash
# VPC ID (where your EC2/Postgres lives)
aws ec2 describe-vpcs

# Private Subnet IDs (same subnets as Postgres)
aws ec2 describe-subnets --filters "Name=vpc-id,Values=YOUR_VPC_ID"

# Postgres Security Group ID
aws ec2 describe-security-groups --filters "Name=vpc-id,Values=YOUR_VPC_ID"
```

## Terraform State Management

**Option 1: Local State (Default)**
State is stored in `infrastructure/terraform/terraform.tfstate`.

**Option 2: S3 Backend (Recommended for teams)**

Uncomment in [main.tf](terraform/main.tf):

```hcl
backend "s3" {
  bucket = "market-pulse-terraform-state"
  key    = "ecs-jobs/terraform.tfstate"
  region = "us-east-1"
}
```

Then create the S3 bucket:

```bash
aws s3api create-bucket \
  --bucket market-pulse-terraform-state \
  --region us-east-1

aws s3api put-bucket-versioning \
  --bucket market-pulse-terraform-state \
  --versioning-configuration Status=Enabled
```

## Deployment Workflow

```mermaid
graph TD
    A[Code Change] --> B[Git Push to main]
    B --> C[GitHub Actions]
    C --> D[Build Docker Image]
    D --> E[Push to ECR]
    E --> F[Update ECS Task Definitions]
    F --> G[EventBridge Triggers Tasks]
```

## Manual Commands

See [Makefile](../Makefile) for all available commands:

```bash
# Build and deploy
make push-jobs-image          # Build and push to ECR
make tf-apply                 # Deploy infrastructure changes

# Run tasks manually
make ecs-run-scraper          # Trigger Reddit scraper
make ecs-run-sentiment        # Trigger sentiment analysis
make ecs-run-status           # Trigger status check

# View logs
make ecs-logs-scraper         # Tail scraper logs
make ecs-logs-sentiment       # Tail sentiment logs
make ecs-logs-status          # Tail status logs

# Manage schedules
make schedule-enable-all      # Enable all EventBridge schedules
make schedule-disable-all     # Disable all schedules
make schedule-status          # Check schedule status
```

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ EventBridge Scheduler                                        │
├──────────────────────────────────────────────────────────────┤
│ • reddit-scraper        (*/15 min)                           │
│ • sentiment-analysis    (*/15 min)                           │
│ • daily-status          (daily @ 4am UTC)                    │
└────────────┬─────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────┐
│ ECS Cluster: market-pulse-jobs                               │
├──────────────────────────────────────────────────────────────┤
│ • Fargate Spot (cost-optimized)                              │
│ • 0.25 vCPU, 512 MB RAM per task                             │
│ • Private subnets (same VPC as Postgres)                     │
└────────────┬─────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────┐
│ Task Definitions                                             │
├──────────────────────────────────────────────────────────────┤
│ 1. reddit-scraper        → ingest.reddit_scraper_cli        │
│ 2. sentiment-analysis    → app/jobs/analyze_sentiment.py    │
│ 3. daily-status          → reddit_scraper_cli --mode status │
└──────────────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────┐
│ PostgreSQL Database (on EC2)                                 │
└──────────────────────────────────────────────────────────────┘
```

## Secrets Management

All secrets are stored in **AWS Secrets Manager**:

```bash
# Create required secrets
aws secretsmanager create-secret \
  --name market-pulse/postgres-url \
  --secret-string "postgresql://user:pass@host:5432/db"

aws secretsmanager create-secret \
  --name market-pulse/reddit-client-id \
  --secret-string "YOUR_CLIENT_ID"

aws secretsmanager create-secret \
  --name market-pulse/reddit-client-secret \
  --secret-string "YOUR_CLIENT_SECRET"

aws secretsmanager create-secret \
  --name market-pulse/reddit-user-agent \
  --secret-string "market-pulse/1.0"
```

Secrets are injected into ECS tasks at runtime via the `secrets` field in task definitions.

## Cost Estimate

| Resource | Monthly Cost |
|----------|--------------|
| ECS Fargate Spot (0.25 vCPU, 512 MB) | $1-2 |
| CloudWatch Logs (7-day retention) | $0.50 |
| Secrets Manager (4 secrets) | $1.60 |
| EventBridge Scheduler | < $0.01 |
| SQS (DLQs) | < $0.01 |
| **Total** | **~$3-4/month** |

Compare to EC2 overhead for cron jobs: **$30-60/month** → **~90% savings**

## Troubleshooting

### Tasks Not Starting

```bash
# Check task stopped reason
aws ecs describe-tasks \
  --cluster market-pulse-jobs \
  --tasks $(aws ecs list-tasks --cluster market-pulse-jobs --query 'taskArns[0]' --output text) \
  --query 'tasks[0].stoppedReason'
```

Common issues:
- Missing IAM permissions
- Invalid secrets ARN
- ECR image not found
- Network connectivity (security groups)

### Database Connection Errors

```bash
# Verify security group rules
aws ec2 describe-security-group-rules \
  --filters Name=group-id,Values=YOUR_POSTGRES_SG_ID

# Test Secrets Manager values
aws secretsmanager get-secret-value \
  --secret-id market-pulse/postgres-url \
  --query SecretString --output text
```

### High Costs

```bash
# Check task usage
aws ecs describe-clusters --clusters market-pulse-jobs

# Verify Spot usage (should be FARGATE_SPOT, not FARGATE)
aws ecs describe-tasks \
  --cluster market-pulse-jobs \
  --tasks $(aws ecs list-tasks --cluster market-pulse-jobs --query 'taskArns[0]' --output text) \
  --query 'tasks[0].capacityProviderName'
```

## Updating Infrastructure

```bash
# Make changes to .tf files
vim infrastructure/terraform/ecs.tf

# Preview changes
make tf-plan

# Apply changes
make tf-apply
```

## Destroying Infrastructure

⚠️ **Use with caution**

```bash
# Disable schedules first
make schedule-disable-all

# Destroy all resources
make tf-destroy

# Confirm with "yes"
```

## Further Reading

- [ECS Migration Guide](../docs/ECS_MIGRATION_GUIDE.md) - Complete migration walkthrough
- [Makefile](../Makefile) - All available commands
- [Terraform Docs](https://www.terraform.io/docs)
