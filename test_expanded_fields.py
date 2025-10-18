#!/usr/bin/env python3
"""Test the expanded stock price fields implementation."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.stock_data import StockDataService


async def test_expanded_fields():
    """Test fetching stock data with all the new fields."""

    print("=" * 80)
    print("Testing Expanded Stock Price Fields")
    print("=" * 80)

    service = StockDataService()

    # Test with a few representative stocks
    test_symbols = ["AAPL", "TSLA", "SPY"]

    print(f"\nFetching data for: {', '.join(test_symbols)}\n")

    for symbol in test_symbols:
        print(f"\n{'=' * 80}")
        print(f"Testing: {symbol}")
        print("=" * 80)

        data = await service.get_stock_price(symbol)

        if not data:
            print(f"❌ Failed to fetch data for {symbol}")
            continue

        # Display all fields organized by category
        print("\n📊 BASIC PRICE DATA")
        print(f"  Symbol:           {data.get('symbol')}")
        print(f"  Current Price:    ${data.get('price', 0):.2f}")
        print(f"  Previous Close:   ${data.get('previous_close', 0):.2f}")
        print(f"  Change:           ${data.get('change', 0):+.2f}")
        print(f"  Change %:         {data.get('change_percent', 0):+.2f}%")

        print("\n📈 INTRADAY TRADING DATA")
        print(
            f"  Open:             ${data.get('open', 0):.2f}"
            if data.get("open")
            else "  Open:             N/A"
        )
        print(
            f"  Day High:         ${data.get('day_high', 0):.2f}"
            if data.get("day_high")
            else "  Day High:         N/A"
        )
        print(
            f"  Day Low:          ${data.get('day_low', 0):.2f}"
            if data.get("day_low")
            else "  Day Low:          N/A"
        )
        if data.get("volume"):
            volume_m = data.get("volume") / 1_000_000
            print(f"  Volume:           {volume_m:.2f}M shares")
        else:
            print("  Volume:           N/A")

        print("\n💹 BID/ASK SPREAD")
        print(
            f"  Bid:              ${data.get('bid', 0):.2f}"
            if data.get("bid")
            else "  Bid:              N/A"
        )
        print(
            f"  Ask:              ${data.get('ask', 0):.2f}"
            if data.get("ask")
            else "  Ask:              N/A"
        )
        print(f"  Bid Size:         {data.get('bid_size', 'N/A')}")
        print(f"  Ask Size:         {data.get('ask_size', 'N/A')}")
        if data.get("bid") and data.get("ask"):
            spread = data.get("ask") - data.get("bid")
            spread_pct = (spread / data.get("price", 1)) * 100
            print(f"  Spread:           ${spread:.2f} ({spread_pct:.3f}%)")

        print("\n💼 MARKET METRICS")
        if data.get("market_cap"):
            market_cap_b = data.get("market_cap") / 1_000_000_000
            print(f"  Market Cap:       ${market_cap_b:.2f}B")
        else:
            print("  Market Cap:       N/A")

        if data.get("shares_outstanding"):
            shares_m = data.get("shares_outstanding") / 1_000_000
            print(f"  Shares Out:       {shares_m:.2f}M")
        else:
            print("  Shares Out:       N/A")

        if data.get("average_volume"):
            avg_vol_m = data.get("average_volume") / 1_000_000
            print(f"  Avg Volume (3m):  {avg_vol_m:.2f}M")
        else:
            print("  Avg Volume (3m):  N/A")

        if data.get("average_volume_10d"):
            avg_vol_10d_m = data.get("average_volume_10d") / 1_000_000
            print(f"  Avg Volume (10d): {avg_vol_10d_m:.2f}M")
        else:
            print("  Avg Volume (10d): N/A")

        print("\n🏦 METADATA")
        print(f"  Exchange:         {data.get('exchange', 'N/A')}")
        print(f"  Currency:         {data.get('currency', 'N/A')}")
        print(f"  Market State:     {data.get('market_state', 'N/A')}")
        print(f"  Last Updated:     {data.get('last_updated', 'N/A')}")

    # Summary of fields captured
    print(f"\n{'=' * 80}")
    print("FIELD CAPTURE SUMMARY")
    print("=" * 80)

    # Count which fields are being captured
    all_data = await service.get_multiple_prices(test_symbols, max_concurrent=3)

    field_stats = {}
    for symbol, data in all_data.items():
        if not data:
            continue
        for field in data.keys():
            if field not in field_stats:
                field_stats[field] = {"captured": 0, "missing": 0}
            if data[field] is not None and data[field] != "":
                field_stats[field]["captured"] += 1
            else:
                field_stats[field]["missing"] += 1

    print("\nField capture rates:")
    print(f"{'Field':<25} {'Captured':<10} {'Rate':<10}")
    print("-" * 50)

    for field, stats in sorted(field_stats.items()):
        total = stats["captured"] + stats["missing"]
        rate = (stats["captured"] / total * 100) if total > 0 else 0
        status = "✓" if rate >= 80 else "⚠️"
        print(f"{status} {field:<23} {stats['captured']}/{total:<8} {rate:>5.1f}%")

    print(f"\n{'=' * 80}")
    print("✅ Testing Complete!")
    print("=" * 80)

    # Check for critical fields
    critical_fields = [
        "price",
        "open",
        "day_high",
        "day_low",
        "volume",
        "market_cap",
        "average_volume",
    ]

    print("\n🎯 Critical Field Status:")
    all_critical_ok = True
    for field in critical_fields:
        if field in field_stats:
            total = field_stats[field]["captured"] + field_stats[field]["missing"]
            rate = (field_stats[field]["captured"] / total * 100) if total > 0 else 0
            if rate >= 80:
                print(f"  ✓ {field}: {rate:.0f}%")
            else:
                print(f"  ⚠️  {field}: {rate:.0f}%")
                all_critical_ok = False
        else:
            print(f"  ❌ {field}: Not found")
            all_critical_ok = False

    if all_critical_ok:
        print("\n🎉 All critical fields are being captured successfully!")
    else:
        print("\n⚠️  Some critical fields have low capture rates")

    print(f"\n{'=' * 80}")


if __name__ == "__main__":
    asyncio.run(test_expanded_fields())
