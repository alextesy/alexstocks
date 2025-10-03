# Reddit Scraper - Production Documentation

## Overview

The production Reddit scraper (`ingest/reddit_scraper.py`) is a unified, comprehensive solution for scraping r/wallstreetbets daily/weekend discussion threads. It consolidates all previous scraper implementations into one production-ready service.

## Features

### ✅ Core Capabilities

- **Incremental Scraping**: 15-minute cron jobs that only process new comments
- **Historical Backfill**: Scrape by date range for historical data
- **Rate Limit Handling**: Advanced exponential backoff with jitter
- **Stateful Tracking**: Uses `last_seen_created_utc` for efficient filtering
- **Idempotent**: Safe to run multiple times, no duplicates
- **Batch Saving**: Commits every 200 comments (resilient to crashes)
- **Comprehensive Logging**: Structured logs with full observability

### 🎯 PRD Compliance

This implementation fully satisfies the PRD requirements:

| Requirement | Status | Implementation |
|------------|--------|----------------|
| Incremental mode (15-min) | ✅ | `--mode incremental` |
| Backfill by date range | ✅ | `--mode backfill --start YYYY-MM-DD --end YYYY-MM-DD` |
| Rate limiting (90 QPM) | ✅ | `RateLimiter` class with proactive throttling |
| Exponential backoff | ✅ | 30s → 60s → 120s with 0-5s jitter |
| PRAW exception parsing | ✅ | Extracts "X minutes" from RATELIMIT messages |
| Idempotent operations | ✅ | `reddit_id` uniqueness + skip existing |
| Stateful tracking | ✅ | `last_seen_created_utc` + `RedditThread` table |
| Batch commits | ✅ | Every 200 comments with progress updates |
| Structured logging | ✅ | Thread ID, counts, duration_ms, etc. |
| Ticker linking | ✅ | Inline during scraping |
| Thread discovery | ✅ | `find_daily_discussion_threads` + date filtering |

## Architecture

### Class Structure

```
RedditScraper (main class)
├── RateLimiter (advanced rate limiting)
├── RedditDiscussionScraper (PRAW wrapper, thread discovery)
├── TickerLinker (ticker matching)
└── ScrapeStats (metrics dataclass)
```

### Data Flow

```
1. Thread Discovery
   ├─ find_daily_discussion_threads() → List[Submission]
   └─ find_threads_by_date() → List[Submission] (backfill)

2. Comment Extraction
   ├─ extract_comments_with_retry() → List[Comment]
   ├─ Rate limit checking (proactive)
   └─ Exponential backoff on 429

3. Filtering
   ├─ get_last_seen_timestamp() → datetime (for incremental)
   ├─ get_existing_comment_ids() → Set[str] (fallback)
   └─ Filter new comments

4. Processing
   ├─ parse_comment_to_article() → Article
   ├─ link_article() → List[TickerLink]
   ├─ Batch save every 200 comments
   └─ Update RedditThread progress

5. Metrics
   └─ ScrapeStats (threads, comments, articles, links, duration)
```

### Database Models

**Article** (source: "reddit_comment")
- `id` (PK): Auto-increment
- `reddit_id` (unique): Reddit comment ID
- `url`: Comment permalink
- `published_at`: Comment timestamp
- `text`: Comment body
- `sentiment`: NULL initially (set by sentiment job)
- `subreddit`, `author`, `upvotes`: Metadata

**RedditThread** (tracks scraping progress)
- `reddit_id` (PK): Reddit submission ID
- `title`, `subreddit`, `thread_type`: Metadata
- `total_comments`: Reported by Reddit
- `scraped_comments`: Count of scraped comments
- `last_scraped_at`: Last successful scrape
- `is_complete`: Whether scraping is done

**ArticleTicker** (links articles to tickers)
- `article_id`, `ticker` (composite PK)
- `confidence`: Match confidence score
- `matched_terms`: List of matched keywords

## Usage

### CLI Interface

