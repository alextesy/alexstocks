# Historical Stock Price Backfill Guide

Complete guide for running the historical stock price backfill job locally and on ECS.

## 🎯 Overview

The backfill job downloads historical stock prices for active tickers and stores them in the `stock_price_history` table. It's designed to be:
- **Durable**: Tracks progress in `backfill_progress` table
- **Resumable**: Can continue after rate limits or failures
- **Safe**: Won't affect production backend when run on ECS

## 📋 Prerequisites

### 1. Run Database Migration

```bash
cd /Users/alex/market-pulse-v2
make migrate-up
```

This creates the `backfill_progress` table.

### 2. Deploy ECS Task (First Time Only)

```bash
# Apply terraform changes
cd infrastructure/terraform
terraform plan
terraform apply

# Build and push Docker image
cd ../..
make push-jobs-image
```

## 🧪 Testing (Always Test First!)

### Local Test (Top 5 Tickers, Last 7 Days)

```bash
make test-historical-backfill
```

**What it does:**
- Finds top 5 most-mentioned tickers
- Backfills last 7 days of data
- Quick validation (~1-2 minutes)
- Shows if API calls work

### Custom Local Test

```bash
# Test specific date range
make test-historical-backfill-custom START=2025-01-01 END=2025-01-15

# Test more tickers
make test-historical-backfill-custom TOP_N=10

# Both
make test-historical-backfill-custom TOP_N=10 START=2025-01-01 END=2025-01-15
```

### ECS Test (Recommended Before Full Run)

```bash
# Run test on ECS Fargate Spot
make ecs-run-historical-backfill-test

# Watch logs in real-time
make ecs-logs-historical-backfill
```

**Cost:** ~$0.01 per test run

## 🚀 Production Runs

### Full Backfill (ECS - Recommended)

```bash
# Run full backfill on ECS
make ecs-run-historical-backfill

# Monitor logs
make ecs-logs-historical-backfill
```

**Configuration:**
- Date range: October 1, 2025 to today (configurable in config.py)
- Min articles: 10 (only tickers with ≥10 articles)
- Batch size: 50 tickers per batch
- Delay: 2 seconds between batches
- Resources: 1 vCPU, 2GB RAM
- Cost: ~$0.02-0.04 per hour

### Resume After Rate Limit

If the job hits rate limits, it will:
1. Mark affected tickers as `rate_limited` in database
2. Save all progress
3. Exit gracefully
4. Display the `run_id` in logs

To resume:

```bash
# ECS (recommended)
make ecs-run-historical-backfill-resume RUN_ID=backfill-20241122-123456-abcd1234

# Or locally
make collect-historical-backfill-resume RUN_ID=backfill-20241122-123456-abcd1234
```

## 📊 Monitoring

### Check Progress in Database

```sql
-- Overall run status
SELECT 
    run_id,
    status,
    COUNT(*) as count,
    SUM(records_inserted) as total_records
FROM backfill_progress
GROUP BY run_id, status
ORDER BY MIN(started_at) DESC;

-- Failed tickers (need retry)
SELECT symbol, error_message, started_at
FROM backfill_progress
WHERE status = 'failed'
ORDER BY started_at DESC;

-- Rate limited tickers (need resume)
SELECT symbol, error_message, started_at
FROM backfill_progress
WHERE status = 'rate_limited'
ORDER BY started_at DESC;
```

### View ECS Task Status

```bash
# List running tasks
aws ecs list-tasks --cluster market-pulse-jobs

# Get task details
aws ecs describe-tasks --cluster market-pulse-jobs --tasks <task-id>
```

## 🎛️ Advanced Usage

### Custom Date Range (ECS)

Currently requires code change in `jobs/jobs/collect_historical_prices_backfill.py`:

```python
# Change default year from 2025 to your desired year
start_dt = datetime(
    2024,  # <-- Change this
    settings.historical_backfill_start_month,
    settings.historical_backfill_start_day,
    tzinfo=UTC,
)
```

