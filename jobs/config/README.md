# Reddit Scraper Configuration

This directory contains configuration files for the Reddit scraper.

## Configuration File

**`reddit_scraper_config.yaml`** - Main configuration for multi-subreddit scraping

### Features

- **Multi-subreddit support**: Configure multiple subreddits with individual settings
- **Daily discussions**: Automatically detect and scrape daily/weekend discussion threads
- **Top posts**: Scrape top posts from the last 24 hours
- **Configurable limits**: Set different comment limits for discussions vs regular posts
- **Unlimited comments**: Use `-1` or `null` for unlimited comment scraping

### Configuration Structure

```yaml
rate_limiting:
  requests_per_minute: 60  # Reddit OAuth limit

scraping:
  batch_save_interval: 200  # Save to DB every N comments
  max_workers: 5           # Worker threads for ticker linking

subreddits:
  - name: wallstreetbets
    enabled: true
    daily_discussion_keywords:
      - "daily discussion"
      - "weekend discussion"
      - "moves tomorrow"
    limits:
      daily_discussion_max_comments: -1  # -1 = unlimited comments
      regular_post_max_comments: 0       # 0 = just the post, no comments (fast!)
      max_top_posts_per_run: 100
```

### Subreddit Settings

- **`name`**: Subreddit name (without r/ prefix)
- **`enabled`**: Set to `false` to skip this subreddit
- **`daily_discussion_keywords`**: List of keywords to identify discussion threads (case-insensitive)
- **`limits.daily_discussion_max_comments`**: Max comments per discussion thread (-1 for unlimited)
- **`limits.regular_post_max_comments`**: Max comments per top post (0 = just scrape post metadata, no comments)
- **`limits.max_top_posts_per_run`**: Max number of top posts to scrape per run

### Adding New Subreddits

To add a new subreddit, copy the template below and adjust the settings:

```yaml
  - name: your_subreddit_name
    enabled: true
    daily_discussion_keywords:
      - "daily thread"
      - "discussion"
    limits:
      daily_discussion_max_comments: 500
      regular_post_max_comments: 50
      max_top_posts_per_run: 50
```

### Usage

The scraper automatically loads the config from this directory. You can also specify a custom config path:

```bash
# Use default config
python -m ingest.reddit_scraper_cli --mode incremental

# Use custom config
python -m ingest.reddit_scraper_cli --mode incremental --config path/to/config.yaml

# Scrape specific subreddit (overrides config)
python -m ingest.reddit_scraper_cli --mode incremental --subreddit wallstreetbets
```

### Behavior

**Daily Discussions:**
- ALL matching discussion threads are scraped (no artificial limit)
- Uses `daily_discussion_max_comments` limit per thread
- Incremental: Only scrapes new comments since last run

**Top Posts:**
- Scrapes top posts from last 24 hours
- Limited to `max_top_posts_per_run` posts
- Excludes posts matching daily discussion keywords
- Uses `regular_post_max_comments` limit per post:
  - `0` = Just scrape post metadata (title, upvotes, comment count) - FAST!
  - `> 0` = Scrape post + N comments from each post
  - `-1` = Scrape post + all comments (slow)
- Incremental: Skips posts already in database

### Rate Limiting

- Default: 60 requests per minute (Reddit OAuth limit)
- The scraper automatically throttles to stay under the limit
- Handles rate limit errors with exponential backoff

### Post Data Captured

When scraping posts (with `regular_post_max_comments: 0`), each Article record includes:
- **Title**: Post title
- **URL**: Reddit post URL
- **Upvotes**: Current score/upvotes
- **Comment Count**: Total number of comments on the post
- **Author**: Username who posted
- **Subreddit**: Which subreddit it was posted in
- **Published Date**: When the post was created
- **Text**: Post body/selftext (if any)
- **Linked Tickers**: Automatically detected stock tickers from title and text

