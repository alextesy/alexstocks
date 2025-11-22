"""Stock price data collector for Market Pulse."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.db.models import (
    BackfillProgress,
    StockDataCollection,
    StockPrice,
    StockPriceHistory,
    Ticker,
)
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

            # Ensure started_at is timezone-aware for duration calculation
            started_at = collection_run.started_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=UTC)

            collection_run.duration_seconds = (
                collection_run.completed_at - started_at
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

            # Ensure started_at is timezone-aware for duration calculation
            started_at = collection_run.started_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=UTC)

            collection_run.duration_seconds = (
                collection_run.completed_at - started_at
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

    async def collect_historical_backfill(
        self,
        db: Session,
        run_id: str,
        start_date: datetime,
        end_date: datetime | None = None,
        symbols: list[str] | None = None,
        min_article_threshold: int = 10,
        batch_size: int = 50,
        delay_between_batches: float = 2.0,
        resume: bool = True,
    ) -> dict:
        """
        Backfill historical hourly stock price data with durability and rate limit handling.

        Args:
            db: Database session
            run_id: Unique identifier for this backfill run (for resumability)
            start_date: Start date for backfill (timezone-aware)
            end_date: End date for backfill (defaults to now)
            symbols: Optional list of specific symbols to backfill (bypasses threshold query)
            min_article_threshold: Minimum number of articles to include ticker (ignored if symbols provided)
            batch_size: Number of tickers to process before committing
            delay_between_batches: Seconds to wait between batches
            resume: Whether to skip already processed tickers

        Returns:
            Statistics about the backfill operation
        """
        if end_date is None:
            end_date = datetime.now(UTC)

        # Ensure dates are timezone-aware
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=UTC)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=UTC)

        logger.info("=" * 80)
        logger.info("Starting Historical Price Backfill")
        logger.info(f"Run ID: {run_id}")
        logger.info(f"Date range: {start_date.date()} to {end_date.date()}")
        logger.info(f"Min article threshold: {min_article_threshold}")
        logger.info(f"Batch size: {batch_size}")
        logger.info(f"Resume mode: {resume}")
        logger.info("=" * 80)

        # Get symbols to backfill
        if symbols is not None:
            # Use provided symbols (for testing)
            logger.info(f"Using provided symbols: {symbols}")
        else:
            # Get active tickers (those with sufficient article coverage)
            from app.db.models import ArticleTicker

            active_tickers_subq = (
                db.query(ArticleTicker.ticker, func.count().label("article_count"))
                .group_by(ArticleTicker.ticker)
                .having(func.count() >= min_article_threshold)
                .subquery()
            )

            active_tickers = (
                db.query(
                    Ticker.symbol,
                    active_tickers_subq.c.article_count,
                )
                .join(
                    active_tickers_subq,
                    Ticker.symbol == active_tickers_subq.c.ticker,
                )
                .order_by(Ticker.symbol)
                .all()
            )

            symbols = [symbol for symbol, count in active_tickers]
            logger.info(f"Found {len(symbols)} active tickers to backfill")

        if not symbols:
            logger.warning("No active tickers found matching criteria")
            return {
                "run_id": run_id,
                "requested": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "rate_limited": 0,
                "errors": [],
            }

        # If resuming, skip already processed symbols
        processed_symbols = set()
        if resume:
            processed = (
                db.query(BackfillProgress.symbol)
                .filter(
                    BackfillProgress.run_id == run_id,
                    BackfillProgress.status.in_(["success", "rate_limited"]),
                )
                .all()
            )
            processed_symbols = {symbol for (symbol,) in processed}
            if processed_symbols:
                logger.info(
                    f"Resuming: skipping {len(processed_symbols)} already processed tickers"
                )
                symbols = [s for s in symbols if s not in processed_symbols]

        logger.info(f"Processing {len(symbols)} tickers")

        success_count = 0
        failed_count = 0
        skipped_count = len(processed_symbols)
        rate_limited_count = 0
        errors = []

        # Process in batches
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(symbols) - 1) // batch_size + 1

            logger.info("-" * 80)
            logger.info(
                f"Processing batch {batch_num}/{total_batches}: {', '.join(batch)}"
            )

            for symbol in batch:
                # Check if progress row already exists (for resume mode)
                progress = (
                    db.query(BackfillProgress)
                    .filter(
                        BackfillProgress.run_id == run_id,
                        BackfillProgress.symbol == symbol,
                    )
                    .first()
                )

                if progress:
                    # Update existing progress row
                    logger.debug(
                        f"{symbol}: Resuming from previous status '{progress.status}'"
                    )
                    progress.status = "pending"
                    progress.started_at = datetime.now(UTC)
                    progress.error_message = None
                else:
                    # Create new progress row
                    progress = BackfillProgress(
                        run_id=run_id,
                        symbol=symbol,
                        status="pending",
                        started_at=datetime.now(UTC),
                    )
                    db.add(progress)

                db.flush()  # Ensure we have the ID

                try:
                    logger.info(f"Fetching historical data for {symbol}...")

                    # Determine interval based on date range
                    days_diff = (end_date - start_date).days
                    if days_diff <= 7:
                        interval = "1h"
                    elif days_diff <= 60:
                        interval = "1h"
                    else:
                        interval = "1d"

                    # Get historical data using date range
                    hist_data_list = await self.stock_service.get_historical_data_range(
                        symbol, start=start_date, end=end_date, interval=interval
                    )

                    # Convert list to dict format expected by rest of code
                    hist_data = {"data": hist_data_list} if hist_data_list else None

                    if not hist_data or not hist_data.get("data"):
                        progress.status = "failed"
                        progress.error_message = "No data returned from API"
                        progress.completed_at = datetime.now(UTC)
                        failed_count += 1
                        error_msg = f"{symbol}: No data returned"
                        errors.append(error_msg)
                        logger.warning(error_msg)
                        continue

                    # Filter data to our date range
                    records_to_insert = []
                    for point in hist_data["data"]:
                        try:
                            # Parse the date from the API response
                            # get_historical_data_range returns "timestamp" key
                            if "timestamp" in point:
                                point_date = point["timestamp"]
                                # Ensure timezone-aware
                                if isinstance(point_date, str):
                                    point_date = datetime.fromisoformat(
                                        point_date.replace("Z", "+00:00")
                                    )
                                elif point_date.tzinfo is None:
                                    point_date = point_date.replace(tzinfo=UTC)
                            elif "datetime" in point:
                                point_date = datetime.fromisoformat(
                                    point["datetime"].replace("Z", "+00:00")
                                )
                            elif "date" in point:
                                point_date = datetime.strptime(
                                    point["date"], "%Y-%m-%d"
                                ).replace(tzinfo=UTC)
                            else:
                                logger.debug(
                                    f"Skipping point for {symbol}: no timestamp/datetime/date key"
                                )
                                continue

                            # Check if within our backfill range
                            if start_date <= point_date <= end_date:
                                # get_historical_data_range uses "close", not "price"
                                close_price = point.get("close") or point.get("price")
                                if close_price is None:
                                    logger.debug(
                                        f"Skipping point for {symbol} at {point_date}: no close price"
                                    )
                                    continue

                                records_to_insert.append(
                                    {
                                        "symbol": symbol,
                                        "date": point_date,
                                        "open_price": point.get("open"),
                                        "high_price": point.get("high"),
                                        "low_price": point.get("low"),
                                        "close_price": close_price,
                                        "volume": point.get("volume", 0),
                                        "created_at": datetime.now(UTC),
                                    }
                                )
                        except Exception as parse_error:
                            logger.debug(
                                f"Error parsing data point for {symbol}: {parse_error}"
                            )
                            continue

                    if not records_to_insert:
                        progress.status = "success"
                        progress.records_inserted = 0
                        progress.completed_at = datetime.now(UTC)
                        success_count += 1
                        logger.info(
                            f"{symbol}: No records in date range, marked as success"
                        )
                        continue

                    # Bulk insert with conflict resolution (ignore duplicates)
                    inserted_count = 0
                    for record in records_to_insert:
                        try:
                            # Check if record already exists
                            existing = (
                                db.query(StockPriceHistory)
                                .filter(
                                    and_(
                                        StockPriceHistory.symbol == record["symbol"],
                                        StockPriceHistory.date == record["date"],
                                    )
                                )
                                .first()
                            )

                            if not existing:
                                db.add(StockPriceHistory(**record))
                                inserted_count += 1
                        except Exception as insert_error:
                            logger.debug(
                                f"Skipping duplicate for {symbol} at {record['date']}: {insert_error}"
                            )
                            continue

                    progress.status = "success"
                    progress.records_inserted = inserted_count
                    progress.completed_at = datetime.now(UTC)
                    success_count += 1
                    logger.info(
                        f"✓ {symbol}: Inserted {inserted_count}/{len(records_to_insert)} records"
                    )

                except Exception as e:
                    error_str = str(e).lower()

                    # Check if it's a rate limit error
                    if (
                        "429" in error_str
                        or "rate limit" in error_str
                        or "too many requests" in error_str
                    ):
                        progress.status = "rate_limited"
                        progress.error_message = f"Rate limited: {str(e)}"
                        progress.completed_at = datetime.now(UTC)
                        rate_limited_count += 1
                        error_msg = f"{symbol}: Rate limited - {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                        logger.warning(
                            "Rate limit detected! Consider waiting before resuming."
                        )
                    else:
                        progress.status = "failed"
                        progress.error_message = str(e)[:500]  # Truncate long errors
                        progress.completed_at = datetime.now(UTC)
                        failed_count += 1
                        error_msg = f"{symbol}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg)

            # Commit after each batch for durability
            try:
                db.commit()
                logger.info(
                    f"Batch {batch_num} committed: {success_count} success, {failed_count} failed, {rate_limited_count} rate limited"
                )
            except Exception as commit_error:
                logger.error(f"Error committing batch: {commit_error}")
                db.rollback()
                raise

            # If we hit rate limits, stop processing
            if rate_limited_count > 0:
                logger.warning(
                    "Rate limit encountered. Stopping backfill. Use resume=True to continue later."
                )
                break

            # Delay between batches to avoid rate limiting
            if i + batch_size < len(symbols):
                logger.info(f"Waiting {delay_between_batches}s before next batch...")
                await asyncio.sleep(delay_between_batches)

        logger.info("=" * 80)
        logger.info("Backfill Summary:")
        logger.info(f"  Run ID: {run_id}")
        logger.info(f"  Total requested: {len(symbols) + skipped_count}")
        logger.info(f"  Successful: {success_count}")
        logger.info(f"  Failed: {failed_count}")
        logger.info(f"  Skipped (already done): {skipped_count}")
        logger.info(f"  Rate limited: {rate_limited_count}")
        if errors:
            logger.warning(f"  Errors (first 10): {errors[:10]}")
        logger.info("=" * 80)

        return {
            "run_id": run_id,
            "requested": len(symbols) + skipped_count,
            "success": success_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "rate_limited": rate_limited_count,
            "errors": errors[:100],  # Limit errors in response
        }

    async def collect_daily_historical_append(
        self,
        db: Session,
        symbols: list[str] | None = None,
        days_back: int = 7,
        batch_size: int = 10,
        delay_between_batches: float = 1.0,
        min_article_threshold: int | None = None,
    ) -> dict:
        """
        Append missing historical data for tickers.

        This job:
        - Finds the last date in stock_price_history for each ticker
        - Fetches data from (last_date + 1) to now
        - Inserts any missing records
        - Can be run for specific symbols or all active tickers

        Args:
            db: Database session
            symbols: Optional list of specific symbols (bypasses threshold if provided)
            days_back: Maximum days to look back if no history exists (default: 7)
            batch_size: Number of tickers to process before committing
            delay_between_batches: Seconds to wait between batches
            min_article_threshold: Minimum articles to include ticker (default: None = all tickers)

        Returns:
            Statistics about the append operation
        """
        logger.info("=" * 80)
        logger.info("Starting Daily Historical Stock Price Append")
        logger.info(f"Days back (if no history): {days_back}")
        logger.info(f"Batch size: {batch_size}")
        logger.info("=" * 80)

        now = datetime.now(UTC)

        # Get symbols to process
        if symbols is not None:
            logger.info(f"Using provided symbols: {symbols}")
            tickers_to_process = symbols
        else:
            # Get all active tickers
            if min_article_threshold:
                from app.db.models import ArticleTicker

                active_tickers_subq = (
                    db.query(ArticleTicker.ticker, func.count().label("article_count"))
                    .group_by(ArticleTicker.ticker)
                    .having(func.count() >= min_article_threshold)
                    .subquery()
                )

                tickers = (
                    db.query(Ticker.symbol)
                    .join(
                        active_tickers_subq,
                        Ticker.symbol == active_tickers_subq.c.ticker,
                    )
                    .order_by(Ticker.symbol)
                    .all()
                )
            else:
                # Get all tickers
                tickers = db.query(Ticker.symbol).order_by(Ticker.symbol).all()

            tickers_to_process = [symbol for (symbol,) in tickers]
            logger.info(
                f"Found {len(tickers_to_process)} tickers to check for missing data"
            )

        if not tickers_to_process:
            logger.warning("No tickers found to process")
            return {
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "total_records_inserted": 0,
                "errors": [],
            }

        success_count = 0
        failed_count = 0
        skipped_count = 0
        total_records_inserted = 0
        errors = []

        # Process in batches
        for i in range(0, len(tickers_to_process), batch_size):
            batch = tickers_to_process[i : i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(tickers_to_process) - 1) // batch_size + 1

            logger.info("-" * 80)
            logger.info(
                f"Processing batch {batch_num}/{total_batches}: {', '.join(batch)}"
            )

            for symbol in batch:
                try:
                    # Find the last date we have data for this ticker
                    last_record = (
                        db.query(StockPriceHistory)
                        .filter(StockPriceHistory.symbol == symbol)
                        .order_by(StockPriceHistory.date.desc())
                        .first()
                    )

                    if last_record:
                        # Fetch from last date + 1 hour to now
                        start_date = last_record.date + timedelta(hours=1)
                        logger.info(
                            f"{symbol}: Last data at {last_record.date}, fetching from {start_date}"
                        )
                    else:
                        # No history, fetch last N days
                        start_date = now - timedelta(days=days_back)
                        logger.info(
                            f"{symbol}: No history, fetching last {days_back} days from {start_date}"
                        )

                    # Skip if start_date is in the future or very recent (< 1 hour ago)
                    if start_date >= now - timedelta(hours=1):
                        logger.info(f"{symbol}: Up to date, skipping")
                        skipped_count += 1
                        continue

                    # Determine interval based on date range
                    days_diff = (now - start_date).days
                    if days_diff <= 7:
                        interval = "1h"
                    elif days_diff <= 60:
                        interval = "1h"
                    else:
                        interval = "1d"

                    logger.info(
                        f"{symbol}: Fetching data with interval={interval} from {start_date} to {now}"
                    )

                    # Get historical data
                    hist_data_list = await self.stock_service.get_historical_data_range(
                        symbol, start=start_date, end=now, interval=interval
                    )

                    if not hist_data_list:
                        logger.warning(f"{symbol}: No data returned from API")
                        skipped_count += 1
                        continue

                    # Parse and insert records
                    records_to_insert = []
                    for point in hist_data_list:
                        try:
                            # Parse timestamp
                            if "timestamp" in point:
                                point_date = point["timestamp"]
                                if isinstance(point_date, str):
                                    point_date = datetime.fromisoformat(
                                        point_date.replace("Z", "+00:00")
                                    )
                                elif point_date.tzinfo is None:
                                    point_date = point_date.replace(tzinfo=UTC)
                            elif "datetime" in point:
                                point_date = datetime.fromisoformat(
                                    point["datetime"].replace("Z", "+00:00")
                                )
                            elif "date" in point:
                                point_date = datetime.strptime(
                                    point["date"], "%Y-%m-%d"
                                ).replace(tzinfo=UTC)
                            else:
                                continue

                            # Check if within our range
                            if not (start_date <= point_date <= now):
                                continue

                            # Get close price
                            close_price = point.get("close") or point.get("price")
                            if close_price is None:
                                continue

                            records_to_insert.append(
                                {
                                    "symbol": symbol,
                                    "date": point_date,
                                    "open_price": point.get("open"),
                                    "high_price": point.get("high"),
                                    "low_price": point.get("low"),
                                    "close_price": close_price,
                                    "volume": point.get("volume", 0),
                                    "created_at": datetime.now(UTC),
                                }
                            )
                        except Exception as parse_error:
                            logger.debug(
                                f"Error parsing data point for {symbol}: {parse_error}"
                            )
                            continue

                    if not records_to_insert:
                        logger.info(f"{symbol}: No new records to insert")
                        skipped_count += 1
                        continue

                    # Insert records (skip duplicates)
                    inserted_count = 0
                    for record in records_to_insert:
                        try:
                            # Check if record already exists
                            existing = (
                                db.query(StockPriceHistory)
                                .filter(
                                    and_(
                                        StockPriceHistory.symbol == record["symbol"],
                                        StockPriceHistory.date == record["date"],
                                    )
                                )
                                .first()
                            )

                            if not existing:
                                db.add(StockPriceHistory(**record))
                                inserted_count += 1
                        except Exception as insert_error:
                            logger.debug(
                                f"Skipping duplicate for {symbol} at {record['date']}: {insert_error}"
                            )
                            continue

                    total_records_inserted += inserted_count
                    success_count += 1
                    logger.info(
                        f"✓ {symbol}: Inserted {inserted_count}/{len(records_to_insert)} new records"
                    )

                except Exception as e:
                    failed_count += 1
                    error_msg = f"{symbol}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)

            # Commit after each batch
            try:
                db.commit()
                logger.info(
                    f"Batch {batch_num} committed: {success_count} success, {failed_count} failed, {skipped_count} skipped"
                )
            except Exception as commit_error:
                logger.error(f"Error committing batch: {commit_error}")
                db.rollback()
                raise

            # Delay between batches
            if i + batch_size < len(tickers_to_process):
                logger.info(f"Waiting {delay_between_batches}s before next batch...")
                await asyncio.sleep(delay_between_batches)

        logger.info("=" * 80)
        logger.info("Daily Historical Append Summary:")
        logger.info(f"  Total processed: {len(tickers_to_process)}")
        logger.info(f"  Successful: {success_count}")
        logger.info(f"  Failed: {failed_count}")
        logger.info(f"  Skipped (up to date): {skipped_count}")
        logger.info(f"  Total records inserted: {total_records_inserted}")
        if errors:
            logger.warning(f"  Errors (first 10): {errors[:10]}")
        logger.info("=" * 80)

        return {
            "success": success_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "total_records_inserted": total_records_inserted,
            "errors": errors[:100],
        }


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
