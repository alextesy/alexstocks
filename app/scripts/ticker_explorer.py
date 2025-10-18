"""Interactive ticker database explorer."""

import logging
import sys

from sqlalchemy import func, or_

from app.db.models import Ticker
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


class TickerExplorer:
    """Interactive explorer for the ticker database."""

    def __init__(self):
        self.db = SessionLocal()

    def search_tickers(self, query: str, limit: int = 20) -> list[Ticker]:
        """Search tickers by symbol, name, or aliases."""
        query = query.upper().strip()

        # Use text search for aliases array
        from sqlalchemy import text

        # Search in symbol, name, and aliases
        results = (
            self.db.query(Ticker)
            .filter(
                or_(
                    Ticker.symbol.ilike(f"%{query}%"),
                    Ticker.name.ilike(f"%{query}%"),
                    text("aliases::text ILIKE :query"),
                )
            )
            .params(query=f"%{query}%")
            .limit(limit)
            .all()
        )

        return results

    def get_by_exchange(self, exchange: str, limit: int = 20) -> list[Ticker]:
        """Get tickers by exchange."""
        return (
            self.db.query(Ticker).filter(Ticker.exchange == exchange).limit(limit).all()
        )

    def get_sp500_tickers(self, limit: int = 20) -> list[Ticker]:
        """Get S&P 500 tickers."""
        return self.db.query(Ticker).filter(Ticker.is_sp500).limit(limit).all()

    def get_by_source(self, source: str, limit: int = 20) -> list[Ticker]:
        """Get tickers by data source."""
        return (
            self.db.query(Ticker)
            .filter(func.jsonb_array_elements_text(Ticker.sources) == source)
            .limit(limit)
            .all()
        )

    def display_ticker(self, ticker: Ticker):
        """Display detailed information about a ticker."""
        print(f"\n{'='*60}")
        print(f"TICKER: {ticker.symbol}")
        print(f"{'='*60}")
        print(f"Name: {ticker.name}")
        print(f"Exchange: {ticker.exchange or 'Unknown'}")
        print(f"S&P 500: {'Yes' if ticker.is_sp500 else 'No'}")
        print(f"CIK: {ticker.cik or 'N/A'}")
        print(f"Sources: {', '.join(ticker.sources) if ticker.sources else 'None'}")

        if ticker.aliases:
            print(f"Aliases ({len(ticker.aliases)}):")
            for i, alias in enumerate(ticker.aliases[:10], 1):  # Show first 10
                print(f"  {i:2d}. {alias}")
            if len(ticker.aliases) > 10:
                print(f"     ... and {len(ticker.aliases) - 10} more")

    def display_results(self, results: list[Ticker], title: str):
        """Display search results in a table format."""
        if not results:
            print(f"\n❌ No results found for {title}")
            return

        print(f"\n📊 {title} ({len(results)} results)")
        print("-" * 80)
        print(f"{'Symbol':<12} {'Exchange':<10} {'S&P500':<8} {'Company Name':<45}")
        print("-" * 80)

        for ticker in results:
            sp500_flag = "✓" if ticker.is_sp500 else ""
            name = ticker.name[:43] + "..." if len(ticker.name) > 45 else ticker.name
            exchange = ticker.exchange[:8] if ticker.exchange else "Unknown"

            print(f"{ticker.symbol:<12} {exchange:<10} {sp500_flag:<8} {name:<45}")

    def interactive_search(self):
        """Run interactive search session."""
        print("\n" + "=" * 60)
        print("ALEXSTOCKS - TICKER DATABASE EXPLORER")
        print("=" * 60)
        print("\nCommands:")
        print("  search <term>     - Search tickers by symbol, name, or aliases")
        print("  exchange <code>   - Show tickers from specific exchange")
        print("  sp500            - Show S&P 500 companies")
        print("  source <name>    - Show tickers from specific data source")
        print("  info <symbol>    - Show detailed info for a ticker")
        print("  stats            - Show database statistics")
        print("  quit             - Exit explorer")
        print("\nData sources: nasdaq, nyse_other, sp500, sec_cik, current")
        print("Exchanges: NASDAQ, N (NYSE), P, Z, A, etc.")

        while True:
            try:
                command = input("\n🔍 Enter command: ").strip()

                if not command:
                    continue

                if command.lower() in ["quit", "exit", "q"]:
                    print("👋 Goodbye!")
                    break

                parts = command.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""

                if cmd == "search" and arg:
                    results = self.search_tickers(arg)
                    self.display_results(results, f"Search: '{arg}'")

                elif cmd == "exchange" and arg:
                    results = self.get_by_exchange(arg.upper())
                    self.display_results(results, f"Exchange: {arg.upper()}")

                elif cmd == "sp500":
                    results = self.get_sp500_tickers(50)  # Show more S&P 500
                    self.display_results(results, "S&P 500 Companies")

                elif cmd == "source" and arg:
                    results = self.get_by_source(arg.lower())
                    self.display_results(results, f"Source: {arg}")

                elif cmd == "info" and arg:
                    ticker = (
                        self.db.query(Ticker)
                        .filter(Ticker.symbol == arg.upper())
                        .first()
                    )
                    if ticker:
                        self.display_ticker(ticker)
                    else:
                        print(f"❌ Ticker '{arg.upper()}' not found")

                elif cmd == "stats":
                    from app.scripts.ticker_stats import display_ticker_stats

                    display_ticker_stats()

                else:
                    print("❌ Invalid command or missing argument")

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")

    def close(self):
        """Close database connection."""
        self.db.close()


def main():
    """Main function."""
    logging.basicConfig(level=logging.WARNING)

    if len(sys.argv) > 1:
        # Command-line mode
        explorer = TickerExplorer()
        try:
            command = " ".join(sys.argv[1:])

            if command.startswith("search "):
                query = command[7:]
                results = explorer.search_tickers(query)
                explorer.display_results(results, f"Search: '{query}'")

            elif command.startswith("info "):
                symbol = command[5:].upper()
                ticker = (
                    explorer.db.query(Ticker).filter(Ticker.symbol == symbol).first()
                )
                if ticker:
                    explorer.display_ticker(ticker)
                else:
                    print(f"❌ Ticker '{symbol}' not found")

            elif command == "stats":
                from app.scripts.ticker_stats import display_ticker_stats

                display_ticker_stats()

            else:
                print(
                    "Usage: python ticker_explorer.py [search <term>|info <symbol>|stats]"
                )

        finally:
            explorer.close()

    else:
        # Interactive mode
        explorer = TickerExplorer()
        try:
            explorer.interactive_search()
        finally:
            explorer.close()


if __name__ == "__main__":
    main()
