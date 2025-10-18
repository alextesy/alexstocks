# Stock Data Collection - Quick Start Guide

## 🚀 Get All Stock Data for All Tickers

### One-Time Collection

```bash
# Get current prices for ALL tickers in database
make collect-stock-prices

# Or run directly:
uv run python app/scripts/collect_all_stock_data.py --type current
```

### Test First (Recommended)

```bash
# Test with 3 sample tickers
make test-stock-collection
```

## ⏰ Set Up 15-Minute Automated Collection

### Quick Setup (Cron)

```bash
# Automatically set up cron job
make setup-stock-cron

# Verify it's running
crontab -l

# Watch the logs
tail -f /tmp/stock_price_collection.log
```

### Manual Cron Setup

```bash
# Edit crontab
crontab -e

# Add this line (every 15 minutes):
*/15 * * * * cd /Users/alex/market-pulse-v2 && /usr/bin/env uv run python app/scripts/collect_all_stock_data.py --type current >> /tmp/stock_price_collection.log 2>&1
```

## 📊 Collection Options

```bash
# Current prices only
make collect-stock-prices

# Historical data (last month)
make collect-historical-data

# Both current + historical
make collect-both-stock-data

# Custom period
uv run python app/scripts/collect_all_stock_data.py --type historical --period 1y

# Force refresh (delete and re-collect)
uv run python app/scripts/collect_all_stock_data.py --type historical --force-refresh
```

## 🎯 Smart Scheduling

### During Market Hours (More Frequent)

```bash
# Every 15 minutes during market hours (9:30 AM - 4 PM ET, Mon-Fri)
*/15 9-16 * * 1-5 cd /Users/alex/market-pulse-v2 && uv run python app/scripts/collect_all_stock_data.py --type current >> /tmp/stock_prices.log 2>&1
```

### Outside Market Hours (Less Frequent)

```bash
# Every hour outside market hours
0 * * * 0,6 cd /Users/alex/market-pulse-v2 && uv run python app/scripts/collect_all_stock_data.py --type current >> /tmp/stock_prices.log 2>&1
0 0-8,17-23 * * 1-5 cd /Users/alex/market-pulse-v2 && uv run python app/scripts/collect_all_stock_data.py --type current >> /tmp/stock_prices.log 2>&1
```

### Daily Historical Update

```bash
# Every day at 5 PM ET (after market close)
0 17 * * 1-5 cd /Users/alex/market-pulse-v2 && uv run python app/scripts/collect_all_stock_data.py --type historical --period 1mo >> /tmp/stock_history.log 2>&1
```

## 🔍 Monitoring

### Check Collection Status

```bash
# View logs
tail -f /tmp/stock_price_collection.log

# Or check in database
psql $DATABASE_URL -c "SELECT * FROM stock_data_collection ORDER BY started_at DESC LIMIT 5;"
```

### Check Latest Prices

```bash
psql $DATABASE_URL -c "SELECT symbol, price, change_percent, updated_at FROM stock_price ORDER BY updated_at DESC LIMIT 10;"
```

## 🛠️ Troubleshooting

### Test Collection

```bash
make test-stock-collection
```

### Check How Many Tickers You Have

```bash
psql $DATABASE_URL -c "SELECT COUNT(*) FROM ticker;"
```

### Run Tests

```bash
make test-stock
```

### Remove Cron Job

```bash
crontab -l | grep -v 'collect_all_stock_data.py' | crontab -
```

## 📖 Full Documentation

See [docs/STOCK_DATA_COLLECTION.md](docs/STOCK_DATA_COLLECTION.md) for complete details including:
- Systemd timer setup (Linux servers)
- Cloud scheduler options (AWS, GCP, Heroku)
- Rate limiting details
- Advanced monitoring
- Troubleshooting guide

## ✅ Summary

**To collect all stock data every 15 minutes:**

1. Test it works: `make test-stock-collection`
2. Set up cron: `make setup-stock-cron`
3. Verify: `crontab -l`
4. Monitor: `tail -f /tmp/stock_price_collection.log`

Done! 🎉
