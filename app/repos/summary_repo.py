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
