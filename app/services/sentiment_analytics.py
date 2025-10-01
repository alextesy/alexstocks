"""Sentiment analytics service for generating histograms and aggregations."""

import logging

from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker
from app.services.sentiment import get_sentiment_service_hybrid

logger = logging.getLogger(__name__)


class SentimentAnalyticsService:
    """Service for sentiment analytics and histogram generation."""

    def __init__(self):
        self.sentiment_service = get_sentiment_service_hybrid()

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

            for article in articles:
                if article.sentiment is not None:
                    sentiment_label = self.sentiment_service.get_sentiment_label(
                        article.sentiment
                    )
                    if sentiment_label == "Positive":
                        positive_count += 1
                    elif sentiment_label == "Negative":
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
        self, db: Session, ticker: str | None = None
    ) -> dict[str, int]:
        """
        Get sentiment histogram using SQL aggregation for better performance.

        Args:
            db: Database session
            ticker: Optional ticker symbol to filter by

        Returns:
            Dictionary with sentiment counts: {"positive": x, "neutral": y, "negative": z}
        """
        try:
            # Define sentiment thresholds (matching the service logic)
            positive_threshold = 0.05
            negative_threshold = -0.05

            # Base query
            base_query = db.query(Article).filter(Article.sentiment.isnot(None))

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
        self, db: Session, ticker: str | None = None
    ) -> dict:
        """
        Get sentiment distribution data for visualization including percentages.

        Args:
            db: Database session
            ticker: Optional ticker symbol to filter by

        Returns:
            Dictionary with counts, percentages, and display data
        """
        histogram = self.get_sentiment_histogram_optimized(db, ticker)
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


# Global service instance
_sentiment_analytics_service = None


def get_sentiment_analytics_service() -> SentimentAnalyticsService:
    """Get sentiment analytics service instance."""
    global _sentiment_analytics_service
    if _sentiment_analytics_service is None:
        _sentiment_analytics_service = SentimentAnalyticsService()
    return _sentiment_analytics_service
