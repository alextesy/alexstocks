# Reddit Scraper - Quick Start Guide

## 🎯 What Is This?

A **production-ready Reddit scraper** that consolidates all previous implementations into one comprehensive service for scraping r/wallstreetbets daily/weekend discussion threads.

## ✨ Key Features

- ✅ **Incremental Mode**: 15-minute cron jobs (only new comments)
- ✅ **Backfill Mode**: Historical data by date range
- ✅ **Advanced Rate Limiting**: 90 QPM with exponential backoff + jitter
- ✅ **Stateful Tracking**: Uses `last_seen_created_utc` for efficiency
- ✅ **Idempotent**: Safe to run multiple times, no duplicates
- ✅ **Batch Saving**: Commits every 200 comments (crash-resistant)
- ✅ **Comprehensive Logging**: Full observability with structured logs
- ✅ **Extensible**: Easy to add new subreddits/sources

## 🚀 Quick Start

### 1. Test Manually

```bash
# Check status (should work even with no data)
make reddit-scrape-status

# Run incremental scraper
make reddit-scrape-incremental

# Check logs
tail -f /Users/alex/logs/market-pulse/prod-scraping.log
```

### 2. Setup Cron (15-minute pipeline)

```bash
# Create log directory
mkdir -p /Users/alex/logs/market-pulse

# Edit crontab
crontab -e

# Add these lines:
PATH=/Users/alex/miniconda3/bin:/usr/local/bin:/usr/bin:/bin
*/15 * * * * cd /Users/alex/market-pulse-v2 && make reddit-scrape-incremental >> /Users/alex/logs/market-pulse/prod-scraping.log 2>&1

# Save and verify
crontab -l
```

### 3. Backfill Historical Data (optional)

```bash
# Backfill last 7 days
make reddit-scrape-backfill START=2025-09-24 END=2025-09-30

# Backfill specific month
make reddit-scrape-backfill START=2025-09-01 END=2025-09-30
```

## 📋 Usage

### CLI Commands

```bash
# Incremental scraping (for cron)
python -m ingest.reddit_scraper_cli --mode incremental

# Backfill by date range
python -m ingest.reddit_scraper_cli --mode backfill \
  --start 2025-09-01 --end 2025-09-30

# Check status
python -m ingest.reddit_scraper_cli --mode status

# Verbose logging
python -m ingest.reddit_scraper_cli --mode incremental --verbose
```

### Make Targets

```bash
make reddit-scrape-incremental  # Incremental mode
make reddit-scrape-backfill START=2025-09-01 END=2025-09-30  # Backfill
make reddit-scrape-status  # Status check
```

## 📊 What It Does

### Incremental Mode (Every 15 Minutes)

1. **Discovers** latest WSB daily/weekend discussion threads
2. **Filters** for new comments using `last_seen_created_utc` (super fast!)
3. **Scrapes** only new comments (typically 50-500 per run)
4. **Links** comments to stock tickers automatically
5. **Saves** in batches of 200 (resilient to crashes)
6. **Logs** comprehensive metrics (threads, comments, articles, links, duration)

### Backfill Mode (Historical Data)

1. **Iterates** through date range (day by day)
2. **Discovers** threads for each date by created_utc
3. **Scrapes** all comments (using ID-based filtering)
4. **Handles** rate limits gracefully
5. **Saves** progress incrementally

## 🔧 Configuration

### Environment Variables

Required in `.env`:
```bash
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=MarketPulse/1.0 by YourUsername
```

### Rate Limiting

- **Default QPM**: 90 requests/minute (safe under 100 limit)
- **Batch saves**: Every 200 comments
- **Exponential backoff**: 30s → 60s → 120s with 0-5s jitter
- **Max retries**: 3 attempts before giving up

### Performance

| Thread Size | New Comments | Duration |
|------------|--------------|----------|
| Small (500) | 50 | ~25s |
| Medium (2000) | 200 | ~110s |
| Large (5000+) | 500 | ~360s |

## 📝 Logs

### Log Locations

```bash
# Main scraper logs
/Users/alex/logs/market-pulse/prod-scraping.log

# Sentiment analysis logs (separate job)
/Users/alex/logs/market-pulse/prod-sentiment.log
```

### Log Format