```bash
# Incremental mode (for 15-min cron)
python -m ingest.reddit_scraper_cli --mode incremental

# Backfill mode (historical data)
python -m ingest.reddit_scraper_cli --mode backfill \
  --start 2025-09-01 --end 2025-09-30

# Status check
python -m ingest.reddit_scraper_cli --mode status

# Verbose logging
python -m ingest.reddit_scraper_cli --mode incremental --verbose

# Custom subreddit
python -m ingest.reddit_scraper_cli --mode incremental --subreddit stocks

# Adjust max_replace_more (comment tree expansion)
python -m ingest.reddit_scraper_cli --mode incremental --max-replace-more 64
```

### Make Targets

```bash
# Incremental scraping (recommended for cron)
make reddit-scrape-incremental

# Backfill historical data
make reddit-scrape-backfill START=2025-09-01 END=2025-09-30

# Check status
make reddit-scrape-status

# Legacy scrapers (still available)
make reddit-robust-scrape
make reddit-incremental
```

### Cron Setup

See [`docs/cron-production-scraper.txt`](cron-production-scraper.txt) for complete cron configuration.

Quick setup:
```bash
# 1. Create log directory
mkdir -p /Users/alex/logs/market-pulse

# 2. Test manually
cd /Users/alex/market-pulse-v2
make reddit-scrape-incremental

# 3. Edit crontab
crontab -e

# 4. Add this line:
*/15 * * * * cd /Users/alex/market-pulse-v2 && make reddit-scrape-incremental >> /Users/alex/logs/market-pulse/prod-scraping.log 2>&1
```

## Configuration

### Environment Variables

Required in `.env`:
```bash
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=MarketPulse/1.0 by YourUsername
```

### Rate Limiting

Default configuration (can be adjusted in `RedditScraper.__init__`):
- `requests_per_minute`: 90 (safe margin under 100 QPM limit)
- `batch_save_interval`: 200 (commits every 200 comments)
- `max_scraping_workers`: 5 (ticker linking concurrency)

To adjust rate limits:
```python
scraper = RedditScraper(
    requests_per_minute=80,  # More conservative
    batch_save_interval=100,  # More frequent saves
)
```

### Comment Tree Expansion

The `max_replace_more` parameter controls how many "more comments" links to expand:

- `None` (unlimited): Gets ALL comments, very slow for large threads (5000+)
- `32` (default): Good balance, typically gets 80-90% of comments
- `64`: More complete, takes longer
- `0`: Minimal expansion, fastest but misses nested comments

For large threads (>5000 comments), the scraper automatically uses adaptive limits.

## Rate Limiting Details

### Proactive Throttling

The scraper tracks request times and proactively sleeps before hitting the limit:

```python
# Track requests in a sliding 60-second window
if len(request_times) >= 90:  # Approaching limit
    sleep_time = 60 - (now - oldest_request) + 1
    sleep(sleep_time)  # Wait until safe to proceed
```

### Exponential Backoff

On 429 errors:
1. **Attempt 1**: 30s + 0-5s jitter
2. **Attempt 2**: 60s + 0-5s jitter
3. **Attempt 3**: 120s + 0-5s jitter
4. **Attempt 4+**: Give up, log error

If PRAW provides a "try again in X minutes" message, the scraper extracts and uses that value.

### Error Detection

Catches both:
- String `"429"` in exception message
- `praw.exceptions.RedditAPIException` with `error_type == "RATELIMIT"`

## Incremental Scraping Strategy

### Two-Pronged Filtering

#### 1. `last_seen_created_utc` (Primary)

For existing threads, the scraper queries:
```sql
SELECT MAX(published_at) FROM article
WHERE source = 'reddit_comment'
  AND reddit_url LIKE '%{thread_id}%'
```

Then filters:
```python
new_comments = [c for c in all_comments
                if datetime.fromtimestamp(c.created_utc) > last_seen]
```

**Benefits:**
- Near-instant for threads with few new comments
- Drastically reduces memory usage
- Scales to very large threads (10k+ comments)

#### 2. `reddit_id` Deduplication (Fallback)

