"""LLM-based sentiment analysis service using Hugging Face transformers."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Import transformers with fallback handling
try:
    from transformers import pipeline

    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.warning("Transformers not available, LLM sentiment analysis will not work")


class LLMSentimentService:
    """Service for analyzing sentiment using LLM models."""

    def __init__(
        self, model_name: str = "ProsusAI/finbert", use_gpu: bool = False
    ) -> None:
        """Initialize the LLM sentiment analyzer.

        Args:
            model_name: Hugging Face model name for sentiment analysis
            use_gpu: Whether to use GPU acceleration if available
        """
        if not TRANSFORMERS_AVAILABLE:
            raise RuntimeError(
                "Transformers library not available. Please install with: pip install transformers torch"
            )

        self.model_name = model_name
        self.use_gpu = use_gpu
        self._analyzer: Any = None
        self._device = 0 if use_gpu else -1

        logger.info(f"LLMSentimentService initialized with model: {model_name}")

    def _load_model(self) -> None:
        """Load the model and tokenizer if not already loaded."""
        if self._analyzer is not None:
            return

        try:
            logger.info(f"Loading LLM model: {self.model_name}")

            # Try to use a financial sentiment model first, fallback to general sentiment
            try:
                # Use a financial sentiment model (FinBERT)
                self._analyzer = pipeline(
                    "sentiment-analysis",
                    model=self.model_name,
                    device=self._device,
                    return_all_scores=True,
                )
                logger.info(
                    f"Successfully loaded financial sentiment model: {self.model_name}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load {self.model_name}, falling back to general model: {e}"
                )
                # Fallback to a general sentiment model
                self._analyzer = pipeline(
                    "sentiment-analysis",
                    model="cardiffnlp/twitter-roberta-base-sentiment-latest",
                    device=self._device,
                    return_all_scores=True,
                )
                self.model_name = "cardiffnlp/twitter-roberta-base-sentiment-latest"
                logger.info("Successfully loaded fallback sentiment model")

        except Exception as e:
            logger.error(f"Failed to load any LLM model: {e}")
            raise RuntimeError(f"Could not load sentiment analysis model: {e}") from e

    def analyze_sentiment(self, text: str) -> float:
        """
        Analyze sentiment of text and return compound score.

        Args:
            text: The text to analyze for sentiment

        Returns:
            Float between -1.0 (most negative) and 1.0 (most positive)

        Raises:
            ValueError: If text is empty or None
            RuntimeError: If model fails to analyze text
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty or None")

        if not TRANSFORMERS_AVAILABLE:
            raise RuntimeError("Transformers library not available")

        # Load model if not already loaded
        self._load_model()

        # Clean and prepare text
        cleaned_text = text.strip()

        # Limit text length to avoid token limits (most models have 512 token limit)
        if len(cleaned_text) > 2000:  # Rough estimate for token limit
            cleaned_text = cleaned_text[:2000] + "..."
            logger.debug("Truncated text to 2000 characters for analysis")

        try:
            # Get sentiment analysis results
            results = self._analyzer(cleaned_text)

            # Extract sentiment scores
            sentiment_scores = {}
            for result in results[0]:
                label = result["label"].lower()
                score = result["score"]
                sentiment_scores[label] = score

            # Convert to compound score based on model output
            compound_score = self._convert_to_compound_score(sentiment_scores)

            logger.debug(
                "LLM sentiment analysis completed",
                extra={
                    "text_length": len(cleaned_text),
                    "compound_score": compound_score,
                    "raw_scores": sentiment_scores,
                },
            )

            return compound_score

        except Exception as e:
            logger.error(f"LLM sentiment analysis failed: {e}")
            raise RuntimeError(f"Sentiment analysis failed: {e}") from e

    def _convert_to_compound_score(self, sentiment_scores: dict[str, float]) -> float:
        """Convert model-specific sentiment scores to compound score.

        Args:
            sentiment_scores: Dictionary of label -> score from the model

        Returns:
            Compound score between -1.0 and 1.0
        """
        # Handle different model output formats
        if "positive" in sentiment_scores and "negative" in sentiment_scores:
            # Standard positive/negative format (FinBERT)
            positive = sentiment_scores.get("positive", 0.0)
            negative = sentiment_scores.get("negative", 0.0)
            sentiment_scores.get("neutral", 0.0)

            # Calculate compound score: positive - negative
            compound = positive - negative

        elif "label_2" in sentiment_scores and "label_0" in sentiment_scores:
            # RoBERTa format: label_0 (negative), label_1 (neutral), label_2 (positive)
            positive = sentiment_scores.get("label_2", 0.0)
            negative = sentiment_scores.get("label_0", 0.0)
            sentiment_scores.get("label_1", 0.0)

            # Calculate compound score: positive - negative
            compound = positive - negative

        elif "pos" in sentiment_scores and "neg" in sentiment_scores:
            # Alternative format
            positive = sentiment_scores.get("pos", 0.0)
            negative = sentiment_scores.get("neg", 0.0)
            compound = positive - negative

        else:
            # Fallback: use the highest scoring label
            if not sentiment_scores:
                return 0.0

            max_label = max(sentiment_scores, key=lambda x: sentiment_scores[x])
            max_score = sentiment_scores[max_label]

            # Map labels to sentiment direction
            if any(
                neg_word in max_label.lower()
                for neg_word in ["negative", "neg", "label_0"]
            ):
                compound = -max_score
            elif any(
                pos_word in max_label.lower()
                for pos_word in ["positive", "pos", "label_2"]
            ):
                compound = max_score
            else:
                compound = 0.0  # neutral

        # Ensure score is within bounds
        return max(-1.0, min(1.0, compound))

    def get_sentiment_label(self, score: float) -> str:
        """
        Convert sentiment score to human-readable label.

        Args:
            score: Sentiment score between -1.0 and 1.0

        Returns:
            String label: 'Positive', 'Neutral', or 'Negative'
        """
        if score >= 0.1:
            return "Positive"
        elif score <= -0.1:
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

    def get_model_info(self) -> dict[str, Any]:
        """Get information about the loaded model.

        Returns:
            Dictionary with model information
        """
        return {
            "model_name": self.model_name,
            "use_gpu": self.use_gpu,
            "device": self._device,
            "is_loaded": self._analyzer is not None,
            "transformers_available": TRANSFORMERS_AVAILABLE,
        }


# Global instance for easy access
_llm_sentiment_service: LLMSentimentService | None = None


def get_llm_sentiment_service(
    model_name: str = "ProsusAI/finbert", use_gpu: bool = False
) -> LLMSentimentService:
    """
    Get the global LLM sentiment service instance.

    Args:
        model_name: Hugging Face model name for sentiment analysis
        use_gpu: Whether to use GPU acceleration if available

    Returns:
        LLMSentimentService instance
    """
    global _llm_sentiment_service
    if _llm_sentiment_service is None:
        _llm_sentiment_service = LLMSentimentService(
            model_name=model_name, use_gpu=use_gpu
        )
    return _llm_sentiment_service


def analyze_sentiment_llm(text: str, model_name: str = "ProsusAI/finbert") -> float:
    """
    Convenience function to analyze sentiment using LLM.

    Args:
        text: The text to analyze for sentiment
        model_name: Hugging Face model name for sentiment analysis

    Returns:
        Float between -1.0 (most negative) and 1.0 (most positive)
    """
    service = get_llm_sentiment_service(model_name=model_name)
    return service.analyze_sentiment(text)
