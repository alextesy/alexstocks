# EC2 Production Cron Setup

This guide explains how to set up and manage cron jobs on the EC2 production server.

## Quick Setup

On your EC2 instance, run:

```bash
cd /opt/market-pulse-v2
./scripts/setup-ec2-cron.sh
```

This will install all production cron jobs automatically.

## Cron Schedule Overview

All times are in **UTC** (EC2 default timezone).

| Job | Frequency | Description | Log File |
|-----|-----------|-------------|----------|
| Reddit Scraping | Every 15 min | Incremental scraping of daily discussion threads | `reddit-scraping.log` |
| Sentiment Analysis | Every 15 min | Analyze sentiment of newly scraped comments | `sentiment-analysis.log` |
| Stock Prices | Every 15 min (market hours) | Current prices during 6:30 AM - 1:00 PM PT | `stock-prices.log` |
| Historical Data | Daily at 2:00 PM PT | 1 month of historical OHLCV data | `historical-data.log` |
| Weekend Prices | Hourly | Stock prices on Sat/Sun | `stock-prices-weekend.log` |
| Daily Status | Daily at 4:00 AM UTC | Scraping status check | `daily-status.log` |

## Market Hours

- **Pacific Time**: 6:30 AM - 1:00 PM PT (Mon-Fri)
- **UTC Time**: 13:30 - 20:00 UTC (Mon-Fri)

The cron jobs use UTC times since EC2 runs on UTC by default.

## Manual Operations

### View Current Cron Jobs
```bash
crontab -l
```

### Edit Cron Jobs Manually
```bash
crontab -e
```

### Install Cron Jobs from File
```bash
cd /opt/market-pulse-v2
crontab cron-ec2-production.txt
```

### Remove All Cron Jobs
```bash
crontab -r
```

## Monitoring Logs

### Real-time Monitoring
```bash
# Reddit scraping
tail -f /var/log/market-pulse/reddit-scraping.log

# Sentiment analysis
tail -f /var/log/market-pulse/sentiment-analysis.log

# Stock prices
tail -f /var/log/market-pulse/stock-prices.log

# Historical data
tail -f /var/log/market-pulse/historical-data.log
```

### Check Recent Logs
```bash
# Last 50 lines of Reddit scraping
tail -50 /var/log/market-pulse/reddit-scraping.log

# Last 50 lines of sentiment analysis
tail -50 /var/log/market-pulse/sentiment-analysis.log

# Check for errors
grep -i error /var/log/market-pulse/*.log
```

### View All Log Files
```bash
ls -lh /var/log/market-pulse/
```

## Manual Testing

Before relying on cron jobs, test each command manually:

### Test Reddit Scraping
```bash
cd /opt/market-pulse-v2
make reddit-scrape-incremental
```

### Test Sentiment Analysis
```bash
cd /opt/market-pulse-v2
make analyze-sentiment-reddit
```

### Test Stock Price Collection
```bash
cd /opt/market-pulse-v2
make collect-stock-prices-smart
```

### Check Scraping Status
```bash
cd /opt/market-pulse-v2
make reddit-scrape-status
```

## Troubleshooting

### Cron Jobs Not Running

1. **Check if cron service is running:**
   ```bash
   sudo systemctl status cron
   ```

2. **Check cron execution logs:**
   ```bash
   sudo grep CRON /var/log/syslog | tail -50
   ```

3. **Check for ubuntu user cron executions:**
   ```bash
   sudo grep "CRON.*ubuntu" /var/log/syslog | tail -30
   ```

### Jobs Running but Failing

1. **Check the application logs:**
   ```bash
   cat /var/log/market-pulse/reddit-scraping.log
   cat /var/log/market-pulse/sentiment-analysis.log
   ```

2. **Common issues:**
   - `uv: not found` - Wrong PATH in crontab
   - `No module named X` - Virtual environment issues
   - Database connection errors - Check `.env` file
   - Reddit API errors - Check credentials

### Environment Issues

Cron runs with a limited environment. Ensure:

1. **PATH includes uv:**
   ```bash
   which uv  # Should be /home/ubuntu/.local/bin/uv
   ```

2. **Working directory is set:**
   All cron jobs include `cd /opt/market-pulse-v2`

3. **Environment variables loaded:**
   The `.env` file is loaded by the scripts themselves

## Log Rotation

To prevent logs from growing too large, set up log rotation:

```bash
sudo nano /etc/logrotate.d/market-pulse
```

Add:
```
/var/log/market-pulse/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0644 ubuntu ubuntu
}
```

Test log rotation:
```bash
sudo logrotate -f /etc/logrotate.d/market-pulse
```

## Cron Job Details

### Reddit Scraping (Every 15 minutes)
```cron
*/15 * * * * cd /opt/market-pulse-v2 && make reddit-scrape-incremental >> /var/log/market-pulse/reddit-scraping.log 2>&1
```
- Runs `uv run python -m ingest.reddit_scraper_cli --mode incremental`
- Scrapes latest comments from daily discussion threads
- Automatically handles rate limiting
- Saves incrementally to avoid data loss

### Sentiment Analysis (Every 15 minutes)
```cron
*/15 * * * * cd /opt/market-pulse-v2 && make analyze-sentiment-reddit >> /var/log/market-pulse/sentiment-analysis.log 2>&1
```
- Runs `uv run python app/jobs/analyze_sentiment.py --source reddit`
- Analyzes sentiment for newly scraped Reddit comments
- Uses dual-model approach (FinBERT + VADER)
- Only processes articles without sentiment

### Stock Prices (Market Hours)
```cron
*/15 13-20 * * 1-5 cd /opt/market-pulse-v2 && make collect-stock-prices-smart >> /var/log/market-pulse/stock-prices.log 2>&1
```
- Runs during market hours (6:30 AM - 1:00 PM PT)
- Uses smart collection (filters inactive tickers)
- Updates current prices for all active tickers

### Historical Data (Daily)
```cron
0 21 * * 1-5 cd /opt/market-pulse-v2 && uv run python app/scripts/collect_stock_data_smart.py --type historical --period 1mo >> /var/log/market-pulse/historical-data.log 2>&1
```
- Runs once daily at 2:00 PM PT (after market close)
- Collects 1 month of historical OHLCV data
- Updates all active tickers

## Best Practices

1. **Monitor logs regularly** - Check for errors and failures
2. **Test manually first** - Always test commands before adding to cron
3. **Use absolute paths** - Always specify full paths to files and commands
4. **Log everything** - Redirect both stdout and stderr to log files (`>> file.log 2>&1`)
5. **Set working directory** - Use `cd /opt/market-pulse-v2` before commands
6. **Handle errors gracefully** - Scripts should handle failures without crashing

## Files

- **Cron configuration**: `/opt/market-pulse-v2/cron-ec2-production.txt`
- **Setup script**: `/opt/market-pulse-v2/scripts/setup-ec2-cron.sh`
- **Log directory**: `/var/log/market-pulse/`
- **Application directory**: `/opt/market-pulse-v2/`

## Support

For issues:
1. Check logs in `/var/log/market-pulse/`
2. Test commands manually
3. Verify environment variables
4. Check database connectivity
5. Review cron execution logs in `/var/log/syslog`
