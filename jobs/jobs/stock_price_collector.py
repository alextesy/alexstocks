"""
Stock price collector job for top 50 most active tickers.

Runs every 15 minutes to keep homepage stock prices fresh.
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta

# Load environment variables FIRST
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.append(".")

# Now import app modules
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker, StockPrice
from app.db.session import SessionLocal
from app.services.stock_data import StockDataService
from .slack_wrapper import run_with_slack

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class StockPriceCollector:
    """Collects and caches stock prices for the top 50 most active tickers."""

    def __init__(self):
        self.stock_service = StockDataService()

    def get_top_n_tickers(self, db: Session, n: int = 50, hours: int = 24) -> list[str]:
        """
        Get top N most active tickers by article count in the last N hours.

        Args:
            db: Database session
            n: Number of top tickers to return
            hours: Time window in hours

        Returns:
            List of ticker symbols
        """
        cutoff_time = datetime.now(UTC) - timedelta(hours=hours)

        top_tickers = (
            db.query(
                ArticleTicker.ticker,
                func.count(ArticleTicker.article_id).label("article_count"),
            )
            .join(Article, ArticleTicker.article_id == Article.id)
            .filter(Article.published_at >= cutoff_time)
            .group_by(ArticleTicker.ticker)
            .order_by(func.count(ArticleTicker.article_id).desc())
            .limit(n)
            .all()
        )

        symbols = [ticker for ticker, count in top_tickers]
        logger.info(f"Top {n} tickers in last {hours}h: {symbols}")
        return symbols

    def validate_price_data(self, data: dict) -> bool:
        """
        Validate price data to ensure it's usable.

        Returns False if:
        - Price is None, zero, or negative
        - Price is unrealistic (> $1M)
        """
        if not data:
            return False

        price = data.get("price")

        if price is None or price <= 0:
            logger.warning(f"Invalid price ({price}) for {data.get('symbol')}")
            return False

        if price > 1000000:  # Sanity check
            logger.warning(
                f"Unrealistically high price ({price}) for {data.get('symbol')}"
            )
            return False

        return True

    async def refresh_prices(self, db: Session, symbols: list[str]) -> dict:
        """
        Refresh prices for given symbols using optimized concurrent fetching.

        Args:
            db: Database session
            symbols: List of ticker symbols

        Returns:
            Statistics about the refresh operation
        """
        if not symbols:
            logger.warning("No symbols to refresh")
            return {"requested": 0, "success": 0, "failed": 0, "errors": []}

        logger.info(
            f"Refreshing prices for {len(symbols)} symbols using concurrent fetching"
        )

        success_count = 0
        failed_count = 0
        errors = []

        # Fetch all prices concurrently (service handles rate limiting)
        price_data = await self.stock_service.get_multiple_prices(
            symbols, max_concurrent=20
        )

        # Process results and update database
        now = datetime.now(UTC)
        for symbol, data in price_data.items():
            try:
                if not data or not self.validate_price_data(data):
                    failed_count += 1
                    error_msg = f"Invalid data for {symbol}"
                    errors.append(error_msg)
                    logger.warning(error_msg)
                    continue

                # Update or create database record
                existing = (
                    db.query(StockPrice).filter(StockPrice.symbol == symbol).first()
                )

                if existing:
                    # Basic price data
                    existing.price = data["price"]
                    existing.previous_close = data.get("previous_close")
                    existing.change = data.get("change")
                    existing.change_percent = data.get("change_percent")
                    # Intraday trading data
                    existing.open = data.get("open")
                    existing.day_high = data.get("day_high")
                    existing.day_low = data.get("day_low")
                    existing.volume = data.get("volume")
                    # Bid/Ask spread
                    existing.bid = data.get("bid")
                    existing.ask = data.get("ask")
                    existing.bid_size = data.get("bid_size")
                    existing.ask_size = data.get("ask_size")
                    # Market metrics
                    existing.market_cap = data.get("market_cap")
                    existing.shares_outstanding = data.get("shares_outstanding")
                    existing.average_volume = data.get("average_volume")
                    existing.average_volume_10d = data.get("average_volume_10d")
                    # Metadata
                    existing.market_state = data.get("market_state")
                    existing.currency = data.get("currency", "USD")
                    existing.exchange = data.get("exchange")
                    existing.updated_at = now
                else:
                    new_price = StockPrice(
                        symbol=symbol,
                        # Basic price data
                        price=data["price"],
                        previous_close=data.get("previous_close"),
                        change=data.get("change"),
                        change_percent=data.get("change_percent"),
                        # Intraday trading data
                        open=data.get("open"),
                        day_high=data.get("day_high"),
                        day_low=data.get("day_low"),
                        volume=data.get("volume"),
                        # Bid/Ask spread
                        bid=data.get("bid"),
                        ask=data.get("ask"),
                        bid_size=data.get("bid_size"),
                        ask_size=data.get("ask_size"),
                        # Market metrics
                        market_cap=data.get("market_cap"),
                        shares_outstanding=data.get("shares_outstanding"),
                        average_volume=data.get("average_volume"),
                        average_volume_10d=data.get("average_volume_10d"),
                        # Metadata
                        market_state=data.get("market_state"),
                        currency=data.get("currency", "USD"),
                        exchange=data.get("exchange"),
                        updated_at=now,
                    )
                    db.add(new_price)

                success_count += 1
                logger.info(f"✓ {symbol}: ${data['price']}")

            except Exception as e:
                failed_count += 1
                error_msg = f"Error processing {symbol}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)

        # Commit all changes at once
        try:
            db.commit()
            logger.info(f"Successfully committed {success_count} price updates")
        except Exception as e:
            logger.error(f"Error committing to database: {e}")
            db.rollback()
            raise

        result = {
            "requested": len(symbols),
            "success": success_count,
            "failed": failed_count,
            "errors": errors[:10],  # Limit errors in response
        }

        logger.info(
            f"Price refresh completed: {success_count}/{len(symbols)} successful, {failed_count} failed"
        )

        return result

    async def run(self):
        """Main execution method."""
        start_time = datetime.now()
        logger.info("=" * 80)
        logger.info("Starting stock price collection job")
        logger.info("=" * 80)

        db = SessionLocal()

        try:
            # Get top 50 tickers
            symbols = self.get_top_n_tickers(db, n=50, hours=24)

            if not symbols:
                logger.warning("No tickers found in the last 24 hours")
                return {
                    "requested": 0,
                    "success": 0,
                    "failed": 0,
                    "errors": [],
                }

            # Refresh prices
            result = await self.refresh_prices(db, symbols)

            duration = (datetime.now() - start_time).total_seconds()

            # Log results
            logger.info("-" * 80)
            logger.info("Collection Results:")
            logger.info(f"  Requested: {result['requested']}")
            logger.info(f"  Successful: {result['success']}")
            logger.info(f"  Failed: {result['failed']}")
            logger.info(f"  Duration: {duration:.2f}s")

            if result["errors"]:
                logger.warning(f"  Errors (showing first 10): {result['errors']}")

            logger.info("=" * 80)
            logger.info(f"Stock price collection completed in {duration:.2f}s")
            logger.info("=" * 80)

            # Add duration to result for Slack notifications
            result["duration"] = duration

            return result

        except Exception as e:
            logger.error(f"Stock price collection job failed: {e}", exc_info=True)
            raise
        finally:
            db.close()


if __name__ == "__main__":

    def run_job():
        """Wrapper function for Slack integration."""
        collector = StockPriceCollector()
        return asyncio.run(collector.run())

    run_with_slack(
        job_name="stock_price_collector",
        job_func=run_job,
        metadata={},
    )
