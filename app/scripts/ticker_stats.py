"""Display statistics about the ticker database."""

import logging
from collections import Counter

from sqlalchemy import func, text

from app.db.models import Ticker
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def display_ticker_stats():
    """Display comprehensive ticker statistics."""
    print("\n" + "=" * 60)
    print("ALEXSTOCKS - TICKER DATABASE STATISTICS")
    print("=" * 60)

    db = SessionLocal()
    try:
        # Basic counts
        total_tickers = db.query(Ticker).count()
        sp500_count = db.query(Ticker).filter(Ticker.is_sp500).count()

        print("\n📊 OVERVIEW")
        print(f"   Total Tickers: {total_tickers:,}")
        print(f"   S&P 500 Companies: {sp500_count}")
        print(f"   Regular Tickers: {total_tickers - sp500_count:,}")

        # Exchange breakdown
        print("\n🏛️  EXCHANGE BREAKDOWN")
        exchange_stats = (
            db.query(Ticker.exchange, func.count(Ticker.symbol))
            .group_by(Ticker.exchange)
            .order_by(func.count(Ticker.symbol).desc())
            .all()
        )

        for exchange, count in exchange_stats[:10]:  # Top 10 exchanges
            exchange_name = exchange or "Unknown"
            print(f"   {exchange_name:<15}: {count:>6,}")

        # Source breakdown
        print("\n📡 DATA SOURCES")

        # Get all sources (since sources is JSONB array)
        all_sources: Counter[str] = Counter()
        all_tickers = db.query(Ticker.sources).all()

        for (sources,) in all_tickers:
            if sources:
                for source in sources:
                    all_sources[source] += 1

        for source, count in all_sources.most_common():
            source_name = {
                "current": "Current (Original)",
                "nasdaq": "NASDAQ Listed",
                "nyse_other": "NYSE/Other Listed",
                "sp500": "S&P 500",
                "sec_cik": "SEC CIK Database",
            }.get(source, source.title())

            print(f"   {source_name:<20}: {count:>6,}")

        # Sample of new high-profile tickers
        print("\n🔍 SAMPLE OF EXPANDED COVERAGE")

        # Look for some well-known tickers that weren't in the original 58
        sample_symbols = [
            "TSMC",
            "BABA",
            "BTC-USD",
            "ETH-USD",
            "RIVN",
            "COIN",
            "PLTR",
            "SNOW",
            "ZM",
            "DOCU",
        ]
        found_samples = []

        for symbol in sample_symbols:
            ticker = db.query(Ticker).filter(Ticker.symbol == symbol).first()
            if ticker:
                found_samples.append(f"   {ticker.symbol:<10}: {ticker.name}")

        for sample in found_samples[:8]:  # Show up to 8
            print(sample)

        # Show S&P 500 companies
        print("\n🏆 S&P 500 SAMPLE")
        sp500_sample = db.query(Ticker).filter(Ticker.is_sp500).limit(8).all()

        for ticker in sp500_sample:
            print(f"   {ticker.symbol:<10}: {ticker.name}")

        # Ticker name length analysis
        print("\n📝 TICKER NAME ANALYSIS")

        avg_name_length = db.execute(
            text("SELECT AVG(LENGTH(name)) FROM ticker")
        ).scalar()

        longest_names = (
            db.query(Ticker.symbol, Ticker.name)
            .order_by(func.length(Ticker.name).desc())
            .limit(3)
            .all()
        )

        print(f"   Average name length: {avg_name_length:.1f} characters")
        print("   Longest company names:")
        for symbol, name in longest_names:
            truncated_name = name[:50] + "..." if len(name) > 50 else name
            print(f"     {symbol}: {truncated_name}")

        # Aliases analysis
        print("\n🏷️  ALIASES ANALYSIS")

        total_aliases = (
            db.execute(
                text(
                    "SELECT SUM(jsonb_array_length(aliases)) FROM ticker WHERE aliases IS NOT NULL"
                )
            ).scalar()
            or 0
        )

        tickers_with_aliases = (
            db.execute(
                text(
                    "SELECT COUNT(*) FROM ticker WHERE jsonb_array_length(aliases) > 0"
                )
            ).scalar()
            or 0
        )

        avg_aliases = total_aliases / total_tickers if total_tickers > 0 else 0

        print(f"   Total aliases: {total_aliases:,}")
        print(f"   Tickers with aliases: {tickers_with_aliases:,}")
        print(f"   Average aliases per ticker: {avg_aliases:.1f}")

        print("\n✅ Database is ready for enhanced market coverage!")
        print("=" * 60)

    except Exception as e:
        logger.error(f"Failed to generate ticker stats: {e}")
        print(f"❌ Error generating stats: {e}")
    finally:
        db.close()


def main():
    """Main function."""
    logging.basicConfig(level=logging.WARNING)  # Reduce noise
    display_ticker_stats()


if __name__ == "__main__":
    main()
