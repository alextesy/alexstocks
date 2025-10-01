# Market Pulse Cron Jobs Summary

## 📋 Overview

This document maps all cron job configurations available for the Market Pulse system and provides recommendations for different use cases.

## 📁 Available Cron Job Files

### 1. `cron-15min-simple.txt` ⭐ **RECOMMENDED FOR MOST USERS**
**Purpose**: Simple 15-minute incremental pipeline  
**Use Case**: Real-time market sentiment tracking  
**Features**:
- Scrape Reddit comments every 15 minutes
- Analyze sentiment every 15 minutes  
- Stock prices during market hours
- Weekend mode (reduced frequency)
- Daily status checks

### 2. `cron-15min-pipeline.txt` 🚀 **RECOMMENDED FOR PRODUCTION**
**Purpose**: Full 15-minute pipeline with all features  
**Use Case**: Production environment with comprehensive monitoring  
**Features**:
- Everything in simple version
- Error monitoring and alerts
- High-frequency mode options (5-minute updates)
- Detailed logging and troubleshooting
- Alternative decoupled pipeline options
- Comprehensive documentation and examples

## 🎯 Recommended Configurations

### For Real-Time Trading (15-minute updates)
```bash
# Use the simple 15-minute pipeline
./setup-cron-15min.sh
# Choose option 1 (simple pipeline)
```

### For Production Environment
```bash
# Use the full 15-minute pipeline
./setup-cron-15min.sh  
# Choose option 2 (full pipeline)
```

### For Moderate Updates (Hourly)
```bash
# Use hourly setup
crontab -e
# Copy content from cron-hourly-setup.txt
```

### For Stock-Focused Analysis
```bash
# Use stock prices setup
crontab -e
# Copy content from cron-stock-prices-setup.txt
```

## 🔧 Pipeline Components

### Core Pipeline: Scrape → Link → Sentiment

1. **Scraping** (`make reddit-robust-scrape`)
   - Uses robust scraper with rate limit handling
   - Incremental saving every 200 comments
   - Handles Reddit API limits gracefully
   - Focuses on latest daily/weekend discussions

2. **Ticker Linking** (automatic during scraping)
   - Links Reddit comments to stock tickers
   - Uses comprehensive ticker database
   - Provides confidence scores

3. **Sentiment Analysis** (`make analyze-sentiment-recent`)
   - Analyzes sentiment for new articles
   - Uses VADER sentiment analysis
   - Can be configured for LLM sentiment

4. **Stock Prices** (`make collect-stock-prices`)
   - Current prices during market hours
   - Historical data after market close

## ⏰ Scheduling Options

### 15-Minute Pipeline (Real-Time)
- **Reddit scraping**: Every 15 minutes
- **Sentiment analysis**: Every 15 minutes  
- **Stock prices**: Every 15 minutes (market hours)
- **Weekend mode**: Every hour (scraping), every 2 hours (sentiment)

### Hourly Pipeline (Moderate)
- **Reddit scraping**: Every hour
- **Sentiment analysis**: Every hour
- **Stock prices**: Every 30 minutes (market hours)

### Custom Schedules
- **Peak hours**: 5-minute updates during market hours
- **After hours**: 2-hour updates
- **Weekend**: 4-6 hour updates

## 📊 Log Files

All configurations create logs in `/Users/alex/logs/market-pulse/`:

- `15min-scraping.log` - Reddit scraping activity
- `15min-sentiment.log` - Sentiment analysis activity  
- `15min-stock-prices.log` - Stock price collection
- `daily-status.log` - Daily status checks
- `weekend-*.log` - Weekend mode activities
- `error-monitor.log` - Error monitoring (full pipeline only)

## 🚀 Quick Setup

### Option 1: Automated Setup (Recommended)
```bash
cd /Users/alex/market-pulse-v2
./setup-cron-15min.sh
```

### Option 2: Manual Setup
```bash
# Create log directory
mkdir -p /Users/alex/logs/market-pulse

# Edit crontab
crontab -e

# Copy content from cron-15min-simple.txt
```

### Option 3: Custom Configuration
```bash
# Review all options
cat cron-15min-pipeline.txt
cat crontab.example

# Create custom configuration
crontab -e
```

## 🔍 Monitoring

### Check Cron Jobs
```bash
crontab -l
```

### Monitor Logs
```bash
# Real-time monitoring
tail -f /Users/alex/logs/market-pulse/15min-scraping.log
tail -f /Users/alex/logs/market-pulse/15min-sentiment.log

# Check for errors
grep -i error /Users/alex/logs/market-pulse/*.log
```

### Test Manually
```bash
# Test scraping
make reddit-robust-scrape

# Test sentiment analysis  
make analyze-sentiment-recent

# Check status
make reddit-status
```

## ⚠️ Important Notes

### Reddit API Limits
- **Limit**: 100 requests per minute
- **Our usage**: 90 requests per minute (safe margin)
- **Rate limiting**: Built into robust scraper
- **Incremental saving**: Prevents data loss

### Database Considerations
- **Incremental processing**: Only new articles processed
- **Duplicate prevention**: Built-in deduplication
- **Performance**: Optimized for 15-minute intervals

### Weekend Mode
- **Reduced frequency**: Conserves API quota
- **Still active**: Maintains data collection
- **Market closed**: Focus on sentiment trends

## 🛠️ Troubleshooting

### Common Issues
1. **Cron not running**: Check cron service status
2. **Permission errors**: Verify file permissions and paths
3. **API rate limits**: Check Reddit credentials and limits
4. **Database errors**: Verify database connection

### Debug Commands
```bash
# Check cron service
sudo systemctl status cron  # Linux
launchctl list | grep cron  # macOS

# Test environment
cd /Users/alex/market-pulse-v2
make reddit-robust-scrape

# Check logs
tail -n 100 /Users/alex/logs/market-pulse/15min-scraping.log
```

## 📈 Performance Metrics

### Expected Throughput (15-minute pipeline)
- **Comments per run**: 200-500 new comments
- **Processing time**: 2-5 minutes per run
- **API usage**: ~50-100 requests per run
- **Data growth**: ~1000-2500 articles per day

### Resource Usage
- **CPU**: Low (mostly I/O bound)
- **Memory**: ~100-200MB per run
- **Disk**: ~10-50MB logs per day
- **Network**: Moderate (Reddit API calls)

## 🎯 Recommendations

### For Development
- Use `cron-15min-simple.txt`
- Monitor logs closely
- Test manually first

### For Production
- Use `cron-15min-pipeline.txt`  
- Set up log rotation
- Monitor error logs
- Have backup plans

### For High-Frequency Trading
- Consider 5-minute updates during market hours
- Monitor API usage closely
- Have rate limit handling
- Use multiple Reddit API keys if needed
