# Stock Price Collection Cron Setup

This document describes how to set up the automated stock price collection job to run every 15 minutes.

## Overview

The top 50 stock price collection job runs every 15 minutes to keep homepage prices fresh. It:

1. Identifies the top 50 most active tickers (by 24h article count)
2. Fetches latest prices from Yahoo Finance API
3. Validates data (rejects NaN, zero, negative prices)
4. Updates the `stock_price` table with fresh data
5. Logs results for monitoring

## Cron Schedule

```bash
*/15 * * * * cd /opt/market-pulse-v2 && make collect-stock-prices-top50 >> /var/log/market_pulse/price_refresh.log 2>&1
```

### Breaking Down the Schedule

- `*/15 * * * *` - Every 15 minutes
- `cd /path/to/market-pulse-v2` - Navigate to project directory
- `/usr/bin/make collect-stock-prices-top50` - Run the collection job
- `>> /var/log/market_pulse/price_refresh.log 2>&1` - Append output to log file

## Setup Instructions

### Local Development

For local development, you can run the job manually:

```bash
make collect-stock-prices-top50
```

### EC2 Production Setup

1. **Create log directory:**
   ```bash
   sudo mkdir -p /var/log/market_pulse
   sudo chown ubuntu:ubuntu /var/log/market_pulse
   ```

2. **Set up log rotation** to prevent logs from growing too large:
   ```bash
   sudo tee /etc/logrotate.d/market-pulse <<EOF
   /var/log/market_pulse/*.log {
       daily
       rotate 7
       compress
       delaycompress
       missingok
       notifempty
       create 0644 ubuntu ubuntu
   }
   EOF
   ```

3. **Edit crontab:**
   ```bash
   crontab -e
   ```

4. **Add the cron entry** (update path to your installation):
   ```bash
   # Stock Price Collection - Top 50 tickers every 15 minutes
   */15 * * * * cd /home/ubuntu/market-pulse-v2 && /usr/bin/make collect-stock-prices-top50 >> /var/log/market_pulse/price_refresh.log 2>&1
   ```

5. **Verify cron is set up:**
   ```bash
   crontab -l | grep collect-stock-prices-top50
   ```

6. **Monitor initial runs:**
   ```bash
   tail -f /var/log/market_pulse/price_refresh.log
   ```

## Monitoring

### Check Recent Runs

```bash
tail -n 100 /var/log/market_pulse/price_refresh.log
```

### Check Cron Status

```bash
# View cron service status
sudo systemctl status cron

# View recent cron execution logs
sudo journalctl -u cron | tail -n 50
```

### Database Monitoring

Check when prices were last updated:

```sql
SELECT
    symbol,
    price,
    updated_at,
    AGE(NOW(), updated_at) as age
FROM stock_price
ORDER BY updated_at DESC
LIMIT 10;
```

Count stale prices (>30 minutes old):

```sql
SELECT COUNT(*) as stale_count
FROM stock_price
WHERE updated_at < NOW() - INTERVAL '30 minutes';
```

## Performance Expectations

- **Duration:** ~5-15 seconds for 50 tickers (depends on API response times)
- **Success Rate:** ≥95% (occasional API failures are normal)
- **Data Freshness:** All top 50 tickers should be ≤15 minutes old

## Troubleshooting

### Issue: Cron not running

**Check cron service:**
```bash
sudo systemctl status cron
sudo systemctl start cron  # if stopped
```

**Verify cron syntax:**
```bash
crontab -l
```

### Issue: Rate limiting errors

**Symptoms:** `Too Many Requests` errors in logs

**Solution:** The retry logic with exponential backoff should handle this automatically. If persistent:
- Increase batch delay in `stock_price_service.py`
- Reduce batch size from 5 to 3

### Issue: No log output

**Check log directory permissions:**
```bash
ls -la /var/log/market_pulse/
```

**Check cron environment:**
Cron runs with minimal environment. Ensure paths are absolute.

### Issue: Database connection errors

**Check database is running:**
```bash
docker ps | grep postgres
```

**Verify database connection in environment:**
```bash
cd /home/ubuntu/market-pulse-v2
uv run python -c "from app.db.session import SessionLocal; db = SessionLocal(); print('DB OK')"
```

## Alignment with Reddit Scraping

The stock price collection runs every 15 minutes, aligned with the Reddit scraping schedule. This ensures that:

1. Homepage always shows fresh prices for active tickers
2. Resource usage is distributed evenly
3. Data collection intervals are predictable

## Testing

Test the cron job manually before deploying:

```bash
# Test the command
cd /home/ubuntu/market-pulse-v2 && /usr/bin/make collect-stock-prices-top50

# Verify it ran successfully
echo $?  # Should output 0

# Check the database was updated
# (use SQL query from Monitoring section)
```

## Disabling the Cron Job

To temporarily disable:

```bash
crontab -e
# Comment out the line:
# */15 * * * * cd /home/ubuntu/market-pulse-v2 && /usr/bin/make collect-stock-prices-top50 ...
```

To permanently remove:

```bash
crontab -e
# Delete the line entirely
```
