"""Repository for managing daily ticker summaries."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import DailyTickerSummary
from app.models.dto import DailyTickerSummaryDTO, DailyTickerSummaryUpsertDTO


class DailyTickerSummaryRepository:
    """Data-access helpers for :class:`DailyTickerSummary`."""

    def __init__(self, session: Session):
        """Initialize the repository with a database session."""
        self.session = session

    def upsert_summary(
        self, summary: DailyTickerSummaryUpsertDTO
    ) -> DailyTickerSummaryDTO:
        """Create or update a summary for the given ticker and date."""

        stmt = select(DailyTickerSummary).where(
            DailyTickerSummary.ticker == summary.ticker,
            DailyTickerSummary.summary_date == summary.summary_date,
        )
        existing = self.session.execute(stmt).scalar_one_or_none()
        now = datetime.now(UTC)

        if existing:
            existing.mention_count = summary.mention_count
            existing.engagement_count = summary.engagement_count
            existing.avg_sentiment = summary.avg_sentiment
            existing.sentiment_stddev = summary.sentiment_stddev
            existing.sentiment_min = summary.sentiment_min
            existing.sentiment_max = summary.sentiment_max
            existing.top_articles = summary.top_articles
            existing.llm_summary = summary.llm_summary
            existing.llm_summary_bullets = summary.llm_summary_bullets
            existing.llm_sentiment = summary.llm_sentiment
            existing.llm_model = summary.llm_model
            existing.llm_version = summary.llm_version
            existing.updated_at = now
            self.session.flush()
            return self._to_dto(existing)

        entity = DailyTickerSummary(
            ticker=summary.ticker,
            summary_date=summary.summary_date,
            mention_count=summary.mention_count,
            engagement_count=summary.engagement_count,
            avg_sentiment=summary.avg_sentiment,
            sentiment_stddev=summary.sentiment_stddev,
            sentiment_min=summary.sentiment_min,
            sentiment_max=summary.sentiment_max,
            top_articles=summary.top_articles,
            llm_summary=summary.llm_summary,
            llm_summary_bullets=summary.llm_summary_bullets,
            llm_sentiment=summary.llm_sentiment,
            llm_model=summary.llm_model,
            llm_version=summary.llm_version,
            created_at=now,
            updated_at=now,
        )
        self.session.add(entity)
        self.session.flush()
        return self._to_dto(entity)

    def get_summaries_for_ticker(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
    ) -> list[DailyTickerSummaryDTO]:
        """Fetch summaries for a ticker ordered by most recent first."""

        stmt = select(DailyTickerSummary).where(DailyTickerSummary.ticker == ticker)
        stmt = self._apply_date_filters(stmt, start_date, end_date)
        stmt = stmt.order_by(DailyTickerSummary.summary_date.desc())
        if limit is not None:
            stmt = stmt.limit(limit)

        rows = self.session.execute(stmt).scalars().all()
        return [self._to_dto(row) for row in rows]

    def get_summaries(
        self,
        tickers: Sequence[str],
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
    ) -> list[DailyTickerSummaryDTO]:
        """Fetch summaries across multiple tickers ordered by ticker/date."""

        if not tickers:
            return []

        stmt = select(DailyTickerSummary).where(
            DailyTickerSummary.ticker.in_(list(tickers))
        )

        stmt = self._apply_date_filters(stmt, start_date, end_date)
        stmt = stmt.order_by(
            DailyTickerSummary.ticker.asc(),
            DailyTickerSummary.summary_date.desc(),
        )
        if limit is not None:
            stmt = stmt.limit(limit)

        rows = self.session.execute(stmt).scalars().all()
        return [self._to_dto(row) for row in rows]

    def get_most_recent_summary_date(self) -> date | None:
        """Return the most recent summary_date that has llm content."""

        stmt = select(func.max(DailyTickerSummary.summary_date)).where(
            DailyTickerSummary.llm_summary.isnot(None)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def cleanup_before(
        self, before_date: date, tickers: Iterable[str] | None = None
    ) -> int:
        """Delete summaries older than ``before_date``.

        Args:
            before_date: Delete summaries strictly before this date.
            tickers: Optional iterable of ticker symbols to scope the cleanup.

        Returns:
            Number of rows removed.
        """

        stmt = delete(DailyTickerSummary).where(
            DailyTickerSummary.summary_date < before_date
        )
        if tickers:
            stmt = stmt.where(DailyTickerSummary.ticker.in_(list(tickers)))

        result = self.session.execute(stmt)
        self.session.flush()
        return int(result.rowcount or 0)

    def get_summaries_for_week(
        self,
        tickers: Sequence[str],
        week_start: date,
        week_end: date,
    ) -> dict[str, list[DailyTickerSummaryDTO]]:
        """Get summaries for multiple tickers within a week window.

        Args:
            tickers: List of ticker symbols to include.
            week_start: Start date of the week (inclusive).
            week_end: End date of the week (inclusive).

        Returns:
            Dictionary mapping ticker symbols to their list of daily summaries,
            ordered by date ascending within each ticker.
        """
        if not tickers:
            return {}

        stmt = (
            select(DailyTickerSummary)
            .where(
                DailyTickerSummary.ticker.in_(list(tickers)),
                DailyTickerSummary.summary_date >= week_start,
                DailyTickerSummary.summary_date <= week_end,
            )
            .order_by(
                DailyTickerSummary.ticker.asc(),
                DailyTickerSummary.summary_date.asc(),
            )
        )

        rows = self.session.execute(stmt).scalars().all()

        # Group by ticker
        result: dict[str, list[DailyTickerSummaryDTO]] = {}
        for row in rows:
            ticker = row.ticker
            if ticker not in result:
                result[ticker] = []
            result[ticker].append(self._to_dto(row))

        return result

    def get_week_aggregate_stats(
        self,
        tickers: Sequence[str],
        week_start: date,
        week_end: date,
    ) -> list[dict]:
        """Get aggregated statistics for tickers over a week.

        Returns a list of dicts with aggregated metrics per ticker,
        ordered by total mentions descending.
        """
        if not tickers:
            return []

        stmt = (
            select(
                DailyTickerSummary.ticker,
                func.sum(DailyTickerSummary.mention_count).label("total_mentions"),
                func.sum(DailyTickerSummary.engagement_count).label("total_engagement"),
                func.avg(DailyTickerSummary.avg_sentiment).label("avg_sentiment"),
                func.count(DailyTickerSummary.id).label("days_with_data"),
                func.min(DailyTickerSummary.summary_date).label("first_date"),
                func.max(DailyTickerSummary.summary_date).label("last_date"),
            )
            .where(
                DailyTickerSummary.ticker.in_(list(tickers)),
                DailyTickerSummary.summary_date >= week_start,
                DailyTickerSummary.summary_date <= week_end,
            )
            .group_by(DailyTickerSummary.ticker)
            .order_by(func.sum(DailyTickerSummary.mention_count).desc())
        )

        rows = self.session.execute(stmt).all()
        return [
            {
                "ticker": row.ticker,
                "total_mentions": row.total_mentions or 0,
                "total_engagement": row.total_engagement or 0,
                "avg_sentiment": (
                    float(row.avg_sentiment) if row.avg_sentiment else None
                ),
                "days_with_data": row.days_with_data or 0,
                "first_date": row.first_date,
                "last_date": row.last_date,
            }
            for row in rows
        ]

    @staticmethod
    def _apply_date_filters(query, start_date: date | None, end_date: date | None):
        if start_date is not None:
            query = query.where(DailyTickerSummary.summary_date >= start_date)
        if end_date is not None:
            query = query.where(DailyTickerSummary.summary_date <= end_date)
        return query

    @staticmethod
    def _to_dto(entity: DailyTickerSummary) -> DailyTickerSummaryDTO:
        return DailyTickerSummaryDTO(
            id=entity.id,
            ticker=entity.ticker,
            summary_date=entity.summary_date,
            mention_count=entity.mention_count,
            engagement_count=entity.engagement_count,
            avg_sentiment=entity.avg_sentiment,
            sentiment_stddev=entity.sentiment_stddev,
            sentiment_min=entity.sentiment_min,
            sentiment_max=entity.sentiment_max,
            top_articles=entity.top_articles,
            llm_summary=entity.llm_summary,
            llm_summary_bullets=entity.llm_summary_bullets,
            llm_sentiment=entity.llm_sentiment,
            llm_model=entity.llm_model,
            llm_version=entity.llm_version,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
