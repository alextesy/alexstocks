"""Stock price data collector for Market Pulse."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.db.models import StockDataCollection, StockPrice, StockPriceHistory, Ticker
from app.db.session import SessionLocal
from app.services.stock_data import StockDataService

logger = logging.getLogger(__name__)


class StockPriceCollector:
    """Collector for stock price data."""

    def __init__(self):
        self.stock_service = StockDataService()

    async def collect_current_prices(
        self, db: Session, symbols: list[str] | None = None
    ) -> dict:
        """Collect current stock prices for all or specified tickers."""
        collection_run = StockDataCollection(
            collection_type="current",
            symbols_requested=0,
            symbols_success=0,
            symbols_failed=0,
        )
        db.add(collection_run)
        db.commit()

        try:
            # Get symbols to update
            if symbols is None:
                symbols = [ticker.symbol for ticker in db.query(Ticker).all()]

            collection_run.symbols_requested = len(symbols)
            db.commit()

            logger.info(f"Collecting current prices for {len(symbols)} symbols")

            errors = []
            success_count = 0
            failed_count = 0

            # Process in batches to avoid rate limiting
            batch_size = 10
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i : i + batch_size]
                logger.info(
                    f"Processing batch {i//batch_size + 1}/{(len(symbols)-1)//batch_size + 1}"
                )

                # Get stock data for batch
                results = await self.stock_service.get_multiple_prices(batch)

                for symbol, stock_data in results.items():
                    try:
                        if stock_data:
                            # Update or create stock price record
                            existing = (
                                db.query(StockPrice)
                                .filter(StockPrice.symbol == symbol)
                                .first()
                            )

                            if existing:
                                existing.price = stock_data["price"]
                                existing.previous_close = stock_data["previous_close"]
                                existing.change = stock_data["change"]
                                existing.change_percent = stock_data["change_percent"]
                                existing.market_state = stock_data["market_state"]
                                existing.currency = stock_data["currency"]
                                existing.exchange = stock_data["exchange"]
                                existing.updated_at = datetime.now(UTC)
                            else:
                                new_price = StockPrice(
                                    symbol=symbol,
                                    price=stock_data["price"],
                                    previous_close=stock_data["previous_close"],
                                    change=stock_data["change"],
                                    change_percent=stock_data["change_percent"],
                                    market_state=stock_data["market_state"],
                                    currency=stock_data["currency"],
                                    exchange=stock_data["exchange"],
                                    updated_at=datetime.now(UTC),
                                )
                                db.add(new_price)

                            success_count += 1
                            logger.debug(
                                f"Updated price for {symbol}: ${stock_data['price']}"
                            )
                        else:
                            failed_count += 1
                            error_msg = f"No data returned for {symbol}"
                            errors.append(error_msg)
                            logger.warning(error_msg)

                    except Exception as e:
                        failed_count += 1
                        error_msg = f"Error updating {symbol}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg)

                # Commit after each batch
                db.commit()

                # Small delay between batches
                if i + batch_size < len(symbols):
                    await asyncio.sleep(1)

            # Update collection run
            collection_run.symbols_success = success_count
            collection_run.symbols_failed = failed_count
            collection_run.errors = errors[:100]  # Limit errors stored
            collection_run.completed_at = datetime.now(UTC)
            collection_run.duration_seconds = (
                collection_run.completed_at - collection_run.started_at
            ).total_seconds()

            db.commit()

            logger.info(
                f"Current price collection completed: {success_count} success, {failed_count} failed"
            )

            return {
                "success": success_count,
                "failed": failed_count,
                "errors": errors,
                "duration": collection_run.duration_seconds,
            }

        except Exception as e:
            collection_run.errors = [f"Collection failed: {str(e)}"]
            collection_run.completed_at = datetime.now(UTC)
            db.rollback()
            logger.error(f"Stock price collection failed: {e}")
            raise

    async def collect_historical_data(
        self,
        db: Session,
        symbols: list[str] | None = None,
        period: str = "1mo",
        force_refresh: bool = False,
    ) -> dict:
        """Collect historical stock price data."""
        collection_run = StockDataCollection(
            collection_type="historical",
            symbols_requested=0,
            symbols_success=0,
            symbols_failed=0,
        )
        db.add(collection_run)
        db.commit()

        try:
            # Get symbols to update
            if symbols is None:
                symbols = [ticker.symbol for ticker in db.query(Ticker).all()]

            collection_run.symbols_requested = len(symbols)
            db.commit()

            logger.info(f"Collecting historical data for {len(symbols)} symbols")

            errors = []
            success_count = 0
            failed_count = 0

            for symbol in symbols:
                try:
                    # Check if we need to update historical data
                    latest_record = (
                        db.query(StockPriceHistory)
                        .filter(StockPriceHistory.symbol == symbol)
                        .order_by(StockPriceHistory.date.desc())
                        .first()
                    )

                    # Skip if we have recent data and not forcing refresh
                    if (
                        not force_refresh
                        and latest_record
                        and latest_record.date.date()
                        >= (datetime.now().date() - timedelta(days=1))
                    ):
                        logger.debug(f"Skipping {symbol}, recent data exists")
                        success_count += 1
                        continue

                    # Get historical data
                    hist_data = await self.stock_service.get_historical_data(
                        symbol, period
                    )

                    if hist_data and hist_data.get("data"):
                        # Clear old data if force refresh
                        if force_refresh:
                            db.query(StockPriceHistory).filter(
                                StockPriceHistory.symbol == symbol
                            ).delete()

                        # Insert new data
                        for point in hist_data["data"]:
                            # Check if this date already exists
                            date_obj = datetime.strptime(
                                point["date"], "%Y-%m-%d"
                            ).replace(tzinfo=UTC)
                            existing = (
                                db.query(StockPriceHistory)
                                .filter(
                                    and_(
                                        StockPriceHistory.symbol == symbol,
                                        func.date(StockPriceHistory.date)
                                        == date_obj.date(),
                                    )
                                )
                                .first()
                            )

                            if not existing:
                                history_record = StockPriceHistory(
                                    symbol=symbol,
                                    date=date_obj,
                                    close_price=point["price"],
                                    volume=point.get("volume", 0),
                                    created_at=datetime.now(UTC),
                                )
                                db.add(history_record)

                        success_count += 1
                        logger.debug(
                            f"Updated historical data for {symbol}: {len(hist_data['data'])} points"
                        )
                    else:
                        failed_count += 1
                        error_msg = f"No historical data for {symbol}"
                        errors.append(error_msg)
                        logger.warning(error_msg)

                except Exception as e:
                    failed_count += 1
                    error_msg = f"Error updating historical data for {symbol}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)

                # Commit periodically and add delay
                if success_count % 5 == 0:
                    db.commit()
                    await asyncio.sleep(0.5)

            # Final commit
            db.commit()

            # Update collection run
            collection_run.symbols_success = success_count
            collection_run.symbols_failed = failed_count
            collection_run.errors = errors[:100]
            collection_run.completed_at = datetime.now(UTC)
            collection_run.duration_seconds = (
                collection_run.completed_at - collection_run.started_at
            ).total_seconds()

            db.commit()

            logger.info(
                f"Historical data collection completed: {success_count} success, {failed_count} failed"
            )

            return {
                "success": success_count,
                "failed": failed_count,
                "errors": errors,
                "duration": collection_run.duration_seconds,
            }

        except Exception as e:
            collection_run.errors = [f"Collection failed: {str(e)}"]
            collection_run.completed_at = datetime.now(UTC)
            db.rollback()
            logger.error(f"Historical data collection failed: {e}")
            raise


async def main():
    """Main function for testing the collector."""
    logging.basicConfig(level=logging.INFO)

    collector = StockPriceCollector()
    db = SessionLocal()

    try:
        # Test current price collection
        print("Testing current price collection...")
        result = await collector.collect_current_prices(
            db, symbols=["AAPL", "NVDA", "MSFT"]
        )
        print(f"Current prices: {result}")

        # Test historical data collection
        print("\nTesting historical data collection...")
        result = await collector.collect_historical_data(
            db, symbols=["AAPL"], period="5d"
        )
        print(f"Historical data: {result}")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
