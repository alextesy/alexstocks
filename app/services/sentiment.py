"""Sentiment analysis service using VADER sentiment analysis."""

import logging
import os

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)


class SentimentService:
    """Service for analyzing sentiment of text using VADER."""

    def __init__(self) -> None:
        """Initialize the sentiment analyzer."""
        self._analyzer = SentimentIntensityAnalyzer()
        logger.info("SentimentService initialized with VADER analyzer")

    def analyze_sentiment(self, text: str) -> float:
        """
        Analyze sentiment of text and return compound score.

        Args:
            text: The text to analyze for sentiment

        Returns:
            Float between -1.0 (most negative) and 1.0 (most positive)

        Raises:
            ValueError: If text is empty or None
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty or None")

        # Clean and prepare text
        cleaned_text = text.strip()

        # Get sentiment scores
        scores = self._analyzer.polarity_scores(cleaned_text)
        compound_score = scores["compound"]

        logger.debug(
            "Sentiment analysis completed",
            extra={
                "text_length": len(cleaned_text),
                "compound_score": compound_score,
                "positive": scores["pos"],
                "neutral": scores["neu"],
                "negative": scores["neg"],
            },
        )

        return compound_score

    def get_sentiment_label(self, score: float) -> str:
        """
        Convert sentiment score to human-readable label.

        Args:
            score: Sentiment score between -1.0 and 1.0

        Returns:
            String label: 'Positive', 'Neutral', or 'Negative'
        """
        if score >= 0.05:
            return "Positive"
        elif score <= -0.05:
            return "Negative"
        else:
            return "Neutral"

    def analyze_with_label(self, text: str) -> tuple[float, str]:
        """
        Analyze sentiment and return both score and label.

        Args:
            text: The text to analyze for sentiment

        Returns:
            Tuple of (score, label) where score is float and label is string
        """
        score = self.analyze_sentiment(text)
        label = self.get_sentiment_label(score)
        return score, label


# Global instance for easy access
_sentiment_service: SentimentService | None = None


def get_sentiment_service() -> SentimentService:
    """
    Get the global sentiment service instance.

    Returns:
        SentimentService instance
    """
    global _sentiment_service
    if _sentiment_service is None:
        _sentiment_service = SentimentService()
    return _sentiment_service


def get_sentiment_service_hybrid():
    """
    Get the hybrid sentiment service that can use LLM or VADER.
    
    Returns:
        Hybrid sentiment service instance
    """
    # Import here to avoid circular imports
    from app.services.hybrid_sentiment import get_hybrid_sentiment_service
    return get_hybrid_sentiment_service()


def analyze_sentiment(text: str) -> float:
    """
    Convenience function to analyze sentiment of text.

    Args:
        text: The text to analyze for sentiment

    Returns:
        Float between -1.0 (most negative) and 1.0 (most positive)
    """
    service = get_sentiment_service()
    return service.analyze_sentiment(text)
