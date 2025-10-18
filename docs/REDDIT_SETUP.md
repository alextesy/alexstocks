# Reddit API Setup Guide

This guide explains how to set up Reddit API access for AlexStocks Reddit ingestion.

## 1. Create Reddit App

1. Go to https://www.reddit.com/prefs/apps
2. Click "Create App" or "Create Another App"
3. Fill in the form:
   - **Name**: `MarketPulse` (or any name you prefer)
   - **App type**: Select "script"
   - **Description**: `Market news analytics bot`
   - **About URL**: Leave blank
   - **Redirect URI**: `http://localhost:8080` (required but not used)
4. Click "Create app"

## 2. Get API Credentials

After creating the app, you'll see:
- **Client ID**: The string under your app name (looks like `abc123def456`)
- **Client Secret**: The "secret" field (looks like `xyz789uvw012`)

## 3. Configure Environment Variables

Add these to your `.env` file:

```bash
# Reddit API Configuration
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=MarketPulse/1.0 by MarketPulseBot
```

## 4. Test Reddit Ingestion

```bash
# Add Reddit columns to database (one-time setup)
make add-reddit-columns

# Test Reddit ingestion (requires valid credentials)
make reddit-ingest

# Or test specific subreddits
make reddit-wsb
make reddit-stocks
make reddit-investing
```

## 5. Reddit API Limits

- **Rate Limit**: 60 requests per minute
- **No Authentication Required**: For public data (posts, comments)
- **User Agent**: Must be descriptive and include your Reddit username

## 6. Target Subreddits

The system is configured to ingest from:
- **r/wallstreetbets**: High-volume, meme stocks, high sentiment
- **r/stocks**: General stock discussion, more balanced
- **r/investing**: Long-term investment focus, quality discussions

## 7. Troubleshooting

### Common Issues

1. **"Reddit API credentials not found"**
   - Check that `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` are set in `.env`
   - Restart your application after adding environment variables

2. **"403 Forbidden" or "401 Unauthorized"**
   - Verify your client ID and secret are correct
   - Check that your user agent string is descriptive
   - Ensure you're not hitting rate limits

3. **"No articles parsed from Reddit"**
   - Check that the subreddits exist and are accessible
   - Verify your Reddit app has the correct permissions
   - Try with `--verbose` flag to see detailed logs

### Testing Without Reddit API

The test suite includes mocked Reddit API calls, so you can run tests without valid credentials:

```bash
uv run pytest tests/test_reddit_ingest.py -v
```

## 8. Data Structure

Reddit posts are stored in the `article` table with these additional fields:
- `reddit_id`: Unique Reddit post ID
- `subreddit`: Source subreddit name
- `author`: Reddit username
- `upvotes`: Post score
- `num_comments`: Comment count
- `reddit_url`: Direct Reddit post URL

The system automatically links Reddit posts to tickers using the same ticker linking logic as GDELT news articles.
