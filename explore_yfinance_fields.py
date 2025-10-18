#!/usr/bin/env python3
"""Explore available fields from yfinance to determine what to store."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import yfinance as yf


async def explore_ticker_data():
    """Examine what data yfinance provides for a ticker."""

    # Use a well-known ticker
    symbol = "AAPL"
    print(f"Exploring yfinance data for {symbol}\n")
    print("=" * 80)

    ticker = yf.Ticker(symbol)

    # Get info (comprehensive data)
    print("\n📊 TICKER.INFO FIELDS")
    print("=" * 80)
    info = ticker.info

    # Categorize the fields
    price_fields = []
    volume_fields = []
    market_cap_fields = []
    valuation_fields = []
    dividend_fields = []
    analyst_fields = []
    company_fields = []
    other_fields = []

    for key, value in sorted(info.items()):
        if value is not None and value != {}:
            # Categorize
            key_lower = key.lower()
            if any(
                x in key_lower
                for x in ["price", "open", "high", "low", "close", "bid", "ask"]
            ):
                price_fields.append((key, type(value).__name__, value))
            elif any(x in key_lower for x in ["volume", "avgvolume"]):
                volume_fields.append((key, type(value).__name__, value))
            elif any(x in key_lower for x in ["marketcap", "cap", "shares"]):
                market_cap_fields.append((key, type(value).__name__, value))
            elif any(x in key_lower for x in ["pe", "pb", "eps", "beta", "ratio"]):
                valuation_fields.append((key, type(value).__name__, value))
            elif any(x in key_lower for x in ["dividend", "yield", "payout"]):
                dividend_fields.append((key, type(value).__name__, value))
            elif any(x in key_lower for x in ["target", "recommendation", "analyst"]):
                analyst_fields.append((key, type(value).__name__, value))
            elif any(
                x in key_lower
                for x in [
                    "name",
                    "sector",
                    "industry",
                    "country",
                    "website",
                    "description",
                ]
            ):
                company_fields.append((key, type(value).__name__, value))
            else:
                other_fields.append((key, type(value).__name__, value))

    def print_category(title, fields):
        if fields:
            print(f"\n{title}:")
            print("-" * 80)
            for key, vtype, value in fields:
                value_str = str(value)
                if len(value_str) > 60:
                    value_str = value_str[:60] + "..."
                print(f"  {key:30s} ({vtype:10s}): {value_str}")

    print_category("💰 PRICE FIELDS", price_fields)
    print_category("📊 VOLUME FIELDS", volume_fields)
    print_category("💼 MARKET CAP FIELDS", market_cap_fields)
    print_category("📈 VALUATION METRICS", valuation_fields)
    print_category("💵 DIVIDEND INFO", dividend_fields)
    print_category("🎯 ANALYST DATA", analyst_fields)
    print_category("🏢 COMPANY INFO", company_fields)
    print_category("🔧 OTHER FIELDS", other_fields[:20])  # Limit other fields

    # Try fast_info
    print("\n\n⚡ TICKER.FAST_INFO FIELDS")
    print("=" * 80)
    try:
        fast_info = ticker.fast_info
        print(f"Available attributes: {dir(fast_info)}")
        print("\nKey fast_info values:")
        for attr in [
            "lastPrice",
            "previousClose",
            "open",
            "dayHigh",
            "dayLow",
            "volume",
            "marketCap",
            "fiftyTwoWeekHigh",
            "fiftyTwoWeekLow",
            "currency",
            "exchange",
            "shares",
        ]:
            try:
                value = getattr(fast_info, attr, None)
                if value is not None:
                    print(f"  {attr:25s}: {value}")
            except:
                pass
    except Exception as e:
        print(f"Error accessing fast_info: {e}")

    # Generate recommendations
    print("\n\n✅ RECOMMENDED FIELDS TO STORE")
    print("=" * 80)
    print(
        """
Based on the analysis, here are the recommended fields to add to the database:

CURRENT PRICE DATA (Real-time, update frequently):
  ✓ price              - Current/last price (already stored)
  ✓ previous_close     - Previous close (already stored)
  ✓ change             - Price change (already stored)
  ✓ change_percent     - Percent change (already stored)
  + open               - Today's open price
  + day_high           - Today's high
  + day_low            - Today's low
  + volume             - Trading volume today
  + bid                - Current bid price
  + ask                - Current ask price
  + bid_size           - Bid size
  + ask_size           - Ask size

MARKET DATA (Update daily/weekly):
  + market_cap         - Market capitalization
  + shares_outstanding - Total shares
  + average_volume     - Average daily volume
  + average_volume_10d - 10-day average volume

52-WEEK RANGE (Update daily):
  + fifty_two_week_high - 52-week high
  + fifty_two_week_low  - 52-week low
  + fifty_two_week_change_percent - % from 52-week range

VALUATION METRICS (Update daily after market close):
  + pe_ratio           - Price-to-earnings ratio (trailing)
  + forward_pe         - Forward P/E ratio
  + price_to_book      - Price-to-book ratio
  + price_to_sales     - Price-to-sales ratio
  + peg_ratio          - PEG ratio
  + beta               - Stock beta (volatility)
  + earnings_per_share - EPS (trailing)
  + book_value         - Book value per share

DIVIDEND INFO (Update quarterly/annually):
  + dividend_rate      - Annual dividend rate
  + dividend_yield     - Dividend yield %
  + ex_dividend_date   - Ex-dividend date
  + payout_ratio       - Dividend payout ratio

ANALYST DATA (Update weekly):
  + target_mean_price  - Mean analyst target price
  + target_high_price  - High target
  + target_low_price   - Low target
  + recommendation_key - Buy/Hold/Sell recommendation
  + number_of_analysts - Number of analysts covering

COMPANY INFO (Static/rarely changes):
  + company_name       - Full company name
  + sector             - Sector
  + industry           - Industry
  + country            - Country
  + website            - Company website
  + employees          - Number of employees
  + description        - Business description (store separately?)
    """
    )


if __name__ == "__main__":
    asyncio.run(explore_ticker_data())
