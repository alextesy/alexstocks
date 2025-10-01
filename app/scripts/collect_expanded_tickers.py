"""Collect and merge tickers from multiple sources."""

import csv
import json
import logging
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Source URLs
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
NYSE_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SEC_CIK_URL = "https://www.sec.gov/files/company_tickers.json"


class TickerCollector:
    """Collect tickers from various sources and merge with existing data."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
        )
        self.collected_tickers: dict[str, dict] = {}

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize ticker symbol."""
        if not symbol:
            return ""
        # Remove spaces and convert to uppercase
        symbol = symbol.strip().upper()
        # Handle some common formats
        symbol = symbol.replace(".", "-")  # Some sources use dots instead of dashes
        return symbol

    def normalize_name(self, name: str) -> str:
        """Normalize company name."""
        if not name:
            return ""
        # Remove extra whitespace and common suffixes
        name = re.sub(r"\s+", " ", name.strip())
        # Remove common corporate suffixes for cleaner names
        name = re.sub(
            r"\s+(Inc\.?|Corp\.?|Corporation|Co\.?|Company|Ltd\.?|Limited|LLC|L\.P\.)\s*$",
            "",
            name,
            flags=re.IGNORECASE,
        )
        return name.strip()

    def generate_aliases(self, symbol: str, name: str) -> list[str]:
        """Generate aliases for a ticker."""
        aliases = []

        # Add the symbol with $ prefix
        aliases.append(f"${symbol}")

        # Add lowercase symbol
        aliases.append(symbol.lower())

        # Add company name variations
        if name:
            # Full name
            aliases.append(name.lower())

            # Remove common words and create variations
            name_words = name.lower().split()
            filtered_words = [
                w
                for w in name_words
                if w
                not in {
                    "inc",
                    "corp",
                    "corporation",
                    "co",
                    "company",
                    "ltd",
                    "limited",
                    "llc",
                    "the",
                    "group",
                    "holdings",
                }
            ]

            if len(filtered_words) >= 1:
                # Single word company name
                if len(filtered_words) == 1:
                    aliases.append(filtered_words[0])
                # Multi-word company name combinations
                elif len(filtered_words) <= 3:
                    aliases.append(" ".join(filtered_words))
                    if len(filtered_words) >= 2:
                        aliases.append(filtered_words[0])  # First word only

        return list(set(aliases))  # Remove duplicates

    def collect_nasdaq_tickers(self) -> dict[str, dict]:
        """Collect tickers from NASDAQ."""
        logger.info("Collecting NASDAQ tickers...")
        tickers = {}

        try:
            response = self.session.get(NASDAQ_URL, timeout=30)
            response.raise_for_status()

            lines = response.text.strip().split("\n")
            # Skip header and footer
            for line in lines[1:]:
                if line.startswith("File Creation Time:"):
                    break

                parts = line.split("|")
                if len(parts) >= 2:
                    symbol = self.normalize_symbol(parts[0])
                    name = self.normalize_name(parts[1])

                    if symbol and name:
                        tickers[symbol] = {
                            "symbol": symbol,
                            "name": name,
                            "exchange": "NASDAQ",
                            "sources": ["nasdaq"],
                            "aliases": self.generate_aliases(symbol, name),
                        }

            logger.info(f"Collected {len(tickers)} NASDAQ tickers")
            return tickers

        except Exception as e:
            logger.error(f"Failed to collect NASDAQ tickers: {e}")
            return {}

    def collect_nyse_tickers(self) -> dict[str, dict]:
        """Collect tickers from NYSE and other exchanges."""
        logger.info("Collecting NYSE/Other tickers...")
        tickers = {}

        try:
            response = self.session.get(NYSE_URL, timeout=30)
            response.raise_for_status()

            lines = response.text.strip().split("\n")
            # Skip header and footer
            for line in lines[1:]:
                if line.startswith("File Creation Time:"):
                    break

                parts = line.split("|")
                if len(parts) >= 3:
                    symbol = self.normalize_symbol(parts[0])
                    name = self.normalize_name(parts[1])
                    exchange = parts[2] if len(parts) > 2 else "NYSE"

                    if symbol and name:
                        tickers[symbol] = {
                            "symbol": symbol,
                            "name": name,
                            "exchange": exchange,
                            "sources": ["nyse_other"],
                            "aliases": self.generate_aliases(symbol, name),
                        }

            logger.info(f"Collected {len(tickers)} NYSE/Other tickers")
            return tickers

        except Exception as e:
            logger.error(f"Failed to collect NYSE/Other tickers: {e}")
            return {}

    def collect_sp500_tickers(self) -> dict[str, dict]:
        """Collect S&P 500 tickers from Wikipedia."""
        logger.info("Collecting S&P 500 tickers...")
        tickers = {}

        try:
            response = self.session.get(SP500_URL, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Find the main S&P 500 table
            table = soup.find("table", {"id": "constituents"})
            if not table:
                # Fallback to first table with headers
                tables = soup.find_all("table", class_="wikitable")
                for t in tables:
                    headers = t.find("tr")
                    if headers and "Symbol" in headers.get_text():
                        table = t
                        break

            if table:
                rows = table.find_all("tr")[1:]  # Skip header
                for row in rows:
                    cells = row.find_all(["td", "th"])
                    if len(cells) >= 2:
                        # Symbol is usually first column, company name second
                        symbol_cell = cells[0].get_text(strip=True)
                        name_cell = cells[1].get_text(strip=True)

                        symbol = self.normalize_symbol(symbol_cell)
                        name = self.normalize_name(name_cell)

                        if symbol and name:
                            tickers[symbol] = {
                                "symbol": symbol,
                                "name": name,
                                "exchange": "S&P_500",
                                "sources": ["sp500"],
                                "aliases": self.generate_aliases(symbol, name),
                                "is_sp500": True,
                            }

            logger.info(f"Collected {len(tickers)} S&P 500 tickers")
            return tickers

        except Exception as e:
            logger.error(f"Failed to collect S&P 500 tickers: {e}")
            return {}

    def collect_sec_cik_tickers(self) -> dict[str, dict]:
        """Collect tickers from SEC CIK data."""
        logger.info("Collecting SEC CIK tickers...")
        tickers = {}

        try:
            response = self.session.get(SEC_CIK_URL, timeout=30)
            response.raise_for_status()

            data = response.json()

            # The SEC data is structured as: CIK -> {cik_str, ticker, title}
            for _cik, company_info in data.items():
                symbol = self.normalize_symbol(company_info.get("ticker", ""))
                name = self.normalize_name(company_info.get("title", ""))
                cik_str = company_info.get("cik_str", "")

                if symbol and name:
                    tickers[symbol] = {
                        "symbol": symbol,
                        "name": name,
                        "exchange": "SEC",
                        "sources": ["sec_cik"],
                        "cik": cik_str,
                        "aliases": self.generate_aliases(symbol, name),
                    }

            logger.info(f"Collected {len(tickers)} SEC CIK tickers")
            return tickers

        except Exception as e:
            logger.error(f"Failed to collect SEC CIK tickers: {e}")
            return {}

    def load_current_tickers(self) -> dict[str, dict]:
        """Load current tickers from CSV."""
        logger.info("Loading current tickers from CSV...")
        tickers = {}

        csv_path = Path("data/tickers_core.csv")
        if not csv_path.exists():
            logger.warning("Current tickers CSV not found")
            return {}

        try:
            with open(csv_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = self.normalize_symbol(row["symbol"])
                    name = self.normalize_name(row["name"])

                    # Parse existing aliases
                    aliases = []
                    if row.get("aliases"):
                        try:
                            aliases = json.loads(row["aliases"])
                        except json.JSONDecodeError:
                            pass

                    if symbol and name:
                        tickers[symbol] = {
                            "symbol": symbol,
                            "name": name,
                            "exchange": "CURRENT",
                            "sources": ["current"],
                            "aliases": aliases,
                        }

            logger.info(f"Loaded {len(tickers)} current tickers")
            return tickers

        except Exception as e:
            logger.error(f"Failed to load current tickers: {e}")
            return {}

    def merge_ticker_data(self, *ticker_sources: dict[str, dict]) -> dict[str, dict]:
        """Merge ticker data from multiple sources."""
        logger.info("Merging ticker data from all sources...")

        merged = {}

        for source_tickers in ticker_sources:
            for symbol, ticker_data in source_tickers.items():
                if symbol in merged:
                    # Merge data for existing ticker
                    existing = merged[symbol]

                    # Combine sources
                    existing["sources"].extend(ticker_data["sources"])
                    existing["sources"] = list(set(existing["sources"]))

                    # Use more complete name if available
                    if len(ticker_data["name"]) > len(existing["name"]):
                        existing["name"] = ticker_data["name"]

                    # Combine aliases
                    existing_aliases = set(existing.get("aliases", []))
                    new_aliases = set(ticker_data.get("aliases", []))
                    existing["aliases"] = list(existing_aliases | new_aliases)

                    # Preserve special flags
                    if ticker_data.get("is_sp500"):
                        existing["is_sp500"] = True
                    if ticker_data.get("cik"):
                        existing["cik"] = ticker_data["cik"]

                    # Use better exchange info
                    if (
                        ticker_data["exchange"] != "SEC"
                        and existing["exchange"] == "SEC"
                    ):
                        existing["exchange"] = ticker_data["exchange"]
                    elif ticker_data["exchange"] in ["NASDAQ", "NYSE"] and existing[
                        "exchange"
                    ] not in ["NASDAQ", "NYSE"]:
                        existing["exchange"] = ticker_data["exchange"]

                else:
                    # New ticker
                    merged[symbol] = ticker_data.copy()

        logger.info(f"Merged data for {len(merged)} unique tickers")
        return merged

    def save_merged_tickers(self, merged_tickers: dict[str, dict], output_path: Path):
        """Save merged ticker data to CSV."""
        logger.info(f"Saving merged tickers to {output_path}...")

        with open(output_path, "w", newline="") as f:
            fieldnames = [
                "symbol",
                "name",
                "exchange",
                "sources",
                "aliases",
                "is_sp500",
                "cik",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            writer.writeheader()

            # Sort by symbol for consistent output
            for symbol in sorted(merged_tickers.keys()):
                ticker = merged_tickers[symbol]

                row = {
                    "symbol": ticker["symbol"],
                    "name": ticker["name"],
                    "exchange": ticker["exchange"],
                    "sources": ",".join(ticker["sources"]),
                    "aliases": json.dumps(ticker["aliases"]),
                    "is_sp500": ticker.get("is_sp500", False),
                    "cik": ticker.get("cik", ""),
                }
                writer.writerow(row)

        logger.info(f"Saved {len(merged_tickers)} tickers to {output_path}")

    def collect_all_tickers(self) -> dict[str, dict]:
        """Collect tickers from all sources and merge."""
        logger.info("Starting comprehensive ticker collection...")

        # Collect from all sources
        current_tickers = self.load_current_tickers()
        nasdaq_tickers = self.collect_nasdaq_tickers()
        nyse_tickers = self.collect_nyse_tickers()
        sp500_tickers = self.collect_sp500_tickers()
        sec_tickers = self.collect_sec_cik_tickers()

        # Merge all data
        merged_tickers = self.merge_ticker_data(
            current_tickers, nasdaq_tickers, nyse_tickers, sp500_tickers, sec_tickers
        )

        # Print summary
        logger.info("Collection Summary:")
        logger.info(f"  Current tickers: {len(current_tickers)}")
        logger.info(f"  NASDAQ tickers: {len(nasdaq_tickers)}")
        logger.info(f"  NYSE/Other tickers: {len(nyse_tickers)}")
        logger.info(f"  S&P 500 tickers: {len(sp500_tickers)}")
        logger.info(f"  SEC CIK tickers: {len(sec_tickers)}")
        logger.info(f"  Total unique tickers: {len(merged_tickers)}")

        return merged_tickers


def main():
    """Main function to collect and save expanded ticker data."""
    logging.basicConfig(level=logging.INFO)

    collector = TickerCollector()

    # Collect all tickers
    merged_tickers = collector.collect_all_tickers()

    # Save to multiple formats
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save as CSV
    csv_path = Path(f"data/tickers_expanded_{timestamp}.csv")
    collector.save_merged_tickers(merged_tickers, csv_path)

    # Also create a backup of the current tickers
    backup_path = Path("data/tickers_core_backup.csv")
    current_path = Path("data/tickers_core.csv")
    if current_path.exists():
        import shutil

        shutil.copy2(current_path, backup_path)
        logger.info(f"Backed up current tickers to {backup_path}")

    # Replace current tickers with expanded set
    collector.save_merged_tickers(merged_tickers, current_path)
    logger.info(f"Updated {current_path} with expanded ticker set")

    logger.info("Ticker collection completed successfully!")


if __name__ == "__main__":
    main()
