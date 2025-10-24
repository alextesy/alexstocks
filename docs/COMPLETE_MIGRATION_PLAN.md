# Complete ECS Migration & App Optimization Plan

**Last Updated:** October 8, 2025
**Branch:** `refactor/create-lambdas`
**Estimated Total Time:** 3-4 hours (can be done over multiple days)

---

## 📋 Table of Contents

1. [Pre-Migration Checklist](#pre-migration-checklist)
2. [Phase 1: Local Testing & Validation](#phase-1-local-testing--validation)
3. [Phase 2: Push Code & Deploy Infrastructure](#phase-2-push-code--deploy-infrastructure)
4. [Phase 3: Test ECS Jobs](#phase-3-test-ecs-jobs)
5. [Phase 4: Production Cutover](#phase-4-production-cutover)
6. [Phase 5: App Docker Image Optimization](#phase-5-app-docker-image-optimization)
7. [Phase 6: Cleanup & Monitoring](#phase-6-cleanup--monitoring)
8. [Rollback Procedures](#rollback-procedures)

---

## Pre-Migration Checklist

### ✅ Before Starting:

```bash
# 1. Verify you're on the correct branch
git branch
# Should show: * refactor/create-lambdas

# 2. Check git status
git status
# Should show: deletions in app/jobs/ and ingest/, additions in jobs/ and infrastructure/

# 3. Verify AWS credentials
aws sts get-caller-identity
# Should show your AWS account

# 4. Backup current EC2 crontab
ssh ubuntu@your-ec2-instance "crontab -l > ~/crontab_backup_$(date +%Y%m%d).txt"
```

### 📝 Information to Gather:

Run these commands and save the output:

```bash
# VPC ID
aws ec2 describe-vpcs --query 'Vpcs[*].[VpcId,Tags[?Key==`Name`].Value|[0]]' --output table

# Private Subnet IDs (where your Postgres/EC2 is)
aws ec2 describe-subnets --filters "Name=vpc-id,Values=YOUR_VPC_ID" --query 'Subnets[*].[SubnetId,AvailabilityZone,CidrBlock,Tags[?Key==`Name`].Value|[0]]' --output table

# Postgres Security Group ID
aws ec2 describe-security-groups --filters "Name=group-name,Values=*postgres*" --query 'SecurityGroups[*].[GroupId,GroupName,VpcId]' --output table

# Your EC2 instance details
aws ec2 describe-instances --filters "Name=tag:Name,Values=*market-pulse*" --query 'Reservations[*].Instances[*].[InstanceId,PrivateIpAddress,SubnetId,SecurityGroups[0].GroupId]' --output table
```

**Save these values - you'll need them for Terraform configuration!**

---

## Phase 1: Local Testing & Validation

**Time:** 15-20 minutes
**Risk Level:** 🟢 Low (local only)

### Step 1.1: Test Docker Build Locally

```bash
# Navigate to project root
cd /Users/alex/market-pulse-v2

# Build the jobs Docker image locally
make build-jobs-image

# Expected output: "Successfully built..." with image ID
# If this fails, DO NOT proceed - fix dependency issues first
```

**If build fails:**
- Check `jobs/pyproject.toml` dependencies
- Check `jobs/Dockerfile` COPY paths
- Fix errors and retry

### Step 1.2: Verify App Still Works Locally

```bash
# Start your local services
make up

# In another terminal, check that the web app starts
uv run uvicorn app.main:app --reload

# Visit http://localhost:8000
# Verify: Homepage loads, ticker pages work, API responses work
```

### Step 1.3: Check Current EC2 Cron Jobs

```bash
# SSH to EC2 and document current cron jobs
ssh ubuntu@your-ec2-instance

# View current crontab
crontab -l

# Save output - you'll need to know what's running
```

**Expected cron entries (document yours):**
```bash
# Example:
*/15 * * * * /path/to/script1.sh
*/15 * * * * /path/to/script2.sh
0 4 * * * /path/to/script3.sh
```

---

## Phase 2: Push Code & Deploy Infrastructure

**Time:** 30-45 minutes
**Risk Level:** 🟡 Medium (EC2 crons will break, but web app safe)

### Step 2.1: Push to GitHub

```bash
# Review changes one more time
git status
git diff --stat

# Commit if not already committed
git add .
git commit -m "Migrate cron jobs to ECS Fargate

- Move jobs from app/jobs/ to isolated jobs/ directory
- Add Terraform infrastructure for ECS Fargate
- Add GitHub Actions workflow for container deployment
- Add EventBridge schedulers for automated job execution
- Remove old job files from app/

This prepares for migrating background jobs from EC2 to containerized ECS tasks."

# Push to GitHub
git push origin refactor/create-lambdas
```

⚠️ **After this push:**
- Your web app on EC2 will continue working normally ✅
- EC2 cron jobs will FAIL when they next run ❌
- **Proceed quickly to deploy ECS jobs!**

### Step 2.2: Create AWS Secrets

```bash
# Run the secret setup script
./scripts/setup-aws-secrets.sh

# You'll be prompted for:
# - Postgres connection string
# - Reddit API credentials
```

**Manual verification:**
```bash
aws secretsmanager list-secrets --query 'SecretList[?starts_with(Name, `market-pulse/`)].Name'

# Should show:
# - market-pulse/postgres-url
# - market-pulse/reddit-client-id
# - market-pulse/reddit-client-secret
# - market-pulse/reddit-user-agent
```

### Step 2.3: Configure Terraform

```bash
cd infrastructure/terraform

# Copy example config
cp terraform.tfvars.example terraform.tfvars

# Edit with your AWS details
vim terraform.tfvars
# OR
nano terraform.tfvars
```

**Fill in these values** (from Pre-Migration Checklist):
```hcl
project_name = "market-pulse"
aws_region   = "us-east-1"  # Change to your region

# VPC Configuration
vpc_id                     = "vpc-xxxxx"        # From Pre-Migration step
private_subnet_ids         = ["subnet-xxxxx", "subnet-yyyyy"]  # From Pre-Migration
postgres_security_group_id = "sg-xxxxx"        # From Pre-Migration

# ECS Configuration
task_cpu    = "256"   # 0.25 vCPU
task_memory = "512"   # 512 MB

# Logging
log_retention_days = 7

# Image tag (use 'latest' for now)
ecr_image_tag = "latest"
```

### Step 2.4: Deploy Infrastructure with Terraform

```bash
# Still in infrastructure/terraform/

# Initialize Terraform
terraform init

# Review what will be created (IMPORTANT - read this!)
terraform plan

# Expected resources to create:
# - ECR repository
# - ECS cluster
# - 3 ECS task definitions
# - 3 EventBridge schedules (DISABLED initially)
# - 3 CloudWatch log groups
# - 3 SQS DLQs
# - IAM roles and policies
# - Security group rules

# If everything looks good, deploy
terraform apply

# Type 'yes' when prompted
```

**Expected output:**
```
Apply complete! Resources: 25 added, 0 changed, 0 destroyed.

Outputs:
ecr_repository_url = "123456789012.dkr.ecr.us-east-1.amazonaws.com/market-pulse-jobs"
ecs_cluster_name = "market-pulse-jobs"
```

### Step 2.5: Build & Push Docker Image to ECR

```bash
# Return to project root
cd /Users/alex/market-pulse-v2

# Login to ECR
make ecr-login

# Build and push the image (this may take 5-10 minutes)
make push-jobs-image

# Expected output: "latest: digest: sha256:xxxxx"
```

**Verify image was pushed:**
```bash
aws ecr describe-images --repository-name market-pulse-jobs
```

---

## Phase 3: Test ECS Jobs

**Time:** 30-45 minutes
**Risk Level:** 🟢 Low (manual testing, schedules still disabled)

### Step 3.1: Test Reddit Scraper

```bash
# Manually run the scraper job
make ecs-run-scraper

# Output will show task ARN
# Wait 2-3 minutes for task to start

# Tail logs (in real-time)
make ecs-logs-scraper

# Look for:
# ✅ "Successfully connected to database"
# ✅ "Fetching submissions from r/wallstreetbets"
# ✅ "Inserted X new articles"
# ✅ "Scraping completed successfully"

# Check for errors (should be none):
# ❌ Database connection errors
# ❌ Reddit API authentication errors
# ❌ Import errors
```

**If task fails to start:**
```bash
# Check task status
aws ecs list-tasks --cluster market-pulse-jobs --desired-status STOPPED

# Get stopped reason
aws ecs describe-tasks --cluster market-pulse-jobs --tasks <task-arn>

# Common issues:
# - Can't pull image from ECR → Check IAM execution role
# - Container exits immediately → Check logs for errors
# - Task never starts → Check subnet/security group config
```

### Step 3.2: Test Sentiment Analysis

```bash
# Run sentiment analysis job
make ecs-run-sentiment

# Tail logs
make ecs-logs-sentiment

# Look for:
# ✅ "Loading LLM model: ProsusAI/finbert"
# ✅ "Successfully loaded financial sentiment model"
# ✅ "Processing X articles"
# ✅ "Updated X articles with sentiment"
```

### Step 3.3: Test Daily Status (Optional)

```bash
# Run daily status job
make ecs-run-status

# Tail logs
make ecs-logs-status

# Look for status output
```

### Step 3.4: Verify Database Writes

```bash
# SSH to EC2
ssh ubuntu@your-ec2-instance

# Connect to Postgres (adjust connection string)
psql $DATABASE_URL

# Check for recent articles (from scraper)
SELECT COUNT(*), MAX(created_at)
FROM articles
WHERE created_at > NOW() - INTERVAL '1 hour';

# Check for recent sentiment updates
SELECT COUNT(*), MAX(updated_at)
FROM articles
WHERE sentiment IS NOT NULL
  AND updated_at > NOW() - INTERVAL '1 hour';

# Exit psql
\q
```

**Expected results:**
- At least a few new articles from scraper
- Sentiment values updated on articles

---

## Phase 4: Production Cutover

**Time:** 15-20 minutes
**Risk Level:** 🟡 Medium (switching from EC2 to ECS)

### Step 4.1: Disable EC2 Cron Jobs

```bash
# SSH to EC2
ssh ubuntu@your-ec2-instance

# Backup current crontab (again, just to be safe)
crontab -l > ~/crontab_backup_before_cutover.txt

# Edit crontab
crontab -e

# Comment out market-pulse cron jobs:
# */15 * * * * /home/ubuntu/market-pulse-v2/.venv/bin/python -m ingest.reddit_scraper_cli --mode incremental
# */15 * * * * /home/ubuntu/market-pulse-v2/.venv/bin/python -m app.jobs.analyze_sentiment --source reddit --hours-back 1
# 0 4 * * * /home/ubuntu/market-pulse-v2/.venv/bin/python -m ingest.reddit_scraper_cli --mode status

# Change to (add # at start of each line):
# #*/15 * * * * /home/ubuntu/market-pulse-v2/.venv/bin/python -m ingest.reddit_scraper_cli --mode incremental
# #*/15 * * * * /home/ubuntu/market-pulse-v2/.venv/bin/python -m app.jobs.analyze_sentiment --source reddit --hours-back 1
# #0 4 * * * /home/ubuntu/market-pulse-v2/.venv/bin/python -m ingest.reddit_scraper_cli --mode status

# Save and exit (Ctrl+X in nano, :wq in vim)

# Verify crontab is updated
crontab -l
```

### Step 4.2: Enable ECS Schedules

```bash
# Return to your local machine
exit  # Exit from EC2

# Enable all EventBridge schedules
make schedule-enable-all

# Verify schedules are enabled
make schedule-status

# Should show:
# reddit-scrape-incremental: ENABLED
# sentiment-analysis-reddit: ENABLED
# daily-status: ENABLED
```

### Step 4.3: Monitor First Automated Runs

The schedules will trigger at the next interval (every 15 minutes for scraper and sentiment).

```bash
# Monitor logs in multiple terminals:

# Terminal 1: Scraper logs
make ecs-logs-scraper

# Terminal 2: Sentiment logs
make ecs-logs-sentiment

# Watch for next scheduled execution (wait up to 15 minutes)
```

**What to watch for:**
- ✅ Tasks start automatically via EventBridge
- ✅ No errors in logs
- ✅ Database writes continue
- ✅ Articles get sentiment scores

### Step 4.4: Verify Web App Still Works

```bash
# Visit your production site
open https://alexstocks.com  # Or your domain

# Check:
# ✅ Homepage loads
# ✅ Ticker pages show data
# ✅ Recent articles appear
# ✅ Sentiment scores visible
```

---

## Phase 5: App Docker Image Optimization

**Time:** 30-45 minutes
**Risk Level:** 🟢 Low (can be done separately, after cutover)

**Why?** Now that jobs are separate, your main app doesn't need heavy ML dependencies.

### Step 5.1: Analyze Current Dependencies

**Heavy dependencies to remove from main app:**
- ❌ `jupyter>=1.1.1` - Only needed for local notebooks
- ❌ `ipykernel>=6.30.1` - Only needed for local notebooks
- ❌ `matplotlib>=3.10.6` - Only needed for local notebooks
- ❌ `seaborn>=0.13.2` - Only needed for local notebooks
- ⚠️ `praw>=7.7.0` - Only needed for jobs (scraping)
- ⚠️ `prawcore>=2.4.0` - Only needed for jobs (scraping)
- ⚠️ `transformers>=4.30.0` - Only needed for jobs (sentiment)
- ⚠️ `torch>=2.2.0` - Only needed for jobs (sentiment)
- ⚠️ `torchvision>=0.17.0` - Only needed for jobs (sentiment)

**Dependencies to KEEP (used by web app):**
- ✅ `fastapi`, `uvicorn` - Web framework
- ✅ `sqlalchemy`, `psycopg` - Database
- ✅ `pandas` - Used in `app/services/stock_data.py`
- ✅ `yfinance` - Stock price API
- ✅ `vaderSentiment` - Lightweight sentiment (used by app)
- ✅ `beautifulsoup4`, `lxml` - HTML parsing

### Step 5.2: Check EC2 for Direct Usage

```bash
# SSH to EC2
ssh ubuntu@your-ec2-instance

# Check if any systemd services use those modules
systemctl list-units | grep market

# Check the systemd service file
cat /etc/systemd/system/market-pulse.service

# Look for ExecStart line - it should only start uvicorn (web app)
# Example: ExecStart=/path/to/.venv/bin/uvicorn app.main:app
```

**If the systemd service ONLY runs uvicorn (web app)**, it's safe to remove heavy deps!

### Step 5.3: Update pyproject.toml

```bash
# Return to local machine
exit

# Edit pyproject.toml
vim pyproject.toml
# OR
code pyproject.toml
```

**Create TWO dependency sets:**

**Option A: Split into separate groups (recommended)**
```toml
[project]
dependencies = [
    # Core web app dependencies
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "jinja2>=3.1.0",
    "python-multipart>=0.0.6",
    "sqlalchemy>=2.0.0",
    "psycopg[binary]>=3.1.0",
    "psycopg2-binary>=2.9.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "httpx>=0.25.0",
    "vaderSentiment>=3.3.2",  # Lightweight, used by app
    "pyyaml>=6.0.0",
    "python-dateutil>=2.8.0",
    "requests>=2.31.0",
    "beautifulsoup4>=4.12.0",
    "lxml>=4.9.0",
    "python-dotenv>=1.0.0",
    "yfinance>=0.2.66",
    "pandas>=2.3.2",  # Used by stock_data service
    "numpy>=1.24.0,<2.0.0",  # Required by pandas
]

[dependency-groups]
# Development tools
dev = [
    "black>=25.1.0",
    "mypy>=1.18.1",
    "pytest>=8.4.2",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.1.0",
    "pytest-mock>=3.12.0",
    "ruff>=0.13.0",
    "faker>=22.0.0",
    "freezegun>=1.4.0",
    "pre-commit>=3.5.0",
    "bandit>=1.7.0",
    "types-requests>=2.31.0",
    "types-beautifulsoup4>=4.12.0",
    "types-pyyaml>=6.0.0",
]

# Heavy dependencies for local development only
notebooks = [
    "jupyter>=1.1.1",
    "ipykernel>=6.30.1",
    "matplotlib>=3.10.6",
    "seaborn>=0.13.2",
]

# Job dependencies (for running jobs locally)
jobs = [
    "praw>=7.7.0",
    "prawcore>=2.4.0",
    "transformers>=4.30.0,<4.40.0",
    "torch>=2.2.0,<2.3.0",
    "torchvision>=0.17.0,<0.18.0",
    "tqdm>=4.66.0",
]
```

### Step 5.4: Update Dockerfile for Production

Create `Dockerfile.prod` (optimized):

```bash
# Create new Dockerfile for production
cat > Dockerfile.prod << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install ONLY core dependencies (not dev, not notebooks, not jobs)
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy application code (only what's needed for web app)
COPY app/ ./app/

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)"

# Run uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF
```

### Step 5.5: Test Optimized Image Locally

```bash
# Build optimized image
docker build -f Dockerfile.prod -t market-pulse-app-optimized .

# Compare sizes
docker images | grep market-pulse

# Expected savings: 30-50% reduction (especially if torch/transformers removed)

# Test the optimized image
docker run -p 8000:8000 --env-file .env market-pulse-app-optimized

# Visit http://localhost:8000
# Verify everything works
```

### Step 5.6: Deploy Optimized Image to EC2

**Only do this after verifying local testing!**

```bash
# SSH to EC2
ssh ubuntu@your-ec2-instance

# Navigate to project
cd ~/market-pulse-v2

# Pull latest code
git pull origin refactor/create-lambdas

# Update dependencies (this will be faster now!)
source .venv/bin/activate
uv pip install -r pyproject.toml

# Restart web app
sudo systemctl restart market-pulse

# Check logs
sudo journalctl -u market-pulse -f

# Look for:
# ✅ "Application startup complete"
# ❌ No import errors
```

**Verify web app:**
```bash
# From your local machine
curl https://alexstocks.com/health

# Should return: {"status":"ok"}
```

---

## Phase 6: Cleanup & Monitoring

**Time:** 15-20 minutes
**Risk Level:** 🟢 Low

### Step 6.1: Monitor for 48 Hours

```bash
# Check ECS tasks are running regularly
make ecs-list-tasks

# Check CloudWatch logs periodically
make ecs-logs-scraper
make ecs-logs-sentiment

# Check database for continuous data flow
ssh ubuntu@your-ec2-instance "psql $DATABASE_URL -c \"SELECT DATE(created_at), COUNT(*) FROM articles WHERE created_at > NOW() - INTERVAL '7 days' GROUP BY DATE(created_at) ORDER BY 1 DESC;\""
```

### Step 6.2: Set Up Alerts (Optional)

Create CloudWatch alarms for:
- ECS task failures
- Dead letter queue messages
- No articles scraped in 1 hour

### Step 6.3: Update Documentation

```bash
# Update README with new deployment process
# Update runbooks with ECS commands
# Document new monitoring procedures
```

### Step 6.4: Clean Up Old Files on EC2

**Only after 1 week of successful operation:**

```bash
# SSH to EC2
ssh ubuntu@your-ec2-instance

# Remove old crontab backup files
rm ~/crontab_backup_*.txt

# Optional: Remove old virtual environment (if you created new one)
# rm -rf ~/market-pulse-v2/.venv.old
```

---

## Rollback Procedures

### If ECS Jobs Fail:

#### Rollback Option 1: Re-enable EC2 Crons (Fast)

```bash
# SSH to EC2
ssh ubuntu@your-ec2-instance

# Restore old crontab
crontab ~/crontab_backup_before_cutover.txt

# Verify
crontab -l

# Disable ECS schedules
make schedule-disable-all
```

#### Rollback Option 2: Fix ECS Issue

```bash
# Check logs for errors
make ecs-logs-scraper
make ecs-logs-sentiment

# Common fixes:
# - Update secrets in AWS Secrets Manager
# - Fix security group rules
# - Update task definition with new image
# - Check IAM permissions
```

### If Web App Breaks After Optimization:

```bash
# SSH to EC2
ssh ubuntu@your-ec2-instance

# Revert to previous commit
cd ~/market-pulse-v2
git log --oneline -5  # Find previous commit
git checkout <previous-commit-hash>

# Reinstall old dependencies
source .venv/bin/activate
uv sync

# Restart app
sudo systemctl restart market-pulse
```

---

## Success Criteria

After completing all phases, you should have:

- ✅ Web app running on EC2 (unchanged functionality)
- ✅ 3 ECS jobs running every 15 minutes / daily
- ✅ CloudWatch logs showing successful runs
- ✅ Continuous data flow into database
- ✅ No errors in application logs
- ✅ 30-50% smaller Docker image for web app
- ✅ ~90% cost reduction on job execution

---

## Cost Tracking

**Before:**
- EC2 instance: $30-60/month (portion for cron jobs)

**After:**
- ECS Fargate Spot tasks: $1-2/month
- CloudWatch Logs: ~$0.20/month
- Secrets Manager: $1.60/month
- **Total:** $3-4/month

**Savings:** ~$27-56/month (~90%)

---

## Support

If you encounter issues:

1. Check logs: `make ecs-logs-scraper`, `make ecs-logs-sentiment`
2. Check task status: `make ecs-list-tasks`
3. Check EventBridge: `make schedule-status`
4. Review [ECS_MIGRATION_GUIDE.md](ECS_MIGRATION_GUIDE.md)
5. Review [Troubleshooting](#rollback-procedures) section above

---

**Good luck with your migration! 🚀**