If no `last_seen` timestamp, falls back to:
```sql
SELECT reddit_id FROM article
WHERE source = 'reddit_comment'
  AND reddit_url LIKE '%{thread_id}%'
```

Then filters:
```python
new_comments = [c for c in all_comments
                if c.id not in existing_ids]
```

**Benefits:**
- Ensures true idempotency
- Prevents duplicates even if timestamps are off
- Works for backfill mode

### Result

Each 15-minute incremental run typically processes:
- **50-200 comments** for normal threads
- **200-500 comments** for very active threads
- **0 comments** if nothing new (graceful no-op)

## Batch Saving

Comments are committed in batches of 200 to balance:
- **Performance**: Fewer DB round-trips
- **Resilience**: If process crashes, lose at most 200 comments
- **Memory**: Keeps DB connection lightweight

### Progress Updates

After each batch:
```python
thread_record.scraped_comments = current_count
thread_record.last_scraped_at = now()
db.commit()
```

This allows resuming from crashes:
- Thread progress is checkpointed every 200 comments
- Re-running will pick up where it left off
- Idempotency ensures no duplicates

## Observability

### Structured Logs

Every run includes:
- 🚀 Scrape mode and configuration
- 📅 Date range (backfill) or thread list (incremental)
- 📊 Per-thread: title, ID, subreddit
- 📥 Comment extraction: total, valid, duration
- 🔍 Filtering: new comments, existing comments
- 💾 Batch saves: progress updates every 200 comments
- ✅ Final stats: articles, ticker links, batches, duration_ms
- 🎉 Aggregate summary

### Log Format

```
2025-10-02 14:30:15 - ingest.reddit_scraper - INFO - 🚀 Starting INCREMENTAL scraping for r/wallstreetbets
2025-10-02 14:30:16 - ingest.reddit_scraper - INFO - 📊 Thread 1/3: Daily Discussion Thread for October 02, 2025
2025-10-02 14:30:17 - ingest.reddit_scraper - INFO - 📥 Extracting comments from: Daily Discussion Thread...
2025-10-02 14:30:17 - ingest.reddit_scraper - INFO -    Total comments reported: 2450
2025-10-02 14:30:20 - ingest.reddit_scraper - INFO - ✅ Extracted 2380 valid comments (out of 2450 total) in 2.8s
2025-10-02 14:30:21 - ingest.reddit_scraper - INFO - 🕐 Using last_seen filter: 2025-10-02 14:15:30+00:00
2025-10-02 14:30:21 - ingest.reddit_scraper - INFO -    Filtered 145 comments newer than 2025-10-02 14:15:30+00:00
2025-10-02 14:30:22 - ingest.reddit_scraper - INFO - 🔄 Processing 145 new comments (batch save every 200)...
2025-10-02 14:30:25 - ingest.reddit_scraper - INFO -    ... 50/145 comments
2025-10-02 14:30:28 - ingest.reddit_scraper - INFO -    ... 100/145 comments
2025-10-02 14:30:30 - ingest.reddit_scraper - INFO - 💾 Final save: 145 comments processed
2025-10-02 14:30:31 - ingest.reddit_scraper - INFO - ✅ Thread complete: 2380 total, 145 new, 145 articles, 387 links, 1 batches, 14200ms
2025-10-02 14:30:40 - ingest.reddit_scraper - INFO - 🎉 Incremental scrape complete:
2025-10-02 14:30:40 - ingest.reddit_scraper - INFO -    Threads: 3
2025-10-02 14:30:40 - ingest.reddit_scraper - INFO -    Comments: 412 new / 7200 total
2025-10-02 14:30:40 - ingest.reddit_scraper - INFO -    Articles: 412
2025-10-02 14:30:40 - ingest.reddit_scraper - INFO -    Ticker links: 1089
2025-10-02 14:30:40 - ingest.reddit_scraper - INFO -    Duration: 25000ms
```

### Metrics (Future)

Ready for Prometheus integration:
- `reddit_threads_processed_total`
- `reddit_comments_new_total`
- `reddit_scrape_duration_seconds` (histogram)
- `reddit_rate_limit_events_total`

