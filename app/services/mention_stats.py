"""Mention statistics service for hourly aggregation of ticker mentions.

Follows repo rules:
- Python 3.11, type hints, no global mutable state
- tz-aware UTC timestamps
- Small, pure functions where possible
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Dict, Iterable, List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker
from app.models.dto import MentionsHourlyResponseDTO, MentionsSeriesDTO

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _HourlyKey:
    symbol: str
    hour: datetime


class MentionStatsService:
    """Service to compute hourly mention counts for one or more tickers."""

    def __init__(self, session: Session):
        self.session = session

    def get_mentions_hourly(
        self, tickers: list[str], hours: int = 24
    ) -> MentionsHourlyResponseDTO:
        """Return hourly mention counts for given tickers over the last N hours.

        Args:
            tickers: List of ticker symbols (case-insensitive) to include.
            hours: Number of trailing hours to include (default 24).

        Returns:
            MentionsHourlyResponseDTO with aligned labels and per-ticker series.
        """
        if not tickers:
            return MentionsHourlyResponseDTO(labels=[], series=[], hours=hours)

        normalized = [t.upper().strip() for t in tickers if t and t.strip()]
        if not normalized:
            return MentionsHourlyResponseDTO(labels=[], series=[], hours=hours)

        now = datetime.now(UTC)
        window_start = now - timedelta(hours=hours - 1)

        # Query: group counts by ticker and hour boundary
        # Branch per dialect for portability (SQLite vs Postgres)
        dialect = self.session.get_bind().dialect.name
        counts_by_key: Dict[_HourlyKey, int] = {}

        if dialect == "sqlite":
            rows = (
                self.session.query(
                    ArticleTicker.ticker.label("ticker"),
                    func.strftime("%Y", Article.published_at).label("y"),
                    func.strftime("%m", Article.published_at).label("m"),
                    func.strftime("%d", Article.published_at).label("d"),
                    func.strftime("%H", Article.published_at).label("h"),
                    func.count(Article.id).label("cnt"),
                )
                .join(Article, Article.id == ArticleTicker.article_id)
                .filter(
                    ArticleTicker.ticker.in_(normalized),
                    Article.published_at >= window_start,
                )
                .group_by(
                    ArticleTicker.ticker,
                    func.strftime("%Y", Article.published_at),
                    func.strftime("%m", Article.published_at),
                    func.strftime("%d", Article.published_at),
                    func.strftime("%H", Article.published_at),
                )
                .all()
            )

            for r in rows:
                try:
                    y = int(r.y)
                    m = int(r.m)
                    d = int(r.d)
                    h = int(r.h)
                    hour_dt = datetime(y, m, d, h, 0, 0, tzinfo=UTC)
                except Exception as ex:
                    logger.warning("Failed to parse hour bucket for mentions: %s", ex)
                    continue
                counts_by_key[_HourlyKey(symbol=r.ticker.upper(), hour=hour_dt)] = int(
                    r.cnt or 0
                )
        else:
            # Postgres and others supporting date_trunc
            hour_expr = func.date_trunc("hour", Article.published_at)
            rows = (
                self.session.query(
                    ArticleTicker.ticker.label("ticker"),
                    hour_expr.label("hour"),
                    func.count(Article.id).label("cnt"),
                )
                .join(Article, Article.id == ArticleTicker.article_id)
                .filter(
                    ArticleTicker.ticker.in_(normalized),
                    Article.published_at >= window_start,
                )
                .group_by(ArticleTicker.ticker, hour_expr)
                .all()
            )

            for r in rows:
                hour_dt = r.hour
                if isinstance(hour_dt, datetime):
                    if hour_dt.tzinfo is None:
                        hour_dt = hour_dt.replace(tzinfo=UTC)
                    else:
                        hour_dt = hour_dt.astimezone(UTC)
                else:
                    # Fallback: try to parse via str()
                    try:
                        hour_dt = datetime.fromisoformat(str(hour_dt)).replace(tzinfo=UTC)
                    except Exception:
                        continue
                counts_by_key[_HourlyKey(symbol=r.ticker.upper(), hour=hour_dt)] = int(
                    r.cnt or 0
                )

        # Build continuous label range hour-by-hour
        labels: list[str] = []
        hours_list: list[datetime] = []
        cursor = datetime(
            window_start.year,
            window_start.month,
            window_start.day,
            window_start.hour,
            tzinfo=UTC,
        )
        end = datetime(now.year, now.month, now.day, now.hour, tzinfo=UTC)
        while cursor <= end:
            labels.append(cursor.isoformat())
            hours_list.append(cursor)
            cursor += timedelta(hours=1)

        # Zero-fill for each symbol
        series: list[MentionsSeriesDTO] = []
        for sym in normalized:
            data_points: list[int] = []
            for hdt in hours_list:
                data_points.append(counts_by_key.get(_HourlyKey(sym, hdt), 0))
            series.append(MentionsSeriesDTO(symbol=sym, data=data_points))

        return MentionsHourlyResponseDTO(labels=labels, series=series, hours=hours)


def get_mention_stats_service(session: Session) -> MentionStatsService:
    """Factory to obtain MentionStatsService instance."""
    return MentionStatsService(session)


