"""Expand stock_price table with intraday trading data and market metrics."""

import sys

sys.path.append(".")

from sqlalchemy import text

from app.db.session import SessionLocal


def expand_stock_price_table():
    """Add new columns to stock_price table for enhanced stock data."""
    print("=" * 80)
    print("Expanding stock_price table with Phase 1 enhancements...")
    print("=" * 80)

    db = SessionLocal()

    try:
        # Check if columns already exist
        result = db.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'stock_price'
                AND column_name IN ('open', 'day_high', 'day_low', 'volume',
                                    'bid', 'ask', 'market_cap')
            """
            )
        )
        existing_columns = [row[0] for row in result]

        if existing_columns:
            print(f"\n⚠️  Some columns already exist: {existing_columns}")
            response = input("Continue anyway? (y/n): ")
            if response.lower() != "y":
                print("Migration cancelled.")
                return

        print("\n📊 Adding intraday trading data columns...")

        # Add intraday trading data columns
        columns_to_add = [
            ("open", "FLOAT"),
            ("day_high", "FLOAT"),
            ("day_low", "FLOAT"),
            ("volume", "BIGINT"),
        ]

        for col_name, col_type in columns_to_add:
            try:
                db.execute(
                    text(
                        f"ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                    )
                )
                print(f"  ✓ Added column: {col_name} ({col_type})")
            except Exception as e:
                print(f"  ⚠️  Column {col_name} might already exist: {e}")

        print("\n💹 Adding bid/ask spread columns...")

        # Add bid/ask columns
        bid_ask_columns = [
            ("bid", "FLOAT"),
            ("ask", "FLOAT"),
            ("bid_size", "INTEGER"),
            ("ask_size", "INTEGER"),
        ]

        for col_name, col_type in bid_ask_columns:
            try:
                db.execute(
                    text(
                        f"ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                    )
                )
                print(f"  ✓ Added column: {col_name} ({col_type})")
            except Exception as e:
                print(f"  ⚠️  Column {col_name} might already exist: {e}")

        print("\n💼 Adding market metrics columns...")

        # Add market metrics columns
        market_columns = [
            ("market_cap", "BIGINT"),
            ("shares_outstanding", "BIGINT"),
            ("average_volume", "BIGINT"),
            ("average_volume_10d", "BIGINT"),
        ]

        for col_name, col_type in market_columns:
            try:
                db.execute(
                    text(
                        f"ALTER TABLE stock_price ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                    )
                )
                print(f"  ✓ Added column: {col_name} ({col_type})")
            except Exception as e:
                print(f"  ⚠️  Column {col_name} might already exist: {e}")

        db.commit()

        print("\n" + "=" * 80)
        print("✅ Migration completed successfully!")
        print("=" * 80)
        print("\nNew fields added:")
        print("\n📊 Intraday Trading Data:")
        print("  - open: Today's opening price")
        print("  - day_high: Today's high")
        print("  - day_low: Today's low")
        print("  - volume: Trading volume today")
        print("\n💹 Bid/Ask Spread:")
        print("  - bid: Current bid price")
        print("  - ask: Current ask price")
        print("  - bid_size: Bid size")
        print("  - ask_size: Ask size")
        print("\n💼 Market Metrics:")
        print("  - market_cap: Market capitalization")
        print("  - shares_outstanding: Total shares")
        print("  - average_volume: Average daily volume (3 month)")
        print("  - average_volume_10d: 10-day average volume")
        print("\n" + "=" * 80)
        print("\n🎯 Next steps:")
        print("  1. The StockDataService has been updated to capture these fields")
        print("  2. Run stock_price_collector to populate the new fields")
        print("  3. Existing records will have NULL values until next update")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Error during migration: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    expand_stock_price_table()
