# ECS Fargate Migration Guide

Complete guide for migrating Market Pulse cron jobs from EC2 to AWS ECS Fargate (Spot).

## 📋 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Initial Setup](#initial-setup)
5. [Deployment Steps](#deployment-steps)
6. [Testing & Validation](#testing--validation)
7. [Production Cutover](#production-cutover)
8. [Monitoring & Operations](#monitoring--operations)
9. [Troubleshooting](#troubleshooting)
10. [Rollback Plan](#rollback-plan)

---

## Overview

### Current State (EC2)

All cron jobs run directly on the EC2 instance:
- **Reddit Scraper**: Every 15 minutes
- **Sentiment Analysis**: Every 15 minutes
- **Daily Status**: Daily at 4:00 UTC

### Target State (ECS Fargate)

Isolated containerized tasks running on-demand:
- **ECS Cluster**: `market-pulse-jobs`
- **Task Definitions**: 3 separate definitions
- **EventBridge Schedules**: Trigger tasks at specified intervals
- **Cost**: ~$1-2/month (vs $30-60/month EC2 overhead)

### Benefits

✅ **Lower Cost**: Pay only for task runtime (~5-10 min/hour)
✅ **Isolated Workloads**: No resource contention with webserver
✅ **Easy Deploys**: Update via GitHub Actions + ECR
✅ **Better Monitoring**: CloudWatch logs per job
✅ **Automatic Retries**: EventBridge handles retry logic

---

## Architecture

```
EventBridge Scheduler
 ├── reddit-scrape-incremental (*/15 minutes)
 │    └── ECS Fargate Spot → ingest.reddit_scraper_cli
 ├── sentiment-analysis-reddit (*/15 minutes)
 │    └── ECS Fargate Spot → app/jobs/analyze_sentiment.py
 └── daily-status (0 4 * daily)
      └── ECS Fargate Spot → reddit_scraper_cli --mode status

Components:
├── ECR Repository (market-pulse-jobs)
├── ECS Cluster (market-pulse-jobs)
├── ECS Task Definitions (3x)
├── EventBridge Schedules (3x)
├── CloudWatch Log Groups (3x)
├── SQS Dead Letter Queues (3x)
└── IAM Roles (Execution + Task + Scheduler)
```

---

## Prerequisites

### 1. AWS CLI Configuration

```bash
# Verify AWS CLI is installed and configured
aws --version
aws sts get-caller-identity

# Should show your AWS account ID and region
```

### 2. Terraform Installation

```bash
# Install Terraform (macOS)
brew install terraform

# Verify installation
terraform --version  # Should be >= 1.0
```

### 3. Required AWS Information

Gather the following from your existing EC2/Postgres setup:

```bash
# VPC ID
aws ec2 describe-vpcs --query 'Vpcs[*].[VpcId,Tags[?Key==`Name`].Value|[0]]' --output table

# Private Subnet IDs (where Postgres is running)
aws ec2 describe-subnets --filters "Name=vpc-id,Values=YOUR_VPC_ID" \
  --query 'Subnets[?MapPublicIpOnLaunch==`false`].[SubnetId,AvailabilityZone,CidrBlock]' \
  --output table

# Postgres Security Group ID
aws ec2 describe-security-groups --filters "Name=vpc-id,Values=YOUR_VPC_ID" \
  --query 'SecurityGroups[*].[GroupId,GroupName,Description]' --output table
```

### 4. Create AWS Secrets Manager Secrets

Store database credentials and Reddit API keys in AWS Secrets Manager:

```bash
# Postgres URL
aws secretsmanager create-secret \
  --name market-pulse/postgres-url \
  --secret-string "postgresql://user:password@host:5432/marketpulse"

# Reddit API credentials
aws secretsmanager create-secret \
  --name market-pulse/reddit-client-id \
  --secret-string "YOUR_REDDIT_CLIENT_ID"

aws secretsmanager create-secret \
  --name market-pulse/reddit-client-secret \
  --secret-string "YOUR_REDDIT_CLIENT_SECRET"

aws secretsmanager create-secret \
  --name market-pulse/reddit-user-agent \
  --secret-string "market-pulse/1.0"
```

---

## Initial Setup

### Step 1: Configure Terraform Variables

```bash
cd infrastructure/terraform

# Copy example variables file
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
vim terraform.tfvars
```

**terraform.tfvars:**
```hcl
aws_region     = "us-east-1"
project_name   = "market-pulse"
environment    = "production"

# Fill in from Prerequisites section
vpc_id                     = "vpc-xxxxxxxxxxxxxxxxx"
private_subnet_ids         = ["subnet-xxxxxxxxxx", "subnet-yyyyyyyyyy"]
postgres_security_group_id = "sg-xxxxxxxxxxxxxxxxx"

# Task configuration (can keep defaults)
task_cpu              = 256  # 0.25 vCPU
task_memory           = 512  # 512 MB
ecr_image_tag         = "latest"
log_retention_days    = 7
```

### Step 2: Initialize Terraform

```bash
make tf-init

# Verify Terraform is ready
cd infrastructure/terraform
terraform validate
```

---

## Deployment Steps

### Phase 1: Build & Push Docker Image

```bash
# Test build locally first
make build-jobs-image

# Test run locally (optional)
docker run --rm market-pulse-jobs:local python -c "print('Container works!')"

# Login to ECR and push image
make push-jobs-image
```

### Phase 2: Deploy Infrastructure with Terraform

```bash
# Review planned changes
make tf-plan

# Apply infrastructure (creates ECS cluster, task definitions, etc.)
make tf-apply

# Confirm with "yes" when prompted
```

This creates:
- ✅ ECR Repository
- ✅ ECS Cluster
- ✅ 3 ECS Task Definitions
- ✅ 3 EventBridge Schedules (**initially DISABLED**)
- ✅ CloudWatch Log Groups
- ✅ IAM Roles & Policies
- ✅ SQS Dead Letter Queues

### Phase 3: Verify Infrastructure

```bash
# Check ECS cluster
aws ecs describe-clusters --clusters market-pulse-jobs

# Check task definitions
aws ecs list-task-definitions --family-prefix market-pulse

# Check EventBridge schedules (should be DISABLED)
make schedule-status
```

---

## Testing & Validation

### Test 1: Manual Task Execution

Run each task manually to verify they work:

```bash
# Test Reddit scraper
make ecs-run-scraper

# Wait ~2 minutes, then check logs
make ecs-logs-scraper

# Test sentiment analysis
make ecs-run-sentiment
make ecs-logs-sentiment

# Test daily status
make ecs-run-status
make ecs-logs-status
```

**Expected Output:**
- Tasks should complete successfully (exit code 0)
- CloudWatch logs should show normal execution
- Database should have new records

### Test 2: Database Verification

```bash
# Connect to your database
psql $POSTGRES_URL

# Check for recent data
SELECT COUNT(*), MAX(created_at)
FROM articles
WHERE source LIKE '%reddit%'
AND created_at > NOW() - INTERVAL '1 hour';

# Check sentiment analysis
SELECT COUNT(*)
FROM articles
WHERE sentiment IS NOT NULL
AND created_at > NOW() - INTERVAL '1 hour';
```

### Test 3: Enable ONE Schedule for Testing

```bash
# Enable only the status check (low-impact)
aws scheduler update-schedule \
  --name market-pulse-daily-status \
  --state ENABLED

# Wait for next 4:00 UTC and verify it runs
```

---

## Production Cutover

### Step 1: Disable EC2 Cron Jobs

**⚠️ DO THIS DURING A LOW-TRAFFIC WINDOW**

```bash
# SSH into EC2 instance
ssh ubuntu@your-ec2-instance

# Backup current crontab
crontab -l > ~/crontab.backup.$(date +%Y%m%d)

# Edit crontab and comment out the 3 market-pulse jobs
crontab -e

# Comment out these lines:
# */15 * * * * cd /opt/market-pulse-v2 && make reddit-scrape-incremental ...
# */15 * * * * cd /opt/market-pulse-v2 && make analyze-sentiment-reddit ...
# 0 4 * * * cd /opt/market-pulse-v2 && make reddit-scrape-status ...

# Verify crontab is updated
crontab -l
```

### Step 2: Enable ECS Schedules

```bash
# Enable all EventBridge schedules
make schedule-enable-all

# Verify they're enabled
make schedule-status
```

### Step 3: Monitor First 48 Hours

```bash
# Watch logs in real-time
make ecs-logs-scraper    # In terminal 1
make ecs-logs-sentiment  # In terminal 2

# Check running tasks
make ecs-list-tasks

# Monitor CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ClusterName,Value=market-pulse-jobs \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average
```

### Step 4: Verify Data Continuity

```bash
# Check that scraping continues without gaps
psql $POSTGRES_URL -c "
SELECT
  DATE(created_at) as date,
  COUNT(*) as articles,
  COUNT(sentiment) as with_sentiment
FROM articles
WHERE source LIKE '%reddit%'
  AND created_at > NOW() - INTERVAL '3 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
"
```

---

## Monitoring & Operations

### CloudWatch Dashboards

View logs for each job:

```bash
# Web console
open "https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups"

# CLI
make ecs-logs-scraper
make ecs-logs-sentiment
make ecs-logs-status
```

### Metric Filters & Alarms

Create CloudWatch alarms for failures:

```bash
# Create alarm for task failures
aws cloudwatch put-metric-alarm \
  --alarm-name market-pulse-ecs-task-failures \
  --alarm-description "Alert on ECS task failures" \
  --metric-name TasksStoppedReason \
  --namespace AWS/ECS \
  --statistic Sum \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1
```

### Dead Letter Queues

Check for failed task invocations:

```bash
# Check DLQ message counts
aws sqs get-queue-attributes \
  --queue-url $(aws sqs get-queue-url --queue-name market-pulse-reddit-scraper-dlq --query QueueUrl --output text) \
  --attribute-names ApproximateNumberOfMessages
```

---

## Troubleshooting

### Issue: Task Fails to Start

**Symptoms:** Task status shows `STOPPED` immediately

**Solutions:**
```bash
# Check task stopped reason
aws ecs describe-tasks \
  --cluster market-pulse-jobs \
  --tasks TASK_ARN \
  --query 'tasks[0].stoppedReason'

# Common fixes:
# 1. Missing IAM permissions
# 2. Invalid secrets ARN
# 3. Image pull failed (check ECR repository)
```

### Issue: Cannot Connect to Database

**Symptoms:** Logs show connection timeout or refused

**Solutions:**
```bash
# Verify security group allows ECS tasks
aws ec2 describe-security-group-rules \
  --filters Name=group-id,Values=YOUR_POSTGRES_SG_ID

# Verify secrets are correct
aws secretsmanager get-secret-value \
  --secret-id market-pulse/postgres-url \
  --query SecretString --output text
```

### Issue: High Costs

**Check Fargate Spot vs On-Demand usage:**

```bash
# View ECS cost breakdown
aws ce get-cost-and-usage \
  --time-period Start=2025-10-01,End=2025-10-08 \
  --granularity DAILY \
  --metrics BlendedCost \
  --filter file://ecs-filter.json
```

---

## Rollback Plan

### Emergency Rollback (< 5 minutes)

If ECS tasks are failing:

```bash
# Step 1: Disable ECS schedules immediately
make schedule-disable-all

# Step 2: Re-enable EC2 cron jobs
ssh ubuntu@ec2-instance
crontab -e  # Uncomment the 3 lines

# Step 3: Verify cron jobs are running
tail -f /var/log/market-pulse/reddit-scraping.log
```

### Full Rollback (Remove ECS Infrastructure)

```bash
# Destroy all ECS resources
make tf-destroy

# Confirm with "yes"
```

---

## Post-Migration Cleanup

After 1-2 weeks of successful ECS operation:

### 1. Remove Old Cron Jobs from EC2

```bash
ssh ubuntu@ec2-instance

# Remove crontab entries permanently
crontab -e  # Delete the 3 commented lines

# Clean up old logs
sudo rm -rf /var/log/market-pulse/*.log
```

### 2. Downsize EC2 Instance

```bash
# Stop instance
aws ec2 stop-instances --instance-ids i-xxxxxxxxx

# Change instance type to smaller size
aws ec2 modify-instance-attribute \
  --instance-id i-xxxxxxxxx \
  --instance-type t3.small

# Start instance
aws ec2 start-instances --instance-ids i-xxxxxxxxx
```

### 3. Update Documentation

Update your README and runbooks to reference ECS commands:

- ✅ Replace `make reddit-scrape-incremental` → `make ecs-run-scraper`
- ✅ Replace log paths `/var/log/market-pulse/` → `make ecs-logs-*`
- ✅ Update monitoring dashboards

---

## Cost Comparison

| Component | EC2 (Before) | ECS Fargate (After) | Savings |
|-----------|--------------|---------------------|---------|
| Compute for cron jobs | $30-60/mo (part of large instance) | $1-2/mo (Spot) | **~95%** |
| Operational overhead | High (manual deploys) | Low (GitHub Actions) | ⏱️ |
| Monitoring | Shared logs | Isolated per-job logs | 📊 |

**Total estimated savings: $28-58/month**

---

## Additional Resources

- [AWS ECS Fargate Pricing](https://aws.amazon.com/fargate/pricing/)
- [EventBridge Scheduler Documentation](https://docs.aws.amazon.com/scheduler/latest/UserGuide/what-is-scheduler.html)
- [ECS Task Definition Reference](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definitions.html)

---

## Support

For issues or questions:
1. Check CloudWatch logs: `make ecs-logs-<task-name>`
2. Review task stopped reasons: `aws ecs describe-tasks ...`
3. Check GitHub Actions for build failures
4. Verify Secrets Manager values are correct