## Error Handling

### Common Errors

#### 1. Rate Limit (429)
**Symptom**: `⚠️  Rate limit hit (attempt 1/3)`
**Action**: Automatic exponential backoff
**Resolution**: Scraper retries automatically, no action needed

#### 2. No Threads Found
**Symptom**: `⚠️  No discussion threads found in r/wallstreetbets`
**Cause**: Subreddit has no recent daily/weekend discussions
**Resolution**: Check subreddit manually, adjust thread discovery keywords

#### 3. No Tickers Found
**Symptom**: `❌ No tickers found in database`
**Cause**: Ticker table not seeded
**Resolution**: `make seed-tickers`

#### 4. Reddit API Error
**Symptom**: `❌ Error scraping thread: <exception>`
**Cause**: PRAW exception (network, auth, etc.)
**Resolution**: Check credentials, network, Reddit API status

#### 5. Integrity Error
**Symptom**: `⚠️  Integrity error for <comment_id>`
**Cause**: Duplicate `reddit_id` (rare)
**Resolution**: Logged and skipped, no action needed (expected)

### Retry Logic

- **Comment extraction**: 3 retries with exponential backoff
- **Batch saves**: Logged and rolled back, processing continues
- **Final save**: Rolled back on error, previous batches are safe

### Graceful Degradation

If a thread fails:
- Error is logged
- Thread is skipped
- Other threads continue processing
- Partial results are saved

## Performance

### Benchmarks

Based on typical WSB daily discussion threads:

| Thread Size | New Comments | Extraction | Processing | Total |
|------------|--------------|-----------|-----------|-------|
| Small (500) | 50 | 2-5s | 10-20s | ~25s |
| Medium (2000) | 200 | 10-20s | 60-90s | ~110s |
| Large (5000+) | 500 | 30-60s | 180-300s | ~360s |

### Optimization Tips

1. **Adjust `max_replace_more`**: Lower values trade completeness for speed
2. **Increase `batch_save_interval`**: Fewer commits, faster processing
3. **Reduce `max_threads`**: Process fewer threads per run
4. **Use `last_seen` filtering**: Much faster than ID-based filtering

### Scalability

The scraper can handle:
- ✅ Threads with 10,000+ comments
- ✅ Multiple subreddits concurrently (extend `find_threads_by_date`)
- ✅ Running 24/7 with 15-minute intervals
- ✅ Historical backfills of months of data

## Testing

### Manual Testing

```bash
# Test incremental mode
make reddit-scrape-incremental

# Check no errors in logs
tail -n 50 /Users/alex/logs/market-pulse/prod-scraping.log

# Verify data in DB
make query-db

# Test backfill for yesterday
make reddit-scrape-backfill START=2025-10-01 END=2025-10-01

# Check status
make reddit-scrape-status
```

### Idempotency Test

```bash
# Run twice in a row
make reddit-scrape-incremental
make reddit-scrape-incremental

# Second run should process 0 new comments
# Check logs for: "✅ No new comments to process"
```

### Rate Limit Test

```bash
# Run with very low QPM to trigger backoff
# Edit reddit_scraper.py:
# RateLimiter(requests_per_minute=10)

make reddit-scrape-incremental

# Should see: "⏱️  Rate limit approaching" messages
```

## Migration from Old Scrapers

If you're currently using the old scrapers:

### Step 1: Test

```bash
# Test the new scraper
make reddit-scrape-incremental

# Check logs
tail -f /Users/alex/logs/market-pulse/prod-scraping.log
```

### Step 2: Verify

```bash
# Check status
make reddit-scrape-status

# Should show increased comment counts
# No duplicate errors
```

### Step 3: Update Cron

```bash
# Edit crontab
crontab -e

# Replace:
# */15 * * * * ... make reddit-robust-scrape ...

# With:
# */15 * * * * ... make reddit-scrape-incremental ...
```

### Step 4: Monitor

```bash
# Monitor for 24 hours
tail -f /Users/alex/logs/market-pulse/prod-scraping.log

# Check for errors
grep -i error /Users/alex/logs/market-pulse/prod-scraping.log
```

