"""Stock price service with caching, validation, and on-demand refresh logic."""

import logging
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker, StockPrice
from app.services.stock_data import StockDataService

logger = logging.getLogger(__name__)

# Constants
PRICE_FRESHNESS_THRESHOLD_MINUTES = 30
TOP_N_TICKERS = 50


class StockPriceService:
    """Service for managing stock price data with caching and validation."""

    def __init__(self):
        self.stock_data_service = StockDataService()

    def validate_price_data(self, data: dict) -> bool:
        """
        Validate price data to ensure it's usable.

        Returns False if:
        - Price is None, NaN, zero, or negative
        - Price is invalid (e.g., extremely large or small)
        """
        if not data:
            return False

        price = data.get("price")

        # Check for None
        if price is None:
            logger.warning(f"Price is None for {data.get('symbol')}")
            return False

        # Check for NaN
        if math.isnan(price):
            logger.warning(f"Price is NaN for {data.get('symbol')}")
            return False

        # Check for zero or negative
        if price <= 0:
            logger.warning(
                f"Price is zero or negative ({price}) for {data.get('symbol')}"
            )
            return False

        # Check for unrealistic values (sanity check)
        if price > 1000000:  # More than $1M per share is suspicious
            logger.warning(
                f"Price is unrealistically high ({price}) for {data.get('symbol')}"
            )
            return False

        return True

    def is_price_stale(self, stock_price: StockPrice | None) -> bool:
        """Check if the cached price is older than the freshness threshold."""
        if not stock_price or not stock_price.updated_at:
            return True

        now = datetime.now(UTC)
        age = now - stock_price.updated_at

        return age > timedelta(minutes=PRICE_FRESHNESS_THRESHOLD_MINUTES)

    async def get_or_refresh_price(
        self, db: Session, symbol: str, force_refresh: bool = False
    ) -> dict | None:
        """
        Get stock price from cache or refresh if stale.

        This implements Tier 2 on-demand fetching:
        - Check cache first
        - If stale (>30 min) or force_refresh, fetch new data
        - Validate and update database
        - Return formatted data
        """
        symbol = symbol.upper()

        # Get cached price
        cached_price = db.query(StockPrice).filter(StockPrice.symbol == symbol).first()

        # Check if refresh is needed
        needs_refresh = force_refresh or self.is_price_stale(cached_price)

        if not needs_refresh and cached_price:
            logger.debug(
                f"Using cached price for {symbol} (age: {datetime.now(UTC) - cached_price.updated_at})"
            )
            return self._format_stock_price(cached_price)

        # Fetch fresh data
        logger.info(f"Fetching fresh price data for {symbol}")
        fresh_data = await self.stock_data_service.get_stock_price(symbol)

        # Validate data
        if not fresh_data or not self.validate_price_data(fresh_data):
            logger.warning(f"Invalid price data received for {symbol}")
            # Return cached data if available, even if stale
            if cached_price:
                logger.info(
                    f"Returning stale cached data for {symbol} due to invalid fresh data"
                )
                return self._format_stock_price(cached_price)
            return None

        # Update or create database record (fresh_data is guaranteed to be dict here)
        now = datetime.now(UTC)
        if cached_price:
            cached_price.price = fresh_data["price"]
            cached_price.previous_close = fresh_data.get("previous_close")
            cached_price.change = fresh_data.get("change")
            cached_price.change_percent = fresh_data.get("change_percent")
            cached_price.market_state = fresh_data.get("market_state")
            cached_price.currency = fresh_data.get("currency", "USD")
            cached_price.exchange = fresh_data.get("exchange")
            cached_price.updated_at = now
        else:
            cached_price = StockPrice(
                symbol=symbol,
                price=fresh_data["price"],
                previous_close=fresh_data.get("previous_close"),
                change=fresh_data.get("change"),
                change_percent=fresh_data.get("change_percent"),
                market_state=fresh_data.get("market_state"),
                currency=fresh_data.get("currency", "USD"),
                exchange=fresh_data.get("exchange"),
                updated_at=now,
            )
            db.add(cached_price)

        db.commit()
        db.refresh(cached_price)

        logger.info(f"Updated price for {symbol}: ${cached_price.price}")
        return self._format_stock_price(cached_price)

    def _format_stock_price(self, stock_price: StockPrice) -> dict:
        """Format StockPrice model instance as dictionary for API response."""
        return {
            "symbol": stock_price.symbol,
            "price": stock_price.price,
            "previous_close": stock_price.previous_close,
            "change": stock_price.change,
            "change_percent": stock_price.change_percent,
            "market_state": stock_price.market_state,
            "currency": stock_price.currency,
            "exchange": stock_price.exchange,
            "last_updated": (
                stock_price.updated_at.isoformat() if stock_price.updated_at else None
            ),
        }

    def get_top_n_tickers(
        self, db: Session, n: int = TOP_N_TICKERS, hours: int = 24
    ) -> list[str]:
        """
        Get top N most active tickers by article count in the last N hours.

        This implements Tier 1 ticker selection logic.
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

    async def refresh_top_n_prices(self, db: Session, n: int = TOP_N_TICKERS) -> dict:
        """
        Refresh prices for top N most active tickers.

        This implements Tier 1 automated refresh logic for the top 50.
        Returns statistics about the refresh operation.
        """
        # Get top N tickers
        symbols = self.get_top_n_tickers(db, n=n)

        if not symbols:
            logger.warning("No tickers found for price refresh")
            return {
                "requested": 0,
                "success": 0,
                "failed": 0,
                "errors": [],
            }

        logger.info(f"Refreshing prices for {len(symbols)} top tickers")

        success_count = 0
        failed_count = 0
        errors = []

        # Process in batches to respect rate limits
        batch_size = 5  # Reduced from 10 to be more conservative
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            logger.info(
                f"Processing batch {i//batch_size + 1}/{(len(symbols)-1)//batch_size + 1}: {batch}"
            )

            # Fetch batch
            results = await self.stock_data_service.get_multiple_prices(batch)

            # Process results
            for symbol, data in results.items():
                try:
                    if not data or not self.validate_price_data(data):
                        failed_count += 1
                        error_msg = f"Invalid data for {symbol}"
                        errors.append(error_msg)
                        logger.warning(error_msg)
                        continue

                    # Update database (data is guaranteed to be dict here)
                    now = datetime.now(UTC)
                    existing = (
                        db.query(StockPrice).filter(StockPrice.symbol == symbol).first()
                    )

                    if existing:
                        existing.price = data["price"]
                        existing.previous_close = data.get("previous_close")
                        existing.change = data.get("change")
                        existing.change_percent = data.get("change_percent")
                        existing.market_state = data.get("market_state")
                        existing.currency = data.get("currency", "USD")
                        existing.exchange = data.get("exchange")
                        existing.updated_at = now
                    else:
                        new_price = StockPrice(
                            symbol=symbol,
                            price=data["price"],
                            previous_close=data.get("previous_close"),
                            change=data.get("change"),
                            change_percent=data.get("change_percent"),
                            market_state=data.get("market_state"),
                            currency=data.get("currency", "USD"),
                            exchange=data.get("exchange"),
                            updated_at=now,
                        )
                        db.add(new_price)

                    success_count += 1
                    logger.debug(f"✓ {symbol}: ${data['price']}")

                except Exception as e:
                    failed_count += 1
                    error_msg = f"Error processing {symbol}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)

            # Commit after each batch
            try:
                db.commit()
            except Exception as e:
                logger.error(f"Error committing batch: {e}")
                db.rollback()

        result = {
            "requested": len(symbols),
            "success": success_count,
            "failed": failed_count,
            "errors": errors[:10],  # Limit errors in response
        }

        logger.info(
            f"Top {n} price refresh completed: {success_count}/{len(symbols)} successful, {failed_count} failed"
        )

        return result

    def get_stale_price_count(self, db: Session) -> int:
        """Count how many cached prices are stale (>30 minutes old)."""
        cutoff_time = datetime.now(UTC) - timedelta(
            minutes=PRICE_FRESHNESS_THRESHOLD_MINUTES
        )

        count = db.query(StockPrice).filter(StockPrice.updated_at < cutoff_time).count()

        return count


# Global instance
stock_price_service = StockPriceService()
