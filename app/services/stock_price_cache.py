"""Helpers for ensuring stock price data stays fresh on demand."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.models import StockPrice
from app.services.stock_data import stock_service

logger = logging.getLogger(__name__)


def _is_fresh(
    record: StockPrice | None, cutoff: datetime, force_refresh: bool = False
) -> bool:
    """Return True when a DB record is fresh enough to reuse."""
    if record is None or force_refresh:
        return False

    updated_at = record.updated_at
    # Ensure timezone-aware comparison
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)

    return updated_at >= cutoff


async def ensure_fresh_stock_price(
    db: Session,
    symbol: str,
    *,
    freshness_minutes: int = 15,
    force_refresh: bool = False,
) -> StockPrice | None:
    """
    Ensure the given symbol has a fresh StockPrice row in the database.

    Returns the up-to-date StockPrice instance (or None when data is unavailable).
    """
    symbol = symbol.upper()
    now = datetime.now(UTC)
    freshness_cutoff = now - timedelta(minutes=freshness_minutes)

    existing = db.query(StockPrice).filter(StockPrice.symbol == symbol).first()
    if _is_fresh(existing, freshness_cutoff, force_refresh):
        return existing

    logger.info(
        "Refreshing stock price for %s (stale or missing, force=%s)",
        symbol,
        force_refresh,
    )

    try:
        data = await stock_service.get_stock_price(symbol)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Failed to fetch price for %s: %s", symbol, exc)
        return existing

    if not data:
        logger.warning("No stock price data returned for %s", symbol)
        return existing

    if existing is None:
        existing = StockPrice(symbol=symbol)
        db.add(existing)

    # Basic price data
    price = data.get("price")
    if price is None:
        logger.error("No price data available for %s", symbol)
        return existing
    existing.price = price
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

    try:
        db.commit()
    except Exception as exc:  # pragma: no cover - DB failure path
        logger.error("Failed to commit stock price for %s: %s", symbol, exc)
        db.rollback()
        return existing

    db.refresh(existing)
    return existing
