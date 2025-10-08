# ECS Migration Checklist

Use this checklist to track your progress through the ECS Fargate migration.

## ☑️ Phase 1: Prerequisites

- [ ] AWS CLI installed and configured (`aws --version`)
- [ ] Terraform installed (`terraform --version` >= 1.0)
- [ ] Docker installed (`docker --version`)
- [ ] Access to AWS account with admin permissions
- [ ] Access to EC2 instance (for crontab changes)
- [ ] Access to production database

## ☑️ Phase 2: Gather Information

- [ ] VPC ID where Postgres is running
  ```bash
  aws ec2 describe-vpcs
  # Record: vpc-_________________
  ```

- [ ] Private Subnet IDs (2+ subnets in different AZs)
  ```bash
  aws ec2 describe-subnets --filters "Name=vpc-id,Values=YOUR_VPC_ID"
  # Record: subnet-_____________, subnet-_____________
  ```

- [ ] Postgres Security Group ID
  ```bash
  aws ec2 describe-security-groups
  # Record: sg-_________________
  ```

- [ ] Postgres connection string
  ```
  postgresql://user:password@host:5432/database
  ```

- [ ] Reddit API credentials
  - Client ID: ___________________________
  - Client Secret: ________________________
  - User Agent: market-pulse/1.0

## ☑️ Phase 3: Setup Secrets

- [ ] Run setup script:
  ```bash
  chmod +x scripts/setup-aws-secrets.sh
  ./scripts/setup-aws-secrets.sh
  ```

- [ ] Verify secrets created:
  ```bash
  aws secretsmanager list-secrets | grep market-pulse
  ```

Expected output:
- market-pulse/postgres-url
- market-pulse/reddit-client-id
- market-pulse/reddit-client-secret
- market-pulse/reddit-user-agent

## ☑️ Phase 4: Configure Terraform

- [ ] Copy example config:
  ```bash
  cd infrastructure/terraform
  cp terraform.tfvars.example terraform.tfvars
  ```

- [ ] Edit terraform.tfvars with your values:
  - [ ] `vpc_id`
  - [ ] `private_subnet_ids`
  - [ ] `postgres_security_group_id`
  - [ ] `aws_region` (if not us-east-1)

- [ ] Initialize Terraform:
  ```bash
  make tf-init
  ```

- [ ] Validate configuration:
  ```bash
  cd infrastructure/terraform && terraform validate
  ```

## ☑️ Phase 5: Deploy Infrastructure

- [ ] Review planned changes:
  ```bash
  make tf-plan
  ```

- [ ] Deploy infrastructure:
  ```bash
  make tf-apply
  ```

- [ ] Verify resources created:
  - [ ] ECR Repository: `aws ecr describe-repositories --repository-names market-pulse-jobs`
  - [ ] ECS Cluster: `aws ecs describe-clusters --clusters market-pulse-jobs`
  - [ ] Task Definitions: `aws ecs list-task-definitions | grep market-pulse`
  - [ ] EventBridge Schedules: `make schedule-status`

## ☑️ Phase 6: Build & Push Docker Image

- [ ] Test build locally:
  ```bash
  make build-jobs-image
  ```

- [ ] Test container runs:
  ```bash
  docker run --rm market-pulse-jobs:local python -c "print('Hello from container!')"
  ```

- [ ] Push to ECR:
  ```bash
  make push-jobs-image
  ```

- [ ] Verify image in ECR:
  ```bash
  aws ecr describe-images --repository-name market-pulse-jobs
  ```

## ☑️ Phase 7: Manual Testing

- [ ] **Test Reddit Scraper:**
  ```bash
  make ecs-run-scraper
  # Wait 2-3 minutes
  make ecs-logs-scraper
  ```
  - [ ] Task completed successfully (no errors in logs)
  - [ ] New articles in database

- [ ] **Test Sentiment Analysis:**
  ```bash
  make ecs-run-sentiment
  make ecs-logs-sentiment
  ```
  - [ ] Task completed successfully
  - [ ] Sentiment scores added to articles

- [ ] **Test Daily Status:**
  ```bash
  make ecs-run-status
  make ecs-logs-status
  ```
  - [ ] Task completed successfully
  - [ ] Status report displayed

- [ ] **Verify Database:**
  ```bash
  psql $POSTGRES_URL
  ```
  ```sql
  -- Check recent articles
  SELECT COUNT(*), MAX(created_at)
  FROM articles
  WHERE source LIKE '%reddit%'
  AND created_at > NOW() - INTERVAL '1 hour';

  -- Check sentiment analysis
  SELECT COUNT(*)
  FROM articles
  WHERE sentiment IS NOT NULL
  AND created_at > NOW() - INTERVAL '1 hour';
  ```

## ☑️ Phase 8: Staged Cutover

### 8.1 Enable ONE Schedule for Testing

- [ ] Enable daily status check (low-impact):
  ```bash
  aws scheduler update-schedule \
    --name market-pulse-daily-status \
    --state ENABLED
  ```

- [ ] Wait for next 4:00 UTC

- [ ] Verify it ran successfully:
  ```bash
  make ecs-logs-status
  ```

### 8.2 Production Cutover

**⚠️ IMPORTANT: Do this during low-traffic hours**

- [ ] **Backup EC2 crontab:**
  ```bash
  ssh ubuntu@ec2-instance
  crontab -l > ~/crontab.backup.$(date +%Y%m%d-%H%M)
  ```

- [ ] **Disable EC2 cron jobs:**
  ```bash
  crontab -e
  # Comment out these 3 lines:
  # */15 * * * * cd /opt/market-pulse-v2 && make reddit-scrape-incremental ...
  # */15 * * * * cd /opt/market-pulse-v2 && make analyze-sentiment-reddit ...
  # 0 4 * * * cd /opt/market-pulse-v2 && make reddit-scrape-status ...
  ```

