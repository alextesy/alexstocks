# Proxy Setup for Yahoo Finance API

To avoid rate limiting from Yahoo Finance, you can configure proxies for the stock data collection.

## Quick Setup

Set the `YFINANCE_PROXIES` environment variable with a comma-separated list of proxy URLs:

```bash
export YFINANCE_PROXIES="http://proxy1.example.com:8080,http://proxy2.example.com:8080,http://proxy3.example.com:8080"
```

The system will automatically rotate through proxies using round-robin.

## Proxy Options

### Option 1: Free Proxy Services (Not Recommended for Production)

**Pros:** Free, easy to try
**Cons:** Unreliable, slow, often blocked

Free proxy lists:
- https://free-proxy-list.net/
- https://www.proxy-list.download/
- https://spys.one/en/

**Example with free proxies:**
```bash
export YFINANCE_PROXIES="http://47.88.62.42:80,http://103.152.112.162:80,http://195.201.231.222:8080"
```

⚠️ **Warning:** Free proxies are often unreliable and may not work. Many are already banned by Yahoo Finance.

---

### Option 2: Residential Proxies (Recommended for Production)

**Pros:** More reliable, less likely to be blocked, better success rate
**Cons:** Costs money ($5-50/month depending on usage)

Popular residential proxy providers:
- **Bright Data (formerly Luminati)** - https://brightdata.com/
- **Smartproxy** - https://smartproxy.com/
- **Oxylabs** - https://oxylabs.io/
- **IPRoyal** - https://iproyal.com/
- **Webshare** - https://www.webshare.io/

**Example with Bright Data:**
```bash
# Format: http://username:password@proxy-host:port
export YFINANCE_PROXIES="http://lum-customer-USER-zone-ZONE:PASSWORD@zproxy.lum-superproxy.io:22225"
```

**Example with Smartproxy:**
```bash
export YFINANCE_PROXIES="http://user:pass@gate.smartproxy.com:7000,http://user:pass@gate.smartproxy.com:7001"
```

---

### Option 3: SOCKS5 Proxies

If you have SOCKS5 proxies, convert them to HTTP/HTTPS format:

```bash
export YFINANCE_PROXIES="socks5://user:pass@proxy.example.com:1080"
```

Note: yfinance uses `requests` library which supports SOCKS5 via `requests[socks]`.

---

### Option 4: VPN Rotation (Alternative)

Instead of proxies, you can use a VPN service that supports server rotation:
- NordVPN
- ExpressVPN
- Surfshark

This is less programmatic but can work for development.

---

## Setup Instructions

### Development (Local)

1. **Add to your `.env` file:**
   ```bash
   YFINANCE_PROXIES="http://proxy1.example.com:8080,http://proxy2.example.com:8080"
   ```

2. **Or export in your shell:**
   ```bash
   export YFINANCE_PROXIES="http://proxy1.example.com:8080,http://proxy2.example.com:8080"
   ```

3. **Test it:**
   ```bash
   uv run python app/scripts/smoke_test_stock_prices.py
   ```

### Production (EC2)

1. **Add to systemd environment file** (if using systemd):
   ```bash
   sudo nano /etc/systemd/system/market-pulse.service.d/override.conf
   ```

   Add:
   ```ini
   [Service]
   Environment="YFINANCE_PROXIES=http://proxy1:8080,http://proxy2:8080"
   ```

2. **Or add to cron environment:**
   ```bash
   crontab -e
   ```

   Add at the top:
   ```bash
   YFINANCE_PROXIES="http://proxy1:8080,http://proxy2:8080"

   */15 * * * * cd /home/ubuntu/market-pulse-v2 && make collect-stock-prices-top50 >> /var/log/market_pulse/price_refresh.log 2>&1
   ```

3. **Or set in shell profile:**
   ```bash
   echo 'export YFINANCE_PROXIES="http://proxy1:8080,http://proxy2:8080"' >> ~/.bashrc
   source ~/.bashrc
   ```

---

## How It Works

The proxy rotation system:

1. **Round-robin rotation** - Each request uses the next proxy in the list
2. **Automatic failover** - If a proxy fails, it retries with exponential backoff
3. **No configuration needed** - Just set the environment variable

Example flow with 3 proxies:
```
Request 1 (AAPL) → Proxy 1
Request 2 (TSLA) → Proxy 2
Request 3 (MSFT) → Proxy 3
Request 4 (NVDA) → Proxy 1 (back to start)
...
```

---

## Testing Proxies

Test if your proxies work:

```bash
# Test with curl
curl -x http://proxy.example.com:8080 https://finance.yahoo.com/quote/AAPL

# Test in Python
python3 << EOF
import requests
proxies = {'http': 'http://proxy.example.com:8080', 'https': 'http://proxy.example.com:8080'}
response = requests.get('https://finance.yahoo.com/quote/AAPL', proxies=proxies, timeout=10)
print(f"Status: {response.status_code}")
EOF
```

---

## Recommended Proxy Setup for Production

For reliable production use:

1. **Use 3-5 residential proxies** from a paid provider
2. **Rotate through them** (handled automatically)
3. **Monitor logs** for proxy failures
4. **Set up alerting** if all proxies fail

**Cost estimate:**
- Bright Data: ~$500/month for 20GB (residential)
- Smartproxy: ~$75/month for 5GB (residential)
- Webshare: ~$10/month for 250 proxies (datacenter, may not work for Yahoo)

For Market Pulse (50 tickers every 15 minutes):
- ~3,200 requests/day
- ~0.5-1GB/month data
- **Recommended:** Smartproxy $75/month plan (5GB) or Bright Data starter

---

## Alternative: Request Caching

If proxies are too expensive, rely more heavily on caching:

```python
# Already implemented:
# - 30-minute cache for individual tickers
# - Top 50 refreshed every 15 minutes
# - Fallback to stale cache on API failures
```

This minimizes API requests and works well for most use cases.

---

## Troubleshooting

### Proxies not working?

**Check environment variable:**
```bash
echo $YFINANCE_PROXIES
```

**Check logs:**
```bash
grep -i "proxy" /var/log/market_pulse/price_refresh.log
```

**Test individual proxy:**
```bash
curl -x http://your-proxy:8080 https://httpbin.org/ip
```

### Still getting rate limited?

1. **Increase delay between requests** in `stock_data.py`:
   ```python
   self._min_request_interval = 1.0  # Increase from 0.5s to 1s
   ```

2. **Reduce batch size** in `stock_price_service.py`:
   ```python
   batch_size = 3  # Reduce from 5 to 3
   ```

3. **Add more proxies** to rotate through

---

## No Proxies? (Fallback Strategy)

If you don't want to use proxies, the system will work but with limitations:

1. ✅ **Caching reduces API calls** - Most requests served from cache
2. ⚠️ **Initial collection may fail** - First time collection of 50 tickers might hit rate limits
3. ✅ **Gradual collection** - Spread collection over multiple runs
4. ✅ **Stale data fallback** - Shows cached data even if API fails

**To minimize rate limiting without proxies:**
- Run collection during off-peak hours (late night/early morning)
- Increase cron interval (30 minutes instead of 15)
- Reduce top N from 50 to 25 tickers

---

## Summary

**For Development:**
- Try without proxies first (use cached data)
- If rate limited, wait a few hours or use free proxies (unreliable)

**For Production:**
- Use 3-5 residential proxies from paid provider ($10-75/month)
- Set via `YFINANCE_PROXIES` environment variable
- Monitor logs for proxy health

**Budget Option:**
- Rely on aggressive caching
- Run collection during off-peak hours
- Accept occasional rate limit failures
