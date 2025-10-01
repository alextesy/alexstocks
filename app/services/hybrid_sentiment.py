"""Hybrid sentiment analysis service that can use VADER or LLM models."""

import logging
import os
from typing import Any

from app.services.llm_sentiment import get_llm_sentiment_service
from app.services.sentiment import get_sentiment_service as get_vader_service

logger = logging.getLogger(__name__)


class HybridSentimentService:
    """Hybrid sentiment service that can switch between VADER and LLM models."""

    def __init__(
        self,
        use_llm: bool = True,
        llm_model_name: str = "ProsusAI/finbert",
        use_gpu: bool = False,
        fallback_to_vader: bool = True,
        dual_model_strategy: bool = True,
        strong_llm_threshold: float = 0.2,
    ) -> None:
        """Initialize the hybrid sentiment service.

        Args:
            use_llm: Whether to use LLM for sentiment analysis
            llm_model_name: Hugging Face model name for LLM sentiment
            use_gpu: Whether to use GPU acceleration for LLM
            fallback_to_vader: Whether to fallback to VADER if LLM fails
            dual_model_strategy: Whether to use both models and choose the one furthest from 0 when LLM is neutral
            strong_llm_threshold: If LLM score abs value > this threshold, use LLM regardless
        """
        self.use_llm = use_llm
        self.llm_model_name = llm_model_name
        self.use_gpu = use_gpu
        self.fallback_to_vader = fallback_to_vader
        self.dual_model_strategy = dual_model_strategy
        self.strong_llm_threshold = strong_llm_threshold

        self._vader_service = None
        self._llm_service = None

        # Load services based on strategy
        if self.dual_model_strategy:
            # For dual model strategy, we need both services
            try:
                self._llm_service = get_llm_sentiment_service(
                    model_name=llm_model_name, use_gpu=use_gpu
                )
                logger.info(f"HybridSentimentService initialized LLM: {llm_model_name}")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM service: {e}")
                if not fallback_to_vader:
                    raise

            # Always load VADER for dual model strategy
            try:
                self._vader_service = get_vader_service()
                logger.info(
                    "HybridSentimentService initialized VADER for dual model strategy"
                )
            except Exception as e:
                logger.warning(f"Failed to initialize VADER service: {e}")

        elif self.use_llm:
            # Original LLM-first logic
            try:
                self._llm_service = get_llm_sentiment_service(
                    model_name=llm_model_name, use_gpu=use_gpu
                )
                logger.info(
                    f"HybridSentimentService initialized with LLM: {llm_model_name}"
                )
            except Exception as e:
                logger.warning(f"Failed to initialize LLM service: {e}")
                if self.fallback_to_vader:
                    self._vader_service = get_vader_service()
                    self.use_llm = False
                    logger.info("Fell back to VADER sentiment analysis")
                else:
                    raise
        else:
            self._vader_service = get_vader_service()
            logger.info("HybridSentimentService initialized with VADER")

    def analyze_sentiment(self, text: str) -> float:
        """
        Analyze sentiment of text using the configured service.

        Args:
            text: The text to analyze for sentiment

        Returns:
            Float between -1.0 (most negative) and 1.0 (most positive)

        Raises:
            ValueError: If text is empty or None
            RuntimeError: If both services fail
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty or None")

        # Dual model strategy: use both models and choose intelligently
        if self.dual_model_strategy and self._llm_service and self._vader_service:
            try:
                # Get LLM score first
                llm_score = self._llm_service.analyze_sentiment(text)

                # If LLM score is strong (> threshold from 0), use it
                if abs(llm_score) > self.strong_llm_threshold:
                    logger.debug(f"Using LLM score {llm_score:.4f} (strong signal)")
                    return llm_score

                # If LLM is neutral-ish, get VADER score and compare
                try:
                    vader_score = self._vader_service.analyze_sentiment(text)

                    # Choose the score that is furthest from 0 (most decisive)
                    if abs(vader_score) > abs(llm_score):
                        logger.debug(
                            f"Using VADER score {vader_score:.4f} over LLM {llm_score:.4f} (further from neutral)"
                        )
                        return vader_score
                    else:
                        logger.debug(
                            f"Using LLM score {llm_score:.4f} over VADER {vader_score:.4f}"
                        )
                        return llm_score

                except Exception as vader_e:
                    logger.warning(f"VADER analysis failed, using LLM score: {vader_e}")
                    return llm_score

            except Exception as llm_e:
                logger.warning(f"LLM analysis failed: {llm_e}")
                if self._vader_service:
                    logger.info("Falling back to VADER sentiment analysis")
                    return self._vader_service.analyze_sentiment(text)
                else:
                    raise RuntimeError(f"Sentiment analysis failed: {llm_e}") from llm_e

        # Original logic for non-dual-model mode
        elif self.use_llm and self._llm_service:
            try:
                return self._llm_service.analyze_sentiment(text)
            except Exception as e:
                logger.warning(f"LLM sentiment analysis failed: {e}")
                if self.fallback_to_vader and self._vader_service:
                    logger.info("Falling back to VADER sentiment analysis")
                    return self._vader_service.analyze_sentiment(text)
                else:
                    raise RuntimeError(f"Sentiment analysis failed: {e}") from e

        elif self._vader_service:
            try:
                return self._vader_service.analyze_sentiment(text)
            except Exception as e:
                logger.error(f"VADER sentiment analysis failed: {e}")
                raise RuntimeError(f"Sentiment analysis failed: {e}") from e

        else:
            raise RuntimeError("No sentiment analysis service available")

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

    def get_service_info(self) -> dict[str, Any]:
        """Get information about the current sentiment service.

        Returns:
            Dictionary with service information
        """
        info = {
            "use_llm": self.use_llm,
            "llm_model_name": self.llm_model_name,
            "use_gpu": self.use_gpu,
            "fallback_to_vader": self.fallback_to_vader,
        }

        if self.use_llm and self._llm_service:
            info.update(self._llm_service.get_model_info())
        elif self._vader_service:
            info["service_type"] = "VADER"
            info["is_loaded"] = True

        return info


# Global instance for easy access
_hybrid_sentiment_service: HybridSentimentService | None = None


def get_hybrid_sentiment_service() -> HybridSentimentService:
    """
    Get the global hybrid sentiment service instance.

    Returns:
        HybridSentimentService instance
    """
    global _hybrid_sentiment_service
    if _hybrid_sentiment_service is None:
        # Check environment variables for configuration (LLM by default)
        use_llm = os.getenv("SENTIMENT_USE_LLM", "true").lower() == "true"
        llm_model = os.getenv("SENTIMENT_LLM_MODEL", "ProsusAI/finbert")
        use_gpu = os.getenv("SENTIMENT_USE_GPU", "false").lower() == "true"
        fallback_vader = os.getenv("SENTIMENT_FALLBACK_VADER", "true").lower() == "true"
        dual_model_strategy = (
            os.getenv("SENTIMENT_DUAL_MODEL", "true").lower() == "true"
        )
        strong_llm_threshold = float(os.getenv("SENTIMENT_STRONG_THRESHOLD", "0.2"))

        _hybrid_sentiment_service = HybridSentimentService(
            use_llm=use_llm,
            llm_model_name=llm_model,
            use_gpu=use_gpu,
            fallback_to_vader=fallback_vader,
            dual_model_strategy=dual_model_strategy,
            strong_llm_threshold=strong_llm_threshold,
        )
    return _hybrid_sentiment_service


def analyze_sentiment_hybrid(text: str) -> float:
    """
    Convenience function to analyze sentiment using hybrid service.

    Args:
        text: The text to analyze for sentiment

    Returns:
        Float between -1.0 (most negative) and 1.0 (most positive)
    """
    service = get_hybrid_sentiment_service()
    return service.analyze_sentiment(text)
