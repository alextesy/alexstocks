#!/usr/bin/env python3
"""Check if Yahoo Finance rate limit has cleared."""

from datetime import datetime

import yfinance as yf

print("=" * 60)
print("Yahoo Finance Rate Limit Check")
print("=" * 60)
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Test with a simple ticker
test_symbol = "AAPL"
print(f"Testing with {test_symbol}...")

try:
    ticker = yf.Ticker(test_symbol)
    hist = ticker.history(period="1d")

    if hist.empty:
        print("⚠️  Empty result - might still be limited or no data available")
        exit(1)
    else:
        print("✅ SUCCESS! Rate limit has cleared!")
        print(f"   Got {len(hist)} data point(s)")
        print()
        print("You can now collect stock data:")
        print()
        print("  # Test with 10 tickers:")
        print("  make collect-stock-prices-test")
        print()
        print("  # Or collect all active tickers:")
        print("  make collect-stock-prices-smart")
        exit(0)

except Exception as e:
    error_msg = str(e)
    if "Rate limit" in error_msg or "Too Many Requests" in error_msg:
        print("❌ Still rate limited!")
        print()
        print("Yahoo Finance is still blocking requests.")
        print("Typical recovery time: 12-24 hours")
        print()
        print("Your cron is now fixed and using smart collector.")
        print("Historical data will collect automatically tomorrow at 2 PM PT.")
        exit(1)
    else:
        print(f"❌ Unexpected error: {error_msg}")
        exit(1)