Then rebuild and push:
```bash
make push-jobs-image
```

### Adjust Parameters

Edit `app/collectors/stock_price_collector.py`:

```python
async def collect_historical_backfill(
    self,
    db: Session,
    run_id: str,
    start_date: datetime,
    end_date: datetime | None = None,
    min_article_threshold: int = 10,  # <-- Lower for more tickers
    batch_size: int = 50,              # <-- Adjust batch size
    delay_between_batches: float = 2.0,  # <-- Increase to avoid rate limits
    resume: bool = True,
) -> dict:
```

## 🔧 Troubleshooting

### Rate Limit Hit Immediately

**Solution:** Increase delay between batches
```bash
# Edit app/collectors/stock_price_collector.py
delay_between_batches: float = 5.0  # Increase from 2.0
```

### No Tickers Found

**Check:** Do you have articles in the database?
```sql
SELECT COUNT(*) FROM article_tickers;
SELECT ticker, COUNT(*) FROM article_tickers GROUP BY ticker ORDER BY COUNT(*) DESC LIMIT 10;
```

### Task Crashes/Times Out on ECS

**Solutions:**
1. Check logs: `make ecs-logs-historical-backfill`
2. Increase timeout in `infrastructure/terraform/ecs.tf`:
   ```hcl
   stopTimeout = 600  # 10 minutes instead of 5
   ```
3. Increase memory if OOM:
   ```hcl
   memory = "4096"  # 4GB instead of 2GB
   ```

### Can't Resume - Run ID Not Found

**Check database:**
```sql
SELECT DISTINCT run_id FROM backfill_progress ORDER BY run_id DESC;
```

## 📈 Performance Expectations

### Test Run (5 tickers, 7 days)
- Duration: 1-2 minutes
- API calls: ~35 calls (5 tickers × 7 days)
- Records inserted: ~35-175 (depending on hourly/daily data)
- Cost (ECS): ~$0.01

### Full Run (Estimated)
- Tickers: ~50-200 (depends on article threshold)
- Date range: Oct 2025 - Today (~2 months)
- Duration: 1-3 hours (with rate limit delays)
- API calls: ~3,000-12,000
- Records inserted: ~15,000-100,000+
- Cost (ECS): ~$0.02-0.06

## 🎯 Recommended Workflow

1. **Test Locally**
   ```bash
   make test-historical-backfill
   ```

2. **Test on ECS**
   ```bash
   make ecs-run-historical-backfill-test
   make ecs-logs-historical-backfill
   ```

3. **Run Full Backfill on ECS**
   ```bash
   make ecs-run-historical-backfill
   make ecs-logs-historical-backfill
   ```

4. **Monitor Progress**
   - Watch logs for rate limits
   - Query `backfill_progress` table
   - Note the `run_id` from logs

5. **Resume if Needed**
   ```bash
   # Wait a few hours if rate limited
   make ecs-run-historical-backfill-resume RUN_ID=your-run-id
   ```

6. **Verify Results**
   ```sql
   SELECT 
       symbol,
       COUNT(*) as data_points,
       MIN(date) as earliest,
       MAX(date) as latest
   FROM stock_price_history
   GROUP BY symbol
   ORDER BY data_points DESC
   LIMIT 20;
   ```

## 🔒 Security Notes

- Secrets managed via AWS Secrets Manager
- No API keys in code or logs
- VPC isolated (private subnets)
- Logs retention: 30 days (configurable)

## 💰 Cost Breakdown

| Item | Cost |
|------|------|
| ECS Fargate Spot (1 vCPU, 2GB) | ~$0.015/hour |
| Data transfer | Negligible |
| CloudWatch Logs | <$0.01/month |
| **Estimated total per full run** | **$0.02-0.06** |

## 📞 Support

If you hit issues:
1. Check logs: `make ecs-logs-historical-backfill`
2. Query database: Check `backfill_progress` table
3. Review error messages in Slack notifications
4. Check this guide's troubleshooting section

