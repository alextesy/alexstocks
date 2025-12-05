# Quickstart: Weekly Email Digest

**Feature**: 001-weekly-email-digest  
**Date**: 2025-12-05

## Prerequisites

- Python 3.11+ with `uv` package manager
- PostgreSQL 16 running (via docker-compose or local install)
- AWS credentials configured (for SES email sending)
- OpenAI API key (for LLM synthesis)

## Setup

### 1. Environment Variables

Add to `.env`:

```bash
# Weekly digest configuration
WEEKLY_DIGEST_SCHEDULE_DAY=SUN          # Day of week to run (MON-SUN)
WEEKLY_DIGEST_SCHEDULE_HOUR=9           # Hour to run (UTC, 0-23)
WEEKLY_DIGEST_BATCH_SIZE=100            # Users per batch
WEEKLY_DIGEST_LLM_MODEL=gpt-4o-mini     # LLM for synthesis
WEEKLY_DIGEST_LLM_MAX_TOKENS=2000       # Max tokens per synthesis
```

### 2. Database Migration

```bash
# Apply migration for WeeklyDigestSendRecord table
uv run alembic upgrade head

# Verify table exists
uv run python -c "
from app.db.session import SessionLocal
from app.db.models import WeeklyDigestSendRecord
with SessionLocal() as session:
    print('WeeklyDigestSendRecord table ready')
"
```

### 3. Verify Existing Data

```bash
# Check for existing daily summaries (required input for weekly digest)
uv run python -c "
from datetime import date, timedelta
from app.db.session import SessionLocal
from app.repos.summary_repo import DailyTickerSummaryRepository

with SessionLocal() as session:
    repo = DailyTickerSummaryRepository(session)
    week_ago = date.today() - timedelta(days=7)
    summaries = repo.get_summaries_since(week_ago)
    print(f'Found {len(summaries)} daily summaries in last 7 days')
"
```

## Local Development

### Run Weekly Digest Job Manually

```bash
# Dry run (no emails sent)
uv run python jobs/jobs/send_weekly_digest.py --dry-run --verbose

# Send to specific user (for testing)
uv run python jobs/jobs/send_weekly_digest.py --user-email test@example.com --verbose

# Full run for current week
uv run python jobs/jobs/send_weekly_digest.py --verbose
```

### Test Email Rendering

```bash
# Preview weekly digest email for a user
uv run python -c "
from datetime import date, timedelta
from app.db.session import SessionLocal
from app.services.weekly_summary import WeeklySummaryService
from app.services.email_templates import EmailTemplateService
from app.repos.user_repo import UserRepository

with SessionLocal() as session:
    user_repo = UserRepository(session)
    user = user_repo.get_user_by_email('test@example.com')
    
    if user:
        weekly_service = WeeklySummaryService(session)
        week_start = date.today() - timedelta(days=date.today().weekday() + 7)
        
        digest = weekly_service.generate_digest_for_user(user.id, week_start)
        
        template_service = EmailTemplateService()
        html, text = template_service.render_weekly_digest(digest)
        
        # Save preview
        with open('weekly_preview.html', 'w') as f:
            f.write(html)
        print('Saved preview to weekly_preview.html')
    else:
        print('User not found')
"
```

### Update Email Cadence via API

```bash
# Get current cadence
curl -X GET http://localhost:8000/api/users/me/email-cadence \
  -H "Authorization: Bearer $TOKEN"

# Update to weekly only
curl -X PUT http://localhost:8000/api/users/me/email-cadence \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email_cadence": "weekly_only"}'

# Update to both daily and weekly
curl -X PUT http://localhost:8000/api/users/me/email-cadence \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email_cadence": "both"}'
```

## Testing

### Run Unit Tests

```bash
# Weekly summary service tests
uv run pytest tests/unit/test_weekly_summary.py -v

# Weekly digest repository tests
uv run pytest tests/unit/test_weekly_digest_repo.py -v

# All weekly digest tests
uv run pytest -k "weekly" -v
```

### Run Integration Tests

```bash
# Requires database running
docker-compose up -d db

# Run integration tests
uv run pytest tests/integration/test_weekly_digest_job.py -v

# Cleanup
docker-compose down
```

## Deployment

### 1. Deploy Database Migration

```bash
# On production
uv run alembic upgrade head
```

### 2. Deploy Application Code

```bash
# Build and push Docker images
make build-app-image
make push-app-image
make build-jobs-image
make push-jobs-image
```

### 3. Deploy Terraform (EventBridge + ECS Task)

```bash
cd infrastructure/terraform
terraform plan -var-file=prod.tfvars
terraform apply -var-file=prod.tfvars
```

### 4. Verify Deployment

```bash
# Check EventBridge schedule
aws scheduler get-schedule --name market-pulse-weekly-digest

# Check ECS task definition
aws ecs describe-task-definition --task-definition market-pulse-weekly-digest

# Trigger test run
aws scheduler invoke --schedule-name market-pulse-weekly-digest
```

## Monitoring

### CloudWatch Metrics

- `WeeklyDigest/UsersProcessed` - Total users processed per run
- `WeeklyDigest/EmailsSent` - Successful email sends
- `WeeklyDigest/EmailsSkipped` - Skipped (no data, opted out)
- `WeeklyDigest/EmailsFailed` - Failed sends
- `WeeklyDigest/JobDuration` - Total job runtime in seconds

### CloudWatch Alarms

- **Multiple sends per user**: Alert if same user receives >1 weekly email
- **High failure rate**: Alert if >5% of sends fail
- **Job timeout**: Alert if job exceeds 2 hours
- **Zero sends**: Alert if job completes with 0 sends (unexpected)

### Log Queries

```sql
-- Find failed sends for a week
fields @timestamp, user_id, error
| filter status = 'failed' and week_start_date = '2025-12-02'
| sort @timestamp desc

-- Summarize weekly job run
fields @timestamp, users_processed, emails_sent, emails_skipped, emails_failed, duration_seconds
| filter @message like /Weekly digest job completed/
| sort @timestamp desc
| limit 10
```

## Troubleshooting

### No emails sent

1. Check user has `email_cadence` set to `weekly_only` or `both`
2. Check user has ticker follows with daily summaries
3. Check `WeeklyDigestSendRecord` for existing record (idempotency)

```bash
uv run python -c "
from app.db.session import SessionLocal
from app.repos.weekly_digest_repo import WeeklyDigestRepository
from datetime import date, timedelta

with SessionLocal() as session:
    repo = WeeklyDigestRepository(session)
    week_start = date.today() - timedelta(days=date.today().weekday())
    records = repo.get_records_for_week(week_start)
    for r in records:
        print(f'User {r.user_id}: {r.status} - {r.skip_reason or r.error or \"OK\"}')
"
```

### Duplicate emails

1. Check unique constraint on `weekly_digest_send_record`
2. Review job logs for concurrent execution
3. Verify idempotency check in job code

### LLM synthesis errors

1. Check OpenAI API key and quota
2. Review daily summary content (required input)
3. Check LLM response parsing in logs

```bash
# Check LLM errors in logs
grep "OpenAI API" logs/weekly_digest.log | tail -20
```

