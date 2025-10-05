# Stock Data Collection Guide

This guide explains how to collect stock price data for all tickers in your database.

## Quick Start

### One-Time Manual Collection

```bash
# Collect current prices for all tickers
uv run python app/scripts/collect_all_stock_data.py --type current

# Collect historical data (last month) for all tickers
uv run python app/scripts/collect_all_stock_data.py --type historical --period 1mo

# Collect both current and historical
uv run python app/scripts/collect_all_stock_data.py --type both --period 1mo
```

### Using the Existing Job Script

You can also use the existing job script:

```bash
# Current prices only
uv run python app/jobs/collect_stock_prices.py --type current

# Historical data only
uv run python app/jobs/collect_stock_prices.py --type historical

# Both
uv run python app/jobs/collect_stock_prices.py --type both
```

## Automated Collection (Production)

### Option 1: Cron (Simple, works everywhere)

**Setup:**

```bash
# Run the setup script
./scripts/setup-stock-price-cron.sh
```

This creates a cron job that runs every 15 minutes.

**Manual Setup:**

```bash
# Open crontab editor
crontab -e

# Add this line (replace /path/to with your actual path):
*/15 * * * * cd /path/to/market-pulse-v2 && /usr/bin/env uv run python app/scripts/collect_all_stock_data.py --type current >> /tmp/stock_price_collection.log 2>&1
```

**Verify:**

```bash
# List cron jobs
crontab -l

# Watch logs
tail -f /tmp/stock_price_collection.log
```

**Remove:**

```bash
crontab -l | grep -v 'collect_all_stock_data.py' | crontab -
```

### Option 2: Systemd Timer (Recommended for Linux servers)

**Setup:**

1. Edit the service file with your paths:
   ```bash
   nano scripts/stock-price-collector.service
   ```

2. Update these fields:
   - `User=your_username`
   - `WorkingDirectory=/path/to/market-pulse-v2`
   - `Environment="DATABASE_URL=..."`

3. Install:
   ```bash
   sudo cp scripts/stock-price-collector.service /etc/systemd/system/
   sudo cp scripts/stock-price-collector.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable stock-price-collector.timer
   sudo systemctl start stock-price-collector.timer
   ```

**Verify:**

```bash
# Check timer status
sudo systemctl status stock-price-collector.timer

# View logs
sudo journalctl -u stock-price-collector.service -f

# List all timers
systemctl list-timers
```

**Control:**

```bash
# Stop timer
sudo systemctl stop stock-price-collector.timer

# Disable (won't start on boot)
sudo systemctl disable stock-price-collector.timer

# Manually trigger
sudo systemctl start stock-price-collector.service
```

### Option 3: GitHub Actions / Cloud Schedulers

For hosted deployments, you can use:

- **GitHub Actions**: `.github/workflows/collect-stock-prices.yml`
- **AWS EventBridge**: Trigger Lambda/ECS task every 15 minutes
- **Google Cloud Scheduler**: Trigger Cloud Run job
- **Heroku Scheduler**: Add-on for periodic tasks

Example GitHub Actions workflow:

```yaml
name: Collect Stock Prices

on:
  schedule:
    - cron: '*/15 * * * *'  # Every 15 minutes
  workflow_dispatch:  # Allow manual trigger

jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install uv
        run: pip install uv
      - name: Collect stock prices
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: uv run python app/scripts/collect_all_stock_data.py --type current
```

## Collection Strategies

### Current Prices (Every 15 Minutes)

**When to run:**
- During market hours: Every 15 minutes
- Outside market hours: Once per hour (to save API quota)

**Command:**
```bash
uv run python app/scripts/collect_all_stock_data.py --type current
```

**Expected Duration:**
- 100 tickers: ~2-3 minutes (with rate limiting)
- 500 tickers: ~10-15 minutes

### Historical Data (Daily)

**When to run:**
- Once daily at market close (e.g., 5 PM ET)
- Or weekly for less frequent updates

