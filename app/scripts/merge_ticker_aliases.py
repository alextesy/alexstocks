"""Utilities to merge ticker alias share classes into a canonical symbol."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import (
    ArticleTicker,
    DailyTickerSummary,
    StockPrice,
    StockPriceHistory,
    Ticker,
    UserTickerFollow,
)
from app.db.session import SessionLocal
from app.utils.ticker_aliases import canonicalize_symbol, get_alias_groups

logger = logging.getLogger(__name__)


@dataclass
class MergeStats:
    """Simple counter container for merge operations."""

    article_links_updated: int = 0
    article_links_removed: int = 0
    daily_summaries_touched: int = 0
    stock_price_rows_touched: int = 0
    stock_price_history_rows_touched: int = 0
    user_follows_updated: int = 0
    user_follows_removed: int = 0
    ticker_rows_deleted: int = 0

    def as_dict(self) -> dict[str, int]:
        return self.__dict__.copy()

    def touched(self) -> bool:
        return any(value > 0 for value in self.__dict__.values())


class TickerMergeService:
    """Merge alias symbols into their canonical ticker across all tables."""

    def __init__(self, session: Session):
        self.session = session

    def merge_all(self) -> dict[str, dict[str, int]]:
        """Merge every alias group defined in ticker_aliases."""

        results: dict[str, dict[str, int]] = {}
        for canonical, equivalents in get_alias_groups().items():
            canonical_symbol = canonical.upper()
            for alias in equivalents:
                alias_symbol = alias.upper()
                if alias_symbol == canonical_symbol:
                    continue
                stats = self.merge_pair(canonical_symbol, alias_symbol)
                if stats.touched():
                    key = f"{alias_symbol}->{canonical_symbol}"
                    results[key] = stats.as_dict()
        if results:
            self.session.commit()
        else:
            self.session.rollback()
        return results

    def merge_pair(self, canonical: str, alias: str) -> MergeStats:
        """Merge a specific alias into the canonical symbol."""

        stats = MergeStats()
        canonical_symbol = canonical.upper()
        alias_symbol = canonicalize_symbol(alias.upper())

        if alias_symbol != canonical_symbol:
            logger.debug(
                "Skipping merge for %s because it canonicalizes to %s",
                alias,
                alias_symbol,
            )
            return stats

        stats.article_links_updated, stats.article_links_removed = (
            self._merge_article_tickers(canonical_symbol, alias.upper())
        )
        stats.daily_summaries_touched = self._merge_daily_summaries(
            canonical_symbol, alias.upper()
        )
        stats.stock_price_rows_touched = self._merge_stock_price(
            canonical_symbol, alias.upper()
        )
        stats.stock_price_history_rows_touched = self._merge_stock_price_history(
            canonical_symbol, alias.upper()
        )
        stats.user_follows_updated, stats.user_follows_removed = (
            self._merge_user_follows(canonical_symbol, alias.upper())
        )

        if self._merge_ticker_rows(canonical_symbol, alias.upper()):
            stats.ticker_rows_deleted = 1

        return stats

    def _merge_article_tickers(self, canonical: str, alias: str) -> tuple[int, int]:
        alias_links = (
            self.session.query(ArticleTicker)
            .filter(ArticleTicker.ticker == alias)
            .all()
        )
        if not alias_links:
            return 0, 0

        canonical_article_ids = {
            row.article_id
            for row in self.session.query(ArticleTicker.article_id).filter(
                ArticleTicker.ticker == canonical
            )
        }

        updated = 0
        removed = 0
        for link in alias_links:
            if link.article_id in canonical_article_ids:
                self.session.delete(link)
                removed += 1
            else:
                link.ticker = canonical
                canonical_article_ids.add(link.article_id)
                updated += 1
        return updated, removed

    def _merge_user_follows(self, canonical: str, alias: str) -> tuple[int, int]:
        alias_follows = (
            self.session.query(UserTickerFollow)
            .filter(UserTickerFollow.ticker == alias)
            .all()
        )
        if not alias_follows:
            return 0, 0

        canonical_user_ids = {
            row.user_id
            for row in self.session.query(UserTickerFollow.user_id).filter(
                UserTickerFollow.ticker == canonical
            )
        }

        updated = 0
        removed = 0
        for follow in alias_follows:
            if follow.user_id in canonical_user_ids:
                self.session.delete(follow)
                removed += 1
            else:
                follow.ticker = canonical
                canonical_user_ids.add(follow.user_id)
                updated += 1
        return updated, removed

    def _merge_stock_price(self, canonical: str, alias: str) -> int:
        alias_price = self.session.get(StockPrice, alias)
        if not alias_price:
            return 0

        canonical_price = self.session.get(StockPrice, canonical)
        if not canonical_price:
            alias_price.symbol = canonical
            return 1

        numeric_fields = [
            "price",
            "previous_close",
            "change",
            "change_percent",
            "open",
            "day_high",
            "day_low",
            "volume",
            "bid",
            "ask",
            "bid_size",
            "ask_size",
            "market_cap",
            "shares_outstanding",
            "average_volume",
            "average_volume_10d",
        ]
        text_fields = ["market_state", "currency", "exchange"]

        for field in numeric_fields + text_fields:
            if (
                getattr(canonical_price, field) is None
                and getattr(alias_price, field) is not None
            ):
                setattr(canonical_price, field, getattr(alias_price, field))

        canonical_price.updated_at = max(
            canonical_price.updated_at,
            alias_price.updated_at,
        )
        self.session.delete(alias_price)
        return 1

    def _merge_stock_price_history(self, canonical: str, alias: str) -> int:
        alias_rows = (
            self.session.query(StockPriceHistory)
            .filter(StockPriceHistory.symbol == alias)
            .all()
        )
        if not alias_rows:
            return 0

        canonical_dates = {
            row.date
            for row in self.session.query(StockPriceHistory.date).filter(
                StockPriceHistory.symbol == canonical
            )
        }

        touched = 0
        for row in alias_rows:
            if row.date in canonical_dates:
                self.session.delete(row)
            else:
                row.symbol = canonical
                canonical_dates.add(row.date)
            touched += 1
        return touched

    def _merge_daily_summaries(self, canonical: str, alias: str) -> int:
        alias_rows = (
            self.session.query(DailyTickerSummary)
            .filter(DailyTickerSummary.ticker == alias)
            .all()
        )
        if not alias_rows:
            return 0

        canonical_by_date = {
            row.summary_date: row
            for row in self.session.query(DailyTickerSummary).filter(
                DailyTickerSummary.ticker == canonical
            )
        }

        touched = 0
        for alias_row in alias_rows:
            target = canonical_by_date.get(alias_row.summary_date)
            if target:
                self._combine_summary_rows(target, alias_row)
                self.session.delete(alias_row)
            else:
                alias_row.ticker = canonical
                canonical_by_date[alias_row.summary_date] = alias_row
            touched += 1
        return touched

    def _merge_ticker_rows(self, canonical: str, alias: str) -> bool:
        alias_row = self.session.get(Ticker, alias)
        if not alias_row:
            return False

        canonical_row = self.session.get(Ticker, canonical)
        if not canonical_row:
            alias_row.symbol = canonical
            return False

        canonical_row.name = canonical_row.name or alias_row.name
        canonical_row.exchange = canonical_row.exchange or alias_row.exchange
        canonical_row.cik = canonical_row.cik or alias_row.cik
        canonical_row.sources = self._merge_lists(
            canonical_row.sources,
            alias_row.sources,
        )
        canonical_row.aliases = self._merge_lists(
            canonical_row.aliases,
            alias_row.aliases,
            [alias],
        )
        canonical_row.is_sp500 = canonical_row.is_sp500 or alias_row.is_sp500
        self.session.delete(alias_row)
        return True

    def _combine_summary_rows(
        self,
        target: DailyTickerSummary,
        source: DailyTickerSummary,
    ) -> None:
        old_target_mentions = target.mention_count or 0
        source_mentions = source.mention_count or 0
        old_target_engagement = target.engagement_count or 0
        source_engagement = source.engagement_count or 0

        target.mention_count = old_target_mentions + source_mentions
        target.engagement_count = old_target_engagement + source_engagement
        target.avg_sentiment = self._weighted_average(
            target.avg_sentiment,
            old_target_mentions,
            source.avg_sentiment,
            source_mentions,
        )
        target.sentiment_min = self._merge_min(
            target.sentiment_min, source.sentiment_min
        )
        target.sentiment_max = self._merge_max(
            target.sentiment_max, source.sentiment_max
        )
        target.sentiment_stddev = self._combine_stddev(
            target.avg_sentiment,
            source.avg_sentiment,
            target.sentiment_stddev,
            source.sentiment_stddev,
            old_target_mentions,
            source_mentions,
        )
        target.top_articles = self._merge_lists(
            target.top_articles, source.top_articles
        )
        if not target.llm_summary:
            target.llm_summary = source.llm_summary
        if not target.llm_summary_bullets:
            target.llm_summary_bullets = source.llm_summary_bullets
        if not target.llm_sentiment:
            target.llm_sentiment = source.llm_sentiment
        if not target.llm_model:
            target.llm_model = source.llm_model
        if not target.llm_version:
            target.llm_version = source.llm_version

    @staticmethod
    def _merge_lists(*lists: list | None) -> list:
        merged: list = []
        seen = set()
        for values in lists:
            if not values:
                continue
            for value in values:
                if value in seen:
                    continue
                seen.add(value)
                merged.append(value)
        return merged

    @staticmethod
    def _merge_min(existing: float | None, incoming: float | None) -> float | None:
        if existing is None:
            return incoming
        if incoming is None:
            return existing
        return min(existing, incoming)

    @staticmethod
    def _merge_max(existing: float | None, incoming: float | None) -> float | None:
        if existing is None:
            return incoming
        if incoming is None:
            return existing
        return max(existing, incoming)

    @staticmethod
    def _weighted_average(
        value_a: float | None,
        count_a: int,
        value_b: float | None,
        count_b: int,
    ) -> float | None:
        total = count_a + count_b
        if total == 0:
            return value_a if value_a is not None else value_b
        sum_a = (value_a or 0.0) * count_a
        sum_b = (value_b or 0.0) * count_b
        return (sum_a + sum_b) / total

    @staticmethod
    def _combine_stddev(
        mean_a: float | None,
        mean_b: float | None,
        stddev_a: float | None,
        stddev_b: float | None,
        count_a: int,
        count_b: int,
    ) -> float | None:
        total = count_a + count_b
        if total <= 1:
            return stddev_a if stddev_a is not None else stddev_b

        var_a = (stddev_a or 0.0) ** 2
        var_b = (stddev_b or 0.0) ** 2

        numerator = (count_a - 1) * var_a + (count_b - 1) * var_b
        mean_diff = (mean_a or 0.0) - (mean_b or 0.0)
        numerator += (count_a * count_b / max(total, 1)) * (mean_diff**2)
        return math.sqrt(max(numerator / max(total - 1, 1), 0.0))


def main() -> None:
    """Entry point for CLI usage."""

    logging.basicConfig(level=logging.INFO)
    session = SessionLocal()
    try:
        service = TickerMergeService(session)
        results = service.merge_all()
        if not results:
            logger.info("No alias merges were necessary")
            return
        for key, stats in results.items():
            logger.info("Merged %s with stats %s", key, stats)
    finally:
        session.close()


if __name__ == "__main__":
    main()