```
2025-10-02 14:30:15 - ingest.reddit_scraper - INFO - 🚀 Starting INCREMENTAL scraping...
2025-10-02 14:30:20 - ingest.reddit_scraper - INFO - ✅ Extracted 2380 valid comments in 2.8s
2025-10-02 14:30:21 - ingest.reddit_scraper - INFO - 🕐 Using last_seen filter: 2025-10-02 14:15:30
2025-10-02 14:30:22 - ingest.reddit_scraper - INFO - 🔄 Processing 145 new comments...
2025-10-02 14:30:30 - ingest.reddit_scraper - INFO - 💾 Final save: 145 comments processed
2025-10-02 14:30:31 - ingest.reddit_scraper - INFO - ✅ Thread complete: 145 articles, 387 links
2025-10-02 14:30:40 - ingest.reddit_scraper - INFO - 🎉 Incremental scrape complete!
```

## 🛠️ Troubleshooting

### Common Issues

**"No tickers found in database"**
```bash
make seed-tickers
```

**"Reddit credentials not configured"**
```bash
# Check .env file has:
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
```

**Rate limit warnings (⚠️)**
- Normal! The scraper handles this automatically
- It will backoff and retry

**Cron not running**
```bash
# Check crontab
crontab -l

# Check PATH is set in crontab
# Must include path to python/uv

# Check logs for errors
tail -f /Users/alex/logs/market-pulse/prod-scraping.log
```

## 📚 Full Documentation

See [`docs/REDDIT_SCRAPER.md`](REDDIT_SCRAPER.md) for:
- Complete architecture details
- PRD compliance matrix
- Advanced configuration
- Extensibility guide
- Performance tuning
- Migration from old scrapers

## 🆚 Comparison with Old Scrapers

### Before (Multiple Scrapers)

- `reddit_robust_scraper.py` - Rate limiting + batch saves
- `reddit_incremental_scraper.py` - Incremental logic
- `reddit_full_scraper.py` - Full comment tree
- `reddit_discussion_scraper.py` - PRAW wrapper
- **Total**: 4+ files, overlapping functionality, no backfill

### Now (Unified Scraper)

- `reddit_scraper.py` - **ALL features in one**
- `reddit_scraper_cli.py` - Clean CLI interface
- **Bonus**: Backfill mode, advanced rate limiting, stateful tracking

## ✅ Checklist for Production

- [ ] Test manually: `make reddit-scrape-incremental`
- [ ] Check status: `make reddit-scrape-status`
- [ ] Verify logs: `tail /Users/alex/logs/market-pulse/prod-scraping.log`
- [ ] Seed tickers: `make seed-tickers` (if needed)
- [ ] Test idempotency: Run twice, second should process 0 comments
- [ ] Setup cron: Edit `crontab -e`, add 15-min job
- [ ] Monitor for 24h: Check logs for errors
- [ ] Optional: Run backfill for historical data

## 🎉 Next Steps

Once the scraper is running:

1. **Sentiment Analysis** (separate job):
   ```bash
   # Add to cron (offset by 2 minutes)
   2,17,32,47 * * * * cd /Users/alex/market-pulse-v2 && make analyze-sentiment-recent
   ```

2. **Stock Prices** (market hours only):
   ```bash
   # Add to cron
   */15 6-13 * * 1-5 cd /Users/alex/market-pulse-v2 && make collect-stock-prices
   ```

3. **Monitor Dashboard**:
   - Visit `http://localhost:8000/tickers` to see ticker sentiment
   - Check `http://localhost:8000/articles` for recent articles

4. **Prometheus Metrics** (future):
   - Add metrics export endpoint
   - Setup Grafana dashboards
   - Configure alerts

## 📞 Support

Need help?
1. Check `docs/REDDIT_SCRAPER.md`
2. Check logs: `tail -f /Users/alex/logs/market-pulse/prod-scraping.log`
3. Run with `--verbose` flag
4. Open an issue with logs

## 📄 Files

**Core Files:**
- [`ingest/reddit_scraper.py`](../ingest/reddit_scraper.py) - Main scraper class
- [`ingest/reddit_scraper_cli.py`](../ingest/reddit_scraper_cli.py) - CLI interface
- [`docs/REDDIT_SCRAPER.md`](REDDIT_SCRAPER.md) - Full documentation
- [`docs/cron-production-scraper.txt`](cron-production-scraper.txt) - Cron config

**Legacy Files (still available):**
- `ingest/reddit_robust_scraper.py`
- `ingest/reddit_incremental_scraper.py`
- `ingest/reddit_full_scraper.py`
- `ingest/reddit_discussion_scraper.py` (still used as base)

**Database Models:**
- `app/db/models.py` - Article, RedditThread, ArticleTicker, Ticker

---

**🚀 Ready to roll? Start with:** `make reddit-scrape-incremental`
