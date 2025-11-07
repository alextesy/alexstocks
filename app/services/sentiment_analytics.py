"""Sentiment analytics service for generating histograms and aggregations."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker
# Removed get_sentiment_service_hybrid - only used in non-optimized method
# Optimized methods use SQL aggregation directly

logger = logging.getLogger(__name__)


class SentimentAnalyticsService:
    """Service for sentiment analytics and histogram generation."""

    def get_sentiment_histogram(
        self, db: Session, ticker: str | None = None
    ) -> dict[str, int]:
        """
        Get sentiment histogram counts for all articles or a specific ticker.

        Args:
            db: Database session
            ticker: Optional ticker symbol to filter by

        Returns:
            Dictionary with sentiment counts: {"positive": x, "neutral": y, "negative": z}
        """
        try:
            # Base query for articles with sentiment
            base_query = db.query(Article).filter(Article.sentiment.isnot(None))

            # Filter by ticker if specified
            if ticker:
                base_query = base_query.join(
                    ArticleTicker, Article.id == ArticleTicker.article_id
                ).filter(ArticleTicker.ticker == ticker.upper())

            # Get all articles with sentiment
            articles = base_query.all()

            # Count sentiment categories
            positive_count = 0
            neutral_count = 0
            negative_count = 0

            # Simple threshold-based classification (no ML service needed)
            positive_threshold = 0.1
            negative_threshold = -0.1
            for article in articles:
                if article.sentiment is not None:
                    if article.sentiment >= positive_threshold:
                        positive_count += 1
                    elif article.sentiment <= negative_threshold:
                        negative_count += 1
                    else:
                        neutral_count += 1

            histogram = {
                "positive": positive_count,
                "neutral": neutral_count,
                "negative": negative_count,
                "total": positive_count + neutral_count + negative_count,
            }

            logger.debug(
                f"Generated sentiment histogram for ticker {ticker}: {histogram}"
            )
            return histogram

        except Exception as e:
            logger.error(f"Error generating sentiment histogram: {e}")
            return {"positive": 0, "neutral": 0, "negative": 0, "total": 0}

    def get_sentiment_histogram_optimized(
        self, db: Session, ticker: str | None = None, days: int | None = None
    ) -> dict[str, int]:
        """
        Get sentiment histogram using SQL aggregation for better performance.

        Args:
            db: Database session
            ticker: Optional ticker symbol to filter by
            days: Optional number of days to look back (None = all time)

        Returns:
            Dictionary with sentiment counts: {"positive": x, "neutral": y, "negative": z}
        """
        try:
            # Define sentiment thresholds (matching the service logic)
            positive_threshold = 0.05
            negative_threshold = -0.05

            # Base query
            base_query = db.query(Article).filter(Article.sentiment.isnot(None))

            # Filter by date if specified
            if days is not None:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                base_query = base_query.filter(Article.published_at >= cutoff_date)

            # Filter by ticker if specified
            if ticker:
                base_query = base_query.join(
                    ArticleTicker, Article.id == ArticleTicker.article_id
                ).filter(ArticleTicker.ticker == ticker.upper())

            # Count using SQL aggregation
            positive_count = base_query.filter(
                Article.sentiment >= positive_threshold
            ).count()
            negative_count = base_query.filter(
                Article.sentiment <= negative_threshold
            ).count()
            neutral_count = base_query.filter(
                Article.sentiment > negative_threshold,
                Article.sentiment < positive_threshold,
            ).count()

            histogram = {
                "positive": positive_count,
                "neutral": neutral_count,
                "negative": negative_count,
                "total": positive_count + neutral_count + negative_count,
            }

            logger.debug(
                f"Generated optimized sentiment histogram for ticker {ticker}: {histogram}"
            )
            return histogram

        except Exception as e:
            logger.error(f"Error generating optimized sentiment histogram: {e}")
            return {"positive": 0, "neutral": 0, "negative": 0, "total": 0}

    def get_sentiment_distribution_data(
        self, db: Session, ticker: str | None = None, days: int | None = None
    ) -> dict:
        """
        Get sentiment distribution data for visualization including percentages.

        Args:
            db: Database session
            ticker: Optional ticker symbol to filter by
            days: Optional number of days to look back (None = all time)

        Returns:
            Dictionary with counts, percentages, and display data
        """
        histogram = self.get_sentiment_histogram_optimized(db, ticker, days)
        total = histogram["total"]

        if total == 0:
            return {
                "counts": histogram,
                "percentages": {"positive": 0, "neutral": 0, "negative": 0},
                "display_data": [],
                "total": total,
            }

        # Calculate percentages
        percentages = {
            "positive": round((histogram["positive"] / total) * 100, 1),
            "neutral": round((histogram["neutral"] / total) * 100, 1),
            "negative": round((histogram["negative"] / total) * 100, 1),
        }

        # Create display data for charts/UI
        display_data = [
            {
                "label": "Positive",
                "count": histogram["positive"],
                "percentage": percentages["positive"],
                "color": "#10b981",  # green-500
                "icon": "📈",
            },
            {
                "label": "Neutral",
                "count": histogram["neutral"],
                "percentage": percentages["neutral"],
                "color": "#6b7280",  # gray-500
                "icon": "➡️",
            },
            {
                "label": "Negative",
                "count": histogram["negative"],
                "percentage": percentages["negative"],
                "color": "#ef4444",  # red-500
                "icon": "📉",
            },
        ]

        return {
            "counts": histogram,
            "percentages": percentages,
            "display_data": display_data,
            "total": total,
        }

    # --- New leaning computations ---
    def get_sentiment_lean_data(
        self, db: Session, ticker: str | None = None, days: int = 1
    ) -> dict:
        """Compute leaning metrics for overall or a specific ticker over given days.

        Returns a dictionary containing counts, shares excluding neutral, leaning
        score and a presentation-friendly label with confidence.
        """
        positive_threshold = 0.05
        negative_threshold = -0.05

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        base = db.query(Article)
        base = base.filter(Article.sentiment.isnot(None))
        base = base.filter(Article.published_at >= cutoff_date)

        if ticker:
            base = base.join(
                ArticleTicker, Article.id == ArticleTicker.article_id
            ).filter(ArticleTicker.ticker == ticker.upper())

        positive_count = base.filter(Article.sentiment >= positive_threshold).count()
        negative_count = base.filter(Article.sentiment <= negative_threshold).count()
        neutral_count = base.filter(
            Article.sentiment > negative_threshold,
            Article.sentiment < positive_threshold,
        ).count()

        total = positive_count + negative_count + neutral_count
        pos_neg = positive_count + negative_count

        if total == 0:
            return {
                "counts": {
                    "positive": 0,
                    "negative": 0,
                    "neutral": 0,
                    "total": 0,
                },
                "pos_share_ex_neutral": 0.0,
                "neg_share_ex_neutral": 0.0,
                "leaning_score": 0.0,
                "leaning_label": "Neutral",
                "confidence": 0.0,
                "neutral_dominant": False,
            }

        neutral_share = neutral_count / total if total else 0.0
        confidence = (pos_neg / total) if total else 0.0

        if pos_neg == 0:
            # All neutral
            return {
                "counts": {
                    "positive": positive_count,
                    "negative": negative_count,
                    "neutral": neutral_count,
                    "total": total,
                },
                "pos_share_ex_neutral": 0.0,
                "neg_share_ex_neutral": 0.0,
                "leaning_score": 0.0,
                "leaning_label": "Neutral",
                "confidence": confidence,
                "neutral_dominant": True,
            }

        pos_share_ex_neutral = positive_count / pos_neg
        neg_share_ex_neutral = negative_count / pos_neg
        leaning_score = (positive_count - negative_count) / pos_neg

        # Read threshold from env to avoid importing app.config (which validates DB URL)
        try:
            from os import getenv

            threshold_str = getenv("SENTIMENT_NEUTRAL_DOMINANCE_THRESHOLD", "0.80")
            neutral_dominance_threshold = float(threshold_str)
        except Exception:
            neutral_dominance_threshold = 0.80

        if neutral_share >= neutral_dominance_threshold:
            leaning_label = "Neutral"
            neutral_dominant = True
        else:
            leaning_label = (
                "Leaning Positive"
                if leaning_score > 0
                else "Leaning Negative" if leaning_score < 0 else "Neutral"
            )
            neutral_dominant = False

        return {
            "counts": {
                "positive": positive_count,
                "negative": negative_count,
                "neutral": neutral_count,
                "total": total,
            },
            "pos_share_ex_neutral": round(pos_share_ex_neutral, 4),
            "neg_share_ex_neutral": round(neg_share_ex_neutral, 4),
            "leaning_score": round(leaning_score, 4),
            "leaning_label": leaning_label,
            "confidence": round(confidence, 4),
            "neutral_dominant": neutral_dominant,
        }

    def get_ticker_lean_map(
        self, db: Session, tickers: list[str], days: int = 1
    ) -> dict[str, dict]:
        """Compute lean data for many tickers with one grouped query."""
        if not tickers:
            return {}

        positive_threshold = 0.05
        negative_threshold = -0.05

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        rows = (
            db.query(
                ArticleTicker.ticker.label("ticker"),
                func.sum(
                    case((Article.sentiment >= positive_threshold, 1), else_=0)
                ).label("positive"),
                func.sum(
                    case((Article.sentiment <= negative_threshold, 1), else_=0)
                ).label("negative"),
                func.sum(
                    case(
                        (
                            (Article.sentiment > negative_threshold)
                            & (Article.sentiment < positive_threshold),
                            1,
                        ),
                        else_=0,
                    )
                ).label("neutral"),
            )
            .join(Article, Article.id == ArticleTicker.article_id)
            .filter(ArticleTicker.ticker.in_([t.upper() for t in tickers]))
            .filter(Article.published_at >= cutoff_date)
            .filter(Article.sentiment.isnot(None))
            .group_by(ArticleTicker.ticker)
            .all()
        )

        result: dict[str, dict] = {}
        for r in rows:
            positive = int(r.positive or 0)
            negative = int(r.negative or 0)
            neutral = int(r.neutral or 0)
            total = positive + negative + neutral
            pos_neg = positive + negative
            neutral_share = (neutral / total) if total else 0.0
            confidence = (pos_neg / total) if total else 0.0

            if total == 0 or pos_neg == 0:
                result[r.ticker] = {
                    "counts": {
                        "positive": positive,
                        "negative": negative,
                        "neutral": neutral,
                        "total": total,
                    },
                    "pos_share_ex_neutral": 0.0,
                    "neg_share_ex_neutral": 0.0,
                    "leaning_score": 0.0,
                    "leaning_label": "Neutral",
                    "confidence": round(confidence, 4),
                    "neutral_dominant": True,
                }
                continue

            pos_share_ex_neutral = positive / pos_neg
            neg_share_ex_neutral = negative / pos_neg
            leaning_score = (positive - negative) / pos_neg

            # Threshold from env (default 0.80)
            try:
                from os import getenv

                threshold_str = getenv("SENTIMENT_NEUTRAL_DOMINANCE_THRESHOLD", "0.80")
                neutral_dominance_threshold = float(threshold_str)
            except Exception:
                neutral_dominance_threshold = 0.80

            if neutral_share >= neutral_dominance_threshold:
                leaning_label = "Neutral"
                neutral_dominant = True
            else:
                leaning_label = (
                    "Leaning Positive"
                    if leaning_score > 0
                    else "Leaning Negative" if leaning_score < 0 else "Neutral"
                )
                neutral_dominant = False

            result[r.ticker] = {
                "counts": {
                    "positive": positive,
                    "negative": negative,
                    "neutral": neutral,
                    "total": total,
                },
                "pos_share_ex_neutral": round(pos_share_ex_neutral, 4),
                "neg_share_ex_neutral": round(neg_share_ex_neutral, 4),
                "leaning_score": round(leaning_score, 4),
                "leaning_label": leaning_label,
                "confidence": round(confidence, 4),
                "neutral_dominant": neutral_dominant,
            }

        # Ensure all requested tickers are present with a neutral default when no rows
        for sym in [t.upper() for t in tickers]:
            if sym not in result:
                result[sym] = {
                    "counts": {"positive": 0, "negative": 0, "neutral": 0, "total": 0},
                    "pos_share_ex_neutral": 0.0,
                    "neg_share_ex_neutral": 0.0,
                    "leaning_score": 0.0,
                    "leaning_label": "Neutral",
                    "confidence": 0.0,
                    "neutral_dominant": True,
                }

        return result


# Global service instance
_sentiment_analytics_service = None


def get_sentiment_analytics_service() -> SentimentAnalyticsService:
    """Get sentiment analytics service instance."""
    global _sentiment_analytics_service
    if _sentiment_analytics_service is None:
        _sentiment_analytics_service = SentimentAnalyticsService()
    return _sentiment_analytics_service