- [ ] **Verify crontab disabled:**
  ```bash
  crontab -l | grep market-pulse
  # Should show commented lines only
  ```

- [ ] **Enable all ECS schedules:**
  ```bash
  make schedule-enable-all
  ```

- [ ] **Verify schedules enabled:**
  ```bash
  make schedule-status
  ```

- [ ] **Record cutover time:**
  ```
  Cutover completed at: _______________________ UTC
  ```

## ☑️ Phase 9: Monitoring (First 48 Hours)

### Hour 1-2 (Active Monitoring)

- [ ] Watch logs in real-time:
  ```bash
  # Terminal 1
  make ecs-logs-scraper

  # Terminal 2
  make ecs-logs-sentiment
  ```

- [ ] Check running tasks:
  ```bash
  make ecs-list-tasks
  ```

- [ ] Verify no errors in CloudWatch

### Hour 2-24 (Periodic Checks)

Check every 2 hours:

- [ ] 2 hours: Logs clean, database updating
- [ ] 4 hours: Logs clean, database updating
- [ ] 6 hours: Logs clean, database updating
- [ ] 12 hours: Logs clean, database updating
- [ ] 24 hours: Logs clean, database updating

### Day 2 (Final Verification)

- [ ] **Data continuity check:**
  ```sql
  SELECT
    DATE(created_at) as date,
    COUNT(*) as articles,
    COUNT(sentiment) as with_sentiment
  FROM articles
  WHERE source LIKE '%reddit%'
    AND created_at > NOW() - INTERVAL '3 days'
  GROUP BY DATE(created_at)
  ORDER BY date DESC;
  ```
  - [ ] No gaps in data
  - [ ] Article counts similar to pre-migration
  - [ ] Sentiment analysis keeping up

- [ ] **Check Dead Letter Queues:**
  ```bash
  aws sqs get-queue-attributes \
    --queue-url $(aws sqs get-queue-url --queue-name market-pulse-reddit-scraper-dlq --query QueueUrl --output text) \
    --attribute-names ApproximateNumberOfMessages
  ```
  - [ ] DLQ message count = 0 (or very low)

- [ ] **Cost check:**
  ```bash
  aws ce get-cost-and-usage \
    --time-period Start=$(date -d '7 days ago' +%Y-%m-%d),End=$(date +%Y-%m-%d) \
    --granularity DAILY \
    --metrics BlendedCost \
    --filter file://ecs-filter.json
  ```
  - [ ] ECS costs < $5/day

## ☑️ Phase 10: Post-Migration Cleanup (After 1 Week)

- [ ] Remove EC2 crontab entries permanently:
  ```bash
  ssh ubuntu@ec2-instance
  crontab -e  # Delete commented lines
  ```

- [ ] Clean up old logs on EC2:
  ```bash
  sudo rm -rf /var/log/market-pulse/*.log
  ```

- [ ] Update runbooks/documentation:
  - [ ] Replace `make reddit-scrape-incremental` → `make ecs-run-scraper`
  - [ ] Replace log paths → `make ecs-logs-*`
  - [ ] Update monitoring dashboards

- [ ] Consider downsizing EC2 instance:
  ```bash
  aws ec2 stop-instances --instance-ids i-xxxxxxxxx
  aws ec2 modify-instance-attribute \
    --instance-id i-xxxxxxxxx \
    --instance-type t3.small
  aws ec2 start-instances --instance-ids i-xxxxxxxxx
  ```

## ☑️ Phase 11: GitHub Actions Setup (Optional)

- [ ] Create AWS OIDC provider:
  ```bash
  aws iam create-open-id-connect-provider \
    --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
  ```

- [ ] Create IAM role for GitHub Actions:
  ```bash
  # See .github/workflows/deploy-ecs-jobs.yml for required permissions
  ```

- [ ] Add `AWS_ROLE_ARN` to GitHub secrets

- [ ] Test GitHub Actions workflow:
  - [ ] Push change to `jobs/` directory
  - [ ] Verify workflow runs
  - [ ] Verify new image pushed to ECR
  - [ ] Verify task definitions updated

## 🎉 Migration Complete!

**Congratulations!** You've successfully migrated Market Pulse cron jobs to ECS Fargate.

### Success Criteria

- ✅ All three jobs running on schedule
- ✅ No gaps in data collection
- ✅ CloudWatch logs showing clean execution
- ✅ EC2 CPU usage reduced
- ✅ AWS costs reduced by ~90%
- ✅ No errors in Dead Letter Queues

### Regular Maintenance

**Weekly:**
- [ ] Check Dead Letter Queues for failed invocations
- [ ] Review CloudWatch logs for errors

**Monthly:**
- [ ] Review AWS cost breakdown
- [ ] Update dependencies in jobs/pyproject.toml
- [ ] Rebuild and push new image

---

## 🆘 Rollback Plan

If something goes wrong:

### Quick Rollback (< 5 min)

1. Disable ECS schedules:
   ```bash
   make schedule-disable-all
   ```

2. Re-enable EC2 cron:
   ```bash
   ssh ubuntu@ec2-instance
   crontab -e  # Uncomment the 3 lines
   ```

### Full Rollback

```bash
# Destroy all ECS infrastructure
make tf-destroy
```

---

## 📞 Support

- Issues? Check [docs/ECS_MIGRATION_GUIDE.md](ECS_MIGRATION_GUIDE.md)
- Questions? See [infrastructure/README.md](../infrastructure/README.md)
- Commands? Run `make help`
