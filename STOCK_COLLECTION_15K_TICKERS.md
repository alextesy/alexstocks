# Stock Collection Guide for 15,000+ Tickers

You have **15,011 tickers** in your database. Here's how to handle this efficiently.

## 🚨 The Problem

With 15,011 tickers and rate limiting:
- **Time to collect all**: ~4 hours (15,011 × ~1 second each)
- **Many inactive tickers**: Warrants (-WT), Units (-U), Rights (-R), delisted stocks
- **Wasted API calls**: Retrying invalid tickers 3 times each

## ✅ Solutions

### Option 1: Smart Collection (RECOMMENDED)

Use the smart collector that filters out inactive tickers:

```bash
# Analyze your tickers first
make analyze-tickers

# Collect only active tickers (excludes warrants, units, rights)
make collect-stock-prices-smart

# Test with 10 tickers first
make collect-stock-prices-test
```

**Benefits:**
- Filters out ~30-40% of inactive tickers
- Faster collection (~1.5-2.5 hours instead of 4 hours)
- Fewer failed API calls
- Same data quality for tradeable stocks

### Option 2: Collect in Batches

Collect different groups at different frequencies:

```bash
# Most active/popular tickers every 15 minutes (create a subset)
# Less active tickers every hour
# Inactive tickers once a day or skip entirely
```

### Option 3: Prioritize by Activity

Focus on tickers that are actually mentioned in your Reddit data:

```sql
-- Get tickers that are actually being discussed
SELECT DISTINCT ticker
FROM article_ticker
ORDER BY ticker;
```

Then collect only those.

## 🎯 Recommended Setup

### For Production (15-minute cron):

**Use the smart collector:**

```bash
# Edit your cron setup script to use smart collection
*/15 * * * * cd /Users/alex/market-pulse-v2 && uv run python app/scripts/collect_stock_data_smart.py --type current >> /tmp/stock_prices.log 2>&1
```

### Quick Start

```bash
# 1. Analyze what you have
make analyze-tickers

# 2. Test with 10 tickers
make collect-stock-prices-test

# 3. Run smart collection
make collect-stock-prices-smart
```

## 📊 What the Smart Collector Filters Out

### Excluded ticker patterns:
- `%-WT` - Warrants (e.g., AACT-WT)
- `%-WS` - Warrants (alternative suffix)
- `%-U` - Units
- `%-R` - Rights
- `%+` - Special class shares
- `%.%` - Some foreign/ADR variations

### Example of what gets filtered:
- ❌ `AACT-WT` (Warrant - no price data)
- ❌ `XYZ-U` (Unit - typically splits into stock + warrant)
- ❌ `ABC-R` (Rights - expire quickly)
- ✅ `AAPL` (Regular stock)
- ✅ `TSLA` (Regular stock)
- ✅ `MSFT` (Regular stock)

## 🔍 Check Your Ticker Composition

```bash
# Run the analyzer
make analyze-tickers
```

This will show you:
- Total tickers
- How many have price data
- Breakdown by ticker type (warrants, units, rights)
- Estimated collection time
- Sample tickers without prices

## ⚡ Speed Optimizations

If you still need faster collection:

### 1. Reduce Rate Limiting (riskier)

Edit `app/services/stock_data.py`:
```python
self._min_request_interval = 0.25  # Down from 0.5 (2x faster, higher rate limit risk)
```

### 2. Increase Batch Size

Edit `app/collectors/stock_price_collector.py`:
```python
batch_size = 20  # Up from 10
```

### 3. Parallel Collection (advanced)

Split tickers into chunks and run multiple collectors in parallel:
```bash
# Terminal 1: Collect A-M
python app/scripts/collect_stock_data_smart.py --symbols-pattern "^[A-M]"

# Terminal 2: Collect N-Z
python app/scripts/collect_stock_data_smart.py --symbols-pattern "^[N-Z]"
```

## 🎛️ Commands Reference

```bash
# Analyze your ticker database
make analyze-tickers

# Smart collection (filters inactive)
make collect-stock-prices-smart

# Test with 10 tickers
make collect-stock-prices-test

# Collect ALL tickers (slow, not recommended)
make collect-stock-prices

# Direct commands for more control
uv run python app/scripts/collect_stock_data_smart.py --type current --limit 100
uv run python app/scripts/collect_stock_data_smart.py --type current --no-filter  # Include ALL
```

## 📈 Expected Results

### With Smart Filtering:
- **Active tickers**: ~9,000-11,000 (60-70% of total)
- **Collection time**: ~2-3 hours (with rate limiting)
- **Success rate**: ~85-95%
- **Usable data**: Same quality, just excludes non-tradeable securities

### Without Filtering (all 15,011):
- **Collection time**: ~4 hours
- **Success rate**: ~60-70% (many failures on inactive tickers)
- **Wasted API calls**: 30-40% on delisted/invalid tickers

## 🚀 Quick Setup for Production

```bash
# 1. Test the smart collector
make collect-stock-prices-test

# 2. Run full smart collection once
make collect-stock-prices-smart

# 3. Update cron setup script to use smart collector
nano scripts/setup-stock-price-cron.sh
# Change: collect_all_stock_data.py → collect_stock_data_smart.py

# 4. Set up cron
make setup-stock-cron
```

## 💡 Pro Tips

1. **Start with smart collection** - It's almost always what you want
2. **Monitor the first run** - Watch logs to see failure rate
3. **Use `--limit` for testing** - Test with 10-100 tickers before full run
4. **Run during off-hours** - First full collection during low-traffic time
5. **Check the database after** - Verify you're getting good data

## 🆘 If Collection is Still Too Slow

Consider these alternatives:

1. **Collect only S&P500** - Just the 500 most important stocks
2. **Collect only mentioned tickers** - Track what appears in Reddit discussions
3. **Use paid API** - Finnhub, Alpha Vantage have bulk endpoints
4. **Cloud functions** - Distribute collection across multiple workers

## Summary

**For your 15,011 tickers, I recommend:**

✅ **Use `make collect-stock-prices-smart`** - Filters inactive, saves 1-2 hours
✅ **Set up smart cron** - Use smart collector for 15-min updates
✅ **Run `make analyze-tickers` first** - Understand your data
✅ **Test with `--limit 10`** - Verify before full run

This will give you:
- ~9,000-11,000 actively tradeable stocks
- ~2-3 hour initial collection
- Much better success rate
- Same quality data for real stocks
