# Market Pulse Jobs

Containerized cron jobs for ECS Fargate deployment.

## Overview

This directory contains **only configuration files** for containerized batch jobs on AWS ECS Fargate. The actual code lives in the parent `app/` and `ingest/` directories to avoid duplication.

### Jobs Included

1. **Reddit Scraper** (`ingest/reddit_scraper_cli.py`)
   - Scrapes Reddit discussion threads incrementally
   - Runs every 15 minutes
   - ~1-2 min execution time

2. **Sentiment Analysis** (`app/jobs/analyze_sentiment.py`)
   - Analyzes sentiment for new Reddit comments
   - Runs every 15 minutes
   - ~1-2 min execution time

3. **Daily Status Check** (`ingest/reddit_scraper_cli.py --mode status`)
   - Reports scraping progress and statistics
   - Runs daily at 4:00 UTC
   - <1 min execution time

## Structure

```
jobs/
├── Dockerfile                  # Container definition
├── pyproject.toml              # Minimal dependencies (batch jobs only)
└── README.md                   # This file

# NO code duplication!
# Docker build copies from parent directories:
#   COPY app /app/app           (from ../app/)
#   COPY ingest /app/ingest     (from ../ingest/)
```

**Key Point**: The `jobs/` directory contains **only config files**, not code. This keeps the codebase DRY (Don't Repeat Yourself).

## Docker Image

### Building Locally

```bash
# Build from project root (NOT from jobs/ directory!)
make build-jobs-image

# Or manually:
docker build -f jobs/Dockerfile -t market-pulse-jobs:local .

# Test run
docker run --rm \
  -e POSTGRES_URL="postgresql://..." \
  -e REDDIT_CLIENT_ID="..." \
  -e REDDIT_CLIENT_SECRET="..." \
  -e REDDIT_USER_AGENT="market-pulse/1.0" \
  market-pulse-jobs:local \
  python -m ingest.reddit_scraper_cli --mode status
```

### Pushing to ECR

```bash
# From project root
make push-jobs-image
```

**Important**: Always build from the **project root** directory, not from `jobs/`.

This will:
1. Login to AWS ECR
2. Build the image for `linux/amd64` platform
3. Tag as `latest`
4. Push to ECR repository

## Dependencies

See [pyproject.toml](pyproject.toml) for the full list.

**Key dependencies:**
- `sqlalchemy` + `psycopg2-binary` (database)
- `praw` + `prawcore` (Reddit API)
- `transformers` + `torch` (LLM sentiment)
- `vaderSentiment` (fallback sentiment)
- `tqdm` (progress bars)

**Excluded from jobs:**
- `fastapi`, `uvicorn` (web server)
- `jupyter`, `pandas`, `matplotlib` (analysis tools)
- `yfinance` (stock data - separate job)

This keeps the image size small (~1.2 GB vs ~2 GB for full app).

## Environment Variables

### Required

- `POSTGRES_URL` - Database connection string
- `REDDIT_CLIENT_ID` - Reddit API client ID
- `REDDIT_CLIENT_SECRET` - Reddit API client secret
- `REDDIT_USER_AGENT` - Reddit API user agent

### Optional

- `ENVIRONMENT` - Environment name (production/staging)
- `LOG_LEVEL` - Logging level (DEBUG/INFO/WARNING/ERROR)

## Running Jobs Locally

**Note**: Jobs use code from `app/` and `ingest/` directories in the project root.

### 1. Install Dependencies

```bash
# From project root (NOT from jobs/)
uv sync
```

### 2. Set Environment Variables

```bash
export POSTGRES_URL="postgresql://user:pass@localhost:5432/marketpulse"
export REDDIT_CLIENT_ID="your_client_id"
export REDDIT_CLIENT_SECRET="your_client_secret"
export REDDIT_USER_AGENT="market-pulse/1.0"
```

### 3. Run Jobs

```bash
# From project root
make reddit-scrape-incremental    # Reddit scraper
make analyze-sentiment-reddit     # Sentiment analysis
make reddit-scrape-status         # Status check
```

## ECS Deployment

Jobs are deployed as ECS Fargate tasks. See [ECS Migration Guide](../docs/ECS_MIGRATION_GUIDE.md) for details.

### Task Definitions

Each job has its own ECS task definition:

1. **market-pulse-reddit-scraper**
   ```json
   {
     "command": ["python", "-m", "ingest.reddit_scraper_cli", "--mode", "incremental"]
   }
   ```

2. **market-pulse-sentiment-analysis**
   ```json
   {
     "command": ["python", "app/jobs/analyze_sentiment.py", "--source", "reddit"]
   }
   ```

3. **market-pulse-daily-status**
   ```json
   {
     "command": ["python", "-m", "ingest.reddit_scraper_cli", "--mode", "status"]
   }
   ```

### Resource Limits

- **CPU**: 0.25 vCPU (256 units)
- **Memory**: 512 MB
- **Timeout**: 10 minutes (scraper/sentiment), 5 minutes (status)
- **Platform**: Fargate Spot (cost-optimized)

## Monitoring

### CloudWatch Logs

```bash
# Tail logs for each job
make ecs-logs-scraper
make ecs-logs-sentiment
make ecs-logs-status
```

### Metrics

ECS automatically tracks:
- Task CPU utilization
- Task memory utilization
- Task count
- Task stopped reason

View in CloudWatch: `AWS/ECS` namespace

## Troubleshooting

### Container Fails to Start

```bash
# Check task stopped reason
aws ecs describe-tasks \
  --cluster market-pulse-jobs \
  --tasks TASK_ARN \
  --query 'tasks[0].stoppedReason'
```

Common issues:
- Missing environment variables
- Invalid database connection
- Insufficient memory/CPU

### Database Connection Timeout

- Verify security group allows ECS tasks → Postgres (port 5432)
- Check `POSTGRES_URL` is correct
- Ensure tasks are in same VPC as database

### Reddit API Rate Limiting

Reddit API limits:
- **60 requests/minute** per OAuth client
- Tasks run every 15 minutes, so should be fine

If rate limited:
- Reduce `max_threads` parameter
- Reduce `max_replace_more` parameter
- Increase schedule interval

## Development

### Adding a New Job

1. Create script in `app/jobs/` or `ingest/`
2. Add dependencies to `pyproject.toml` (if needed)
3. Test locally
4. Create ECS task definition in `infrastructure/terraform/ecs.tf`
5. Create EventBridge schedule in `infrastructure/terraform/eventbridge.tf`
6. Deploy with `make tf-apply`

### Updating Dependencies

```bash
cd jobs
vim pyproject.toml  # Add/update dependencies

# Rebuild image
docker build -t market-pulse-jobs:local .

# Push to ECR
make push-jobs-image
```

## CI/CD

GitHub Actions workflow: [.github/workflows/deploy-ecs-jobs.yml](../.github/workflows/deploy-ecs-jobs.yml)

**Triggers:**
- Push to `main` branch (with changes to `jobs/`, `app/db/`, `app/services/`, or `ingest/`)
- Manual workflow dispatch

**Steps:**
1. Checkout code
2. Configure AWS credentials
3. Build Docker image
4. Push to ECR
5. Update ECS task definitions with new image

## Testing

### Unit Tests

```bash
# Run tests (from project root)
pytest tests/test_jobs*.py -v
```

### Integration Tests

```bash
# Test with real database (staging)
export POSTGRES_URL="postgresql://..."
pytest tests/test_integration_jobs.py -v
```

## Further Reading

- [ECS Migration Guide](../docs/ECS_MIGRATION_GUIDE.md)
- [Infrastructure README](../infrastructure/README.md)
- [Project Makefile](../Makefile)
