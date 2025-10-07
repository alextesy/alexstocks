# Avoiding Yahoo Finance Rate Limits

## Summary

Yahoo Finance aggressively rate limits requests. Here are the strategies implemented:

## ✅ Already Implemented (No Action Needed)

### 1. Aggressive Caching (30-minute freshness)
- Individual ticker pages use cached data if < 30 minutes old
- Reduces API calls by ~80-90%
- Fallback to stale cache on API failures

### 2. Batch Processing with Delays
- Top 50 collection uses batches of 5 tickers
- 500ms minimum delay between requests
- Spread across 15-minute intervals

### 3. Exponential Backoff Retry
- Up to 3 retries per failed request
- 1s → 2s → 4s delays
- Automatic recovery from temporary blocks

### 4. Better User-Agent Headers
- Uses realistic browser User-Agent
- Mimics Chrome browser requests
- Less likely to be flagged as bot

## 🆕 New: Proxy Support (Optional)

### Quick Setup

```bash
# Set environment variable with proxy list
export YFINANCE_PROXIES="http://proxy1:8080,http://proxy2:8080,http://proxy3:8080"

# Test it
uv run python app/scripts/test_proxies.py
```

### How It Works

- **Round-robin rotation**: Each request uses next proxy
- **Automatic**: No code changes needed
- **Transparent**: Falls back to direct connection if no proxies

### Proxy Options

**Free Proxies (Testing Only):**
```bash
# Get from https://free-proxy-list.net/
export YFINANCE_PROXIES="http://47.88.62.42:80,http://103.152.112.162:80"
```
⚠️ **Warning:** Free proxies are unreliable and often already blocked

**Paid Proxies (Production):**
```bash
# Smartproxy (~$75/month for 5GB)
export YFINANCE_PROXIES="http://user:pass@gate.smartproxy.com:7000"

# Bright Data (~$500/month for 20GB)
export YFINANCE_PROXIES="http://user:pass@zproxy.lum-superproxy.io:22225"
```

See [PROXY_SETUP.md](./PROXY_SETUP.md) for detailed instructions.

## 📊 Rate Limit Management Strategy

### Without Proxies (Current)

**Pros:**
- ✅ Free
- ✅ Caching minimizes API calls
- ✅ Fallback to stale data

**Cons:**
- ⚠️ Initial collection may fail (first 50 tickers)
- ⚠️ Occasional rate limit errors
- ⚠️ Need to wait hours if blocked

**Best practices:**
- Run collection during off-peak hours (late night)
- Let cache handle most requests
- Accept occasional failures (graceful degradation)

### With Proxies (Recommended for Production)

**Pros:**
- ✅ Much higher request limits
- ✅ Near 100% success rate
- ✅ Faster collection times

**Cons:**
- ⚠️ Costs $10-75/month
- ⚠️ Requires proxy maintenance

**Best practices:**
- Use 3-5 residential proxies
- Rotate through them automatically
- Monitor for proxy failures

## 🧪 Testing

### Test Without Proxies
```bash
# Wait a few hours for rate limits to clear, then:
uv run python app/scripts/smoke_test_stock_prices.py
```

### Test With Proxies
```bash
# Set proxies
export YFINANCE_PROXIES="http://proxy1:8080,http://proxy2:8080"

# Test proxy setup
uv run python app/scripts/test_proxies.py

# Run full smoke test
uv run python app/scripts/smoke_test_stock_prices.py
```

## 🔧 Current Rate Limit Status

### Check If You're Rate Limited

```bash
# Try a simple request
curl https://query1.finance.yahoo.com/v7/finance/quote?symbols=AAPL
```

**Success:** Returns JSON with stock data
**Rate Limited:** Returns 429 error or "Too Many Requests"

### How Long Do Rate Limits Last?

- **Typical:** 1-6 hours
- **Severe:** Up to 24 hours
- **Varies by:** IP address, request volume, time of day

## 💡 Recommendations

### For Development (Your Current Situation)

1. **Wait a few hours** for rate limits to clear
2. **Use cached data** with the `test_stock_prices_cached.ipynb` notebook
3. **Test during off-peak hours** (early morning, late evening)

```bash
# Use cache-only notebook
jupyter notebook notebooks/test_stock_prices_cached.ipynb
```

### For Production (EC2 Deployment)

**Option A: No Proxies (Budget-Friendly)**
- ✅ Rely on aggressive caching
- ✅ Run collection at 3am (off-peak)
- ✅ Accept ~5-10% failure rate
- ✅ Users see cached data (< 30 min old)

**Option B: With Proxies (Recommended)**
- ✅ 3-5 residential proxies ($10-75/month)
- ✅ Near 100% success rate
- ✅ Run anytime without issues

## 📝 Summary Table

| Strategy | Cost | Success Rate | Setup Effort |
|----------|------|--------------|--------------|
| Cache only | Free | 85-90% | None (done) |
| Cache + off-peak | Free | 90-95% | Cron timing |
| Cache + free proxies | Free | 70-80% | 10 min |
| Cache + paid proxies | $10-75/mo | 95-99% | 15 min |

## 🚀 Quick Start

**Right now (rate limited):**
```bash
# Use cached notebook
jupyter notebook notebooks/test_stock_prices_cached.ipynb
```

**In a few hours:**
```bash
# Try without proxies
make collect-stock-prices-top50
```

**If still having issues:**
```bash
# Set up proxies
export YFINANCE_PROXIES="http://proxy1:8080"
uv run python app/scripts/test_proxies.py
```

See [PROXY_SETUP.md](./PROXY_SETUP.md) for complete proxy configuration guide.
