#!/usr/bin/env python3
"""Quick test script to verify the optimized Yahoo Finance fetching."""

import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.stock_data import StockDataService


async def test_optimization():
    """Test the optimized concurrent fetching."""

    # Test with a reasonable number of tickers
    test_tickers = [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "NVDA",
        "TSLA",
        "META",
        "AMD",
        "NFLX",
        "INTC",
        "SPY",
        "QQQ",
        "DIA",
        "PLTR",
        "COIN",
    ]

    print("=" * 80)
    print("Testing Optimized Yahoo Finance Fetching")
    print("=" * 80)
    print(f"\nTest tickers: {len(test_tickers)}")
    print(f"Symbols: {', '.join(test_tickers)}\n")

    service = StockDataService()

    # Test the optimized method
    print("Fetching prices concurrently (max_concurrent=20)...")
    start = time.time()

    results = await service.get_multiple_prices(test_tickers, max_concurrent=20)

    elapsed = time.time() - start

    # Analyze results
    successful = sum(1 for v in results.values() if v is not None)
    failed = len(test_tickers) - successful

    print(f"\n{'=' * 80}")
    print("RESULTS")
    print("=" * 80)
    print(f"\nTotal time: {elapsed:.2f}s")
    print(f"Average per ticker: {elapsed/len(test_tickers):.2f}s")
    print(
        f"Successful: {successful}/{len(test_tickers)} ({successful/len(test_tickers)*100:.1f}%)"
    )
    print(f"Failed: {failed}")

    # Show sample prices
    print("\nSample results:")
    print("-" * 80)
    for symbol, data in list(results.items())[:10]:
        if data:
            change_emoji = "📈" if data["change"] >= 0 else "📉"
            print(
                f"{change_emoji} {symbol:6s}: ${data['price']:8.2f}  "
                f"{data['change']:+6.2f} ({data['change_percent']:+5.2f}%)  "
                f"{data['market_state']}"
            )
        else:
            print(f"❌ {symbol:6s}: No data available")

    if len(results) > 10:
        print(f"... and {len(results) - 10} more")

    # Performance estimate
    print(f"\n{'=' * 80}")
    print("PERFORMANCE PROJECTION")
    print("=" * 80)
    estimated_50 = (50 / len(test_tickers)) * elapsed
    print(
        f"\nEstimated time for 50 tickers: ~{estimated_50:.1f}s ({estimated_50/60:.1f} min)"
    )
    print(f"Estimated time per ticker: ~{elapsed/len(test_tickers):.2f}s")

    # Based on notebook results
    print("\nComparison (based on benchmark):")
    print("  Old sequential method: ~60s for 50 tickers")
    print(f"  New concurrent method: ~{estimated_50:.1f}s for 50 tickers")
    print(f"  Speedup: ~{60/estimated_50:.1f}x faster")
    print(f"  Time saved: ~{60-estimated_50:.1f}s per run")

    print(f"\n{'=' * 80}")
    print("✅ Test completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_optimization())