**Command:**
```bash
# Daily update (only new data)
uv run python app/scripts/collect_all_stock_data.py --type historical --period 1mo

# Weekly full refresh
uv run python app/scripts/collect_all_stock_data.py --type historical --period 1mo --force-refresh
```

## Smart Scheduling Example

Create a smarter cron that adjusts to market hours:

```bash
# During market hours (9:30 AM - 4:00 PM ET, Mon-Fri): every 15 min
*/15 9-16 * * 1-5 cd /path/to/project && uv run python app/scripts/collect_all_stock_data.py --type current >> /tmp/stock_prices.log 2>&1

# Outside market hours: every hour
0 * * * * cd /path/to/project && uv run python app/scripts/collect_all_stock_data.py --type current >> /tmp/stock_prices.log 2>&1

# Historical data: daily at 5 PM ET
0 17 * * 1-5 cd /path/to/project && uv run python app/scripts/collect_all_stock_data.py --type historical --period 1mo >> /tmp/stock_history.log 2>&1
```

## Monitoring

### Check Collection Status

Query the database to see recent collection runs:

```sql
SELECT
    collection_type,
    symbols_requested,
    symbols_success,
    symbols_failed,
    duration_seconds,
    started_at,
    completed_at
FROM stock_data_collection
ORDER BY started_at DESC
LIMIT 10;
```

### Check Latest Prices

```sql
SELECT
    symbol,
    price,
    change_percent,
    updated_at,
    EXTRACT(EPOCH FROM (NOW() - updated_at))/60 as minutes_ago
FROM stock_price
ORDER BY updated_at DESC
LIMIT 20;
```

### Alert on Failures

```sql
-- Check for recent failures
SELECT COUNT(*) as failed_collections
FROM stock_data_collection
WHERE started_at > NOW() - INTERVAL '1 hour'
  AND symbols_failed > symbols_success;
```

## Rate Limiting

The collector implements:
- **500ms delay** between individual symbol requests
- **1 second delay** between batches (10 symbols per batch)
- **Exponential backoff** on failures (1s, 2s, 4s)
- **Max 3 retries** per symbol

**Yahoo Finance rate limits:**
- ~2000 requests/hour for free tier
- With 500ms delays: ~120 requests/minute = 7200/hour (safe margin)

## Troubleshooting

### No Data Being Collected

1. Check if tickers exist in database:
   ```sql
   SELECT COUNT(*) FROM ticker;
   ```

2. Run manually to see errors:
   ```bash
   uv run python app/scripts/collect_all_stock_data.py --type current
   ```

3. Check logs:
   ```bash
   tail -f /tmp/stock_price_collection.log
   ```

### Slow Collection

- **Too many tickers?** Consider collecting in batches or increasing delays
- **Network issues?** Check internet connection and DNS
- **Rate limited?** Increase delays between requests

### Missing Historical Data

```bash
# Force refresh for specific period
uv run python app/scripts/collect_all_stock_data.py \
    --type historical \
    --period 1y \
    --force-refresh
```

## API Quotas

**Yahoo Finance (yfinance):**
- Free tier: ~2000 requests/hour
- No API key required
- Unofficial API (may change)

**If you hit rate limits:**
1. Increase `_min_request_interval` in `stock_data.py`
2. Reduce collection frequency
3. Consider paid alternative (Finnhub, Alpha Vantage, etc.)

## Testing

Test the collector with a small subset:

```python
# app/scripts/test_collector.py
import asyncio
from app.collectors.stock_price_collector import StockPriceCollector
from app.db.session import SessionLocal

async def test():
    collector = StockPriceCollector()
    db = SessionLocal()
    try:
        # Test with just 3 symbols
        result = await collector.collect_current_prices(
            db,
            symbols=["AAPL", "MSFT", "GOOGL"]
        )
        print(f"Success: {result['success']}, Failed: {result['failed']}")
    finally:
        db.close()

asyncio.run(test())
```

## Next Steps

1. Set up monitoring alerts (e.g., email on failures)
2. Add Prometheus metrics for collection stats
3. Create dashboard to visualize collection health
4. Implement partial collection (only active/popular tickers during off-hours)