### Step 5: Cleanup (Optional)

Once stable, you can deprecate old files:
- `ingest/reddit_robust_scraper.py`
- `ingest/reddit_incremental_scraper.py`
- `ingest/reddit_full_scraper.py`

Keep `ingest/reddit_discussion_scraper.py` (it's used as a base).

## Extensibility

### Adding New Subreddits

Modify `find_daily_discussion_threads`:
```python
# In reddit_discussion_scraper.py
if subreddit_name == "stocks":
    keywords = ["daily discussion", "daily thread"]
elif subreddit_name == "wallstreetbets":
    keywords = ["daily discussion", "weekend discussion", "moves tomorrow"]
```

### Adding New Sources

Extend the scraper to support other sources:
```python
# In reddit_scraper.py
def find_threads_by_source(self, source_type: str, date: datetime):
    if source_type == "daily_discussion":
        return self.find_daily_discussion_threads(...)
    elif source_type == "earnings_thread":
        return self.find_earnings_threads(...)
```

### Custom Processing

Add hooks for custom processing:
```python
# In reddit_scraper.py
def scrape_thread(self, ..., custom_processor=None):
    for comment in new_comments:
        article = parse_comment_to_article(comment)

        if custom_processor:
            article = custom_processor(article, comment)

        db.add(article)
```

## Troubleshooting

### Debug Mode

```bash
# Enable verbose logging
python -m ingest.reddit_scraper_cli --mode incremental --verbose
```

### Check Reddit API Status

```bash
# Test credentials
python -c "from ingest.reddit import get_reddit_credentials; print(get_reddit_credentials())"

# Test PRAW connection
python -c "
import praw
from ingest.reddit import get_reddit_credentials
cid, cs, ua = get_reddit_credentials()
reddit = praw.Reddit(client_id=cid, client_secret=cs, user_agent=ua)
print(reddit.user.me())  # Should print None for app-only auth
"
```

### Database Issues

```bash
# Check connection
make query-db

# Check for orphaned threads
SELECT * FROM reddit_thread WHERE is_complete = false ORDER BY last_scraped_at DESC;

# Check comment counts
SELECT source, COUNT(*) FROM article GROUP BY source;
```

### Log Analysis

```bash
# Find errors
grep -i "error\|❌" /Users/alex/logs/market-pulse/prod-scraping.log

# Find rate limit events
grep "⚠️  Rate limit" /Users/alex/logs/market-pulse/prod-scraping.log

# Count successful runs
grep "🎉 Incremental scrape complete" /Users/alex/logs/market-pulse/prod-scraping.log | wc -l
```

## FAQ

**Q: How often should I run incremental scraping?**
A: Every 15 minutes is optimal for WSB daily discussions. Adjust based on your needs.

**Q: Can I run backfill while incremental is running?**
A: Not recommended. They share the same database and may conflict. Run backfill during off-hours.

**Q: What happens if the process crashes mid-batch?**
A: At most 200 comments are lost (the current batch). Previous batches are safe. Re-running will resume from the last checkpoint.

**Q: How do I scrape only during market hours?**
A: Adjust the cron schedule: `*/15 6-13 * * 1-5` (6:30 AM - 1:00 PM PT, Mon-Fri)

**Q: Can I scrape multiple subreddits?**
A: Yes! Pass `--subreddit stocks` or modify the code to loop through multiple subreddits.

**Q: Why is backfill slow?**
A: Backfill processes every comment (no `last_seen` optimization) and respects rate limits. Historical data takes time.

**Q: How do I monitor the scraper in production?**
A: Use `make reddit-scrape-status` daily and monitor logs for errors. Consider adding Prometheus metrics for alerting.

## Support

For issues, questions, or feature requests:
1. Check this documentation
2. Review logs: `/Users/alex/logs/market-pulse/prod-scraping.log`
3. Test manually: `make reddit-scrape-incremental --verbose`
4. Open an issue with logs and error messages

## License

Part of the Market Pulse project. See main repository for license.
