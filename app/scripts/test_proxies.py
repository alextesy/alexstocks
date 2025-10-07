"""Test proxy configuration for Yahoo Finance API."""

import asyncio
import logging
import os
import sys

sys.path.append(".")

from app.services.stock_data import StockDataService

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def test_proxies():
    """Test proxy configuration with Yahoo Finance."""
    print("=" * 80)
    print("Yahoo Finance Proxy Test")
    print("=" * 80)

    # Check environment variable
    proxy_env = os.getenv("YFINANCE_PROXIES", "")

    if proxy_env:
        proxies = [p.strip() for p in proxy_env.split(",") if p.strip()]
        print(f"\n✓ Found {len(proxies)} proxies in YFINANCE_PROXIES:")
        for i, proxy in enumerate(proxies, 1):
            # Mask credentials if present
            if "@" in proxy:
                parts = proxy.split("@")
                masked = f"{parts[0].split(':')[0]}:****@{parts[1]}"
                print(f"  {i}. {masked}")
            else:
                print(f"  {i}. {proxy}")
    else:
        print("\n⚠️  No proxies configured (YFINANCE_PROXIES not set)")
        print("   Will use direct connection (may hit rate limits)")

    print("\n" + "=" * 80)
    print("Testing API requests...")
    print("=" * 80)

    # Test with a single ticker
    test_symbol = "AAPL"
    stock_service = StockDataService()

    print(f"\nTest 1: Fetching {test_symbol}...")
    try:
        result = await stock_service.get_stock_price(test_symbol)
        if result:
            print(f"✓ Success!")
            print(f"  Price: ${result['price']}")
            print(f"  Change: {result['change_percent']:+.2f}%")
        else:
            print(f"✗ Failed (no data returned)")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test with multiple tickers (proxy rotation)
    test_symbols = ["AAPL", "TSLA", "MSFT"]
    print(f"\nTest 2: Fetching {len(test_symbols)} symbols (tests proxy rotation)...")

    try:
        results = await stock_service.get_multiple_prices(test_symbols)

        success_count = sum(1 for v in results.values() if v is not None)
        print(f"\n✓ Success rate: {success_count}/{len(test_symbols)}")

        for symbol, data in results.items():
            if data:
                print(f"  ✓ {symbol}: ${data['price']}")
            else:
                print(f"  ✗ {symbol}: Failed")
    except Exception as e:
        print(f"✗ Error: {e}")

    print("\n" + "=" * 80)
    print("Proxy Test Complete")
    print("=" * 80)

    if not proxy_env:
        print("\n💡 Tip: Set YFINANCE_PROXIES to avoid rate limiting:")
        print('   export YFINANCE_PROXIES="http://proxy1:8080,http://proxy2:8080"')
        print("\n   See docs/PROXY_SETUP.md for detailed instructions.")


if __name__ == "__main__":
    asyncio.run(test_proxies())
