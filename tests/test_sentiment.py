"""Tests for sentiment analysis service."""

import pytest

from app.services.sentiment import (
    SentimentService,
    analyze_sentiment,
    get_sentiment_service,
)


class TestSentimentService:
    """Test cases for SentimentService class."""

    def test_init(self) -> None:
        """Test service initialization."""
        service = SentimentService()
        assert service is not None
        assert service._analyzer is not None

    def test_analyze_sentiment_positive(self) -> None:
        """Test sentiment analysis with positive text."""
        service = SentimentService()

        # Test various positive texts
        positive_texts = [
            "This is amazing!",
            "Great news for investors!",
            "The stock is performing excellently.",
            "Outstanding results this quarter!",
            "Fantastic earnings report!",
        ]

        for text in positive_texts:
            score = service.analyze_sentiment(text)
            assert isinstance(score, float)
            assert -1.0 <= score <= 1.0
            assert score > 0, f"Expected positive score for: {text}"

    def test_analyze_sentiment_negative(self) -> None:
        """Test sentiment analysis with negative text."""
        service = SentimentService()

        # Test various negative texts
        negative_texts = [
            "This is terrible!",
            "Bad news for investors.",
            "The stock is crashing badly!",
            "Disappointing results this quarter.",
            "Awful earnings report!",
        ]

        for text in negative_texts:
            score = service.analyze_sentiment(text)
            assert isinstance(score, float)
            assert -1.0 <= score <= 1.0
            assert score < 0, f"Expected negative score for: {text}"

    def test_analyze_sentiment_neutral(self) -> None:
        """Test sentiment analysis with neutral text."""
        service = SentimentService()

        # Test various neutral texts
        neutral_texts = [
            "The company reported earnings.",
            "Stock price is unchanged.",
            "Market conditions are stable.",
            "The report was published today.",
            "Data shows no significant change.",
        ]

        for text in neutral_texts:
            score = service.analyze_sentiment(text)
            assert isinstance(score, float)
            assert -1.0 <= score <= 1.0
            # Neutral scores should be close to 0
            assert abs(score) < 0.3, f"Expected neutral score for: {text}"

    def test_analyze_sentiment_empty_text(self) -> None:
        """Test sentiment analysis with empty text raises ValueError."""
        service = SentimentService()

        with pytest.raises(ValueError, match="Text cannot be empty or None"):
            service.analyze_sentiment("")

        with pytest.raises(ValueError, match="Text cannot be empty or None"):
            service.analyze_sentiment("   ")

        with pytest.raises(ValueError, match="Text cannot be empty or None"):
            service.analyze_sentiment(None)  # type: ignore

    def test_analyze_sentiment_whitespace_handling(self) -> None:
        """Test that whitespace is properly handled."""
        service = SentimentService()

        text_with_spaces = "  Great news!  "
        score = service.analyze_sentiment(text_with_spaces)
        assert isinstance(score, float)
        assert score > 0

    def test_get_sentiment_label_positive(self) -> None:
        """Test sentiment label for positive scores."""
        service = SentimentService()

        positive_scores = [0.1, 0.3, 0.5, 0.7, 1.0]
        for score in positive_scores:
            label = service.get_sentiment_label(score)
            assert label == "Positive"

    def test_get_sentiment_label_negative(self) -> None:
        """Test sentiment label for negative scores."""
        service = SentimentService()

        negative_scores = [-0.1, -0.3, -0.5, -0.7, -1.0]
        for score in negative_scores:
            label = service.get_sentiment_label(score)
            assert label == "Negative"

    def test_get_sentiment_label_neutral(self) -> None:
        """Test sentiment label for neutral scores."""
        service = SentimentService()

        neutral_scores = [-0.04, -0.02, 0.0, 0.02, 0.04]
        for score in neutral_scores:
            label = service.get_sentiment_label(score)
            assert label == "Neutral"

    def test_analyze_with_label(self) -> None:
        """Test combined sentiment analysis and labeling."""
        service = SentimentService()

        # Test positive
        score, label = service.analyze_with_label("This is amazing!")
        assert isinstance(score, float)
        assert isinstance(label, str)
        assert score > 0
        assert label == "Positive"

        # Test negative
        score, label = service.analyze_with_label("This is terrible!")
        assert isinstance(score, float)
        assert isinstance(label, str)
        assert score < 0
        assert label == "Negative"

        # Test neutral
        score, label = service.analyze_with_label("The report was published.")
        assert isinstance(score, float)
        assert isinstance(label, str)
        assert label == "Neutral"


class TestGlobalFunctions:
    """Test cases for global convenience functions."""

    def test_get_sentiment_service_singleton(self) -> None:
        """Test that get_sentiment_service returns singleton instance."""
        service1 = get_sentiment_service()
        service2 = get_sentiment_service()

        assert service1 is service2
        assert isinstance(service1, SentimentService)

    def test_analyze_sentiment_function(self) -> None:
        """Test the convenience analyze_sentiment function."""
        # Test positive
        score = analyze_sentiment("Great news!")
        assert isinstance(score, float)
        assert score > 0

        # Test negative
        score = analyze_sentiment("Bad news!")
        assert isinstance(score, float)
        assert score < 0

        # Test neutral
        score = analyze_sentiment("The data was published.")
        assert isinstance(score, float)
        assert abs(score) < 0.3


class TestSentimentEdgeCases:
    """Test edge cases and special scenarios."""

    def test_very_long_text(self) -> None:
        """Test sentiment analysis with very long text."""
        service = SentimentService()

        # Create a long text with mixed sentiment
        long_text = "This is great! " * 100 + "But this is terrible! " * 50
        score = service.analyze_sentiment(long_text)

        assert isinstance(score, float)
        assert -1.0 <= score <= 1.0

    def test_special_characters(self) -> None:
        """Test sentiment analysis with special characters."""
        service = SentimentService()

        texts_with_special_chars = [
            "Great news!!!",
            "Bad news...",
            "So-so results???",
            "Amazing! 🚀",
            "Terrible! 😞",
        ]

        for text in texts_with_special_chars:
            score = service.analyze_sentiment(text)
            assert isinstance(score, float)
            assert -1.0 <= score <= 1.0

    def test_financial_terminology(self) -> None:
        """Test sentiment analysis with financial terminology."""
        service = SentimentService()

        financial_texts = [
            "Stock price surged 10% today!",
            "Market crash caused major losses.",
            "Earnings beat expectations significantly.",
            "Revenue declined quarter over quarter.",
            "Dividend yield increased to 3.5%.",
        ]

        for text in financial_texts:
            score = service.analyze_sentiment(text)
            assert isinstance(score, float)
            assert -1.0 <= score <= 1.0

    def test_mixed_sentiment(self) -> None:
        """Test sentiment analysis with mixed positive and negative content."""
        service = SentimentService()

        mixed_texts = [
            "Great earnings but terrible guidance.",
            "Stock up 5% but market down overall.",
            "Good news for some, bad for others.",
        ]

        for text in mixed_texts:
            score = service.analyze_sentiment(text)
            assert isinstance(score, float)
            assert -1.0 <= score <= 1.0
            # Mixed sentiment should be closer to neutral
            assert abs(score) < 0.5
