"""Hybrid sentiment analysis service that can use VADER or LLM models."""

import logging
import os
from typing import Any

from app.services.llm_sentiment import get_llm_sentiment_service
from app.services.sarcasm_detector import SarcasmDetector, SarcasmPrediction
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
        enable_sarcasm_detection: bool = True,
        sarcasm_threshold: float = 0.65,
        sarcasm_dampening_factor: float = 0.55,
        sarcasm_model_name: str | None = None,
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
        self.enable_sarcasm_detection = enable_sarcasm_detection
        self.sarcasm_threshold = sarcasm_threshold
        self.sarcasm_dampening_factor = sarcasm_dampening_factor

        self._vader_service = None
        self._llm_service = None
        self._sarcasm_detector: SarcasmDetector | None = None

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

                # Also load VADER if fallback is enabled
                if self.fallback_to_vader:
                    try:
                        self._vader_service = get_vader_service()
                        logger.info("VADER service loaded for fallback")
                    except Exception as vader_e:
                        logger.warning(f"Failed to load VADER for fallback: {vader_e}")

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

        if self.enable_sarcasm_detection:
            try:
                self._sarcasm_detector = SarcasmDetector(
                    model_name=sarcasm_model_name
                    or "cardiffnlp/twitter-roberta-base-irony"
                )
            except Exception as exc:
                logger.warning("Failed to initialize sarcasm detector: %s", exc)

    def _compute_base_score(self, text: str) -> float:
        if not text or not text.strip():
            raise ValueError("Text cannot be empty or None")

        if self.dual_model_strategy and self._llm_service and self._vader_service:
            try:
                llm_score = self._llm_service.analyze_sentiment(text)

                if abs(llm_score) > self.strong_llm_threshold:
                    logger.debug(f"Using LLM score {llm_score:.4f} (strong signal)")
                    return llm_score

                try:
                    vader_score = self._vader_service.analyze_sentiment(text)

                    if abs(vader_score) > abs(llm_score):
                        logger.debug(
                            "Using VADER score %s over LLM %s (further from neutral)",
                            f"{vader_score:.4f}",
                            f"{llm_score:.4f}",
                        )
                        return vader_score

                    logger.debug(
                        "Using LLM score %s over VADER %s",
                        f"{llm_score:.4f}",
                        f"{vader_score:.4f}",
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
                raise RuntimeError(f"Sentiment analysis failed: {llm_e}") from llm_e

        if self.use_llm and self._llm_service:
            try:
                return self._llm_service.analyze_sentiment(text)
            except Exception as e:
                logger.warning(f"LLM sentiment analysis failed: {e}")
                if self.fallback_to_vader and self._vader_service:
                    logger.info("Falling back to VADER sentiment analysis")
                    return self._vader_service.analyze_sentiment(text)
                raise RuntimeError(f"Sentiment analysis failed: {e}") from e

        if self._vader_service:
            try:
                return self._vader_service.analyze_sentiment(text)
            except Exception as e:
                logger.error(f"VADER sentiment analysis failed: {e}")
                raise RuntimeError(f"Sentiment analysis failed: {e}") from e

        raise RuntimeError("No sentiment analysis service available")

    def _apply_sarcasm_adjustment(
        self, base_score: float, text: str
    ) -> tuple[float, SarcasmPrediction | None, float | None]:
        if not self._sarcasm_detector:
            return base_score, None, None

        try:
            prediction = self._sarcasm_detector.predict(text)
        except Exception as exc:
            logger.warning("Sarcasm detection failed: %s", exc)
            return base_score, None, None

        if prediction.probability < self.sarcasm_threshold:
            return base_score, prediction, None

        adjustment = max(
            0.0, 1 - prediction.probability * self.sarcasm_dampening_factor
        )
        adjusted_score = base_score * adjustment
        logger.debug(
            "Applied sarcasm adjustment",
            extra={
                "base": base_score,
                "adjusted": adjusted_score,
                "sarcasm_probability": prediction.probability,
            },
        )
        return adjusted_score, prediction, adjustment

    def _analyze(self, text: str) -> dict[str, Any]:
        base_score = self._compute_base_score(text)
        adjusted_score, sarcasm_prediction, adjustment = self._apply_sarcasm_adjustment(
            base_score, text
        )

        return {
            "raw_score": base_score,
            "adjusted_score": adjusted_score,
            "sarcasm": sarcasm_prediction,
            "sarcasm_adjustment": adjustment,
        }

    def analyze_sentiment(self, text: str) -> float:
        details = self._analyze(text)
        return details["adjusted_score"]

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
        adjusted_score = self.analyze_sentiment(text)
        label = self.get_sentiment_label(adjusted_score)
        return adjusted_score, label

    def analyze_with_details(self, text: str) -> dict[str, Any]:
        """Analyze sentiment with sarcasm metadata for exploratory use."""

        details = self._analyze(text)
        details["label"] = self.get_sentiment_label(details["adjusted_score"])
        return details

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
            "enable_sarcasm_detection": self.enable_sarcasm_detection,
            "sarcasm_threshold": self.sarcasm_threshold,
            "sarcasm_dampening_factor": self.sarcasm_dampening_factor,
        }

        if self.use_llm and self._llm_service:
            info.update(self._llm_service.get_model_info())
        elif self._vader_service:
            info["service_type"] = "VADER"
            info["is_loaded"] = True

        if self._sarcasm_detector:
            info["sarcasm_model"] = "heuristic"
            if self._sarcasm_detector._classifier:  # type: ignore[attr-defined]
                info["sarcasm_model"] = self._sarcasm_detector.model_name

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
        enable_sarcasm_detection = (
            os.getenv("SENTIMENT_SARCASM_DETECTION", "true").lower() == "true"
        )
        sarcasm_threshold = float(os.getenv("SENTIMENT_SARCASM_THRESHOLD", "0.65"))
        sarcasm_dampening_factor = float(
            os.getenv("SENTIMENT_SARCASM_DAMPENING", "0.55")
        )
        sarcasm_model_name = os.getenv(
            "SENTIMENT_SARCASM_MODEL", "cardiffnlp/twitter-roberta-base-irony"
        )

        _hybrid_sentiment_service = HybridSentimentService(
            use_llm=use_llm,
            llm_model_name=llm_model,
            use_gpu=use_gpu,
            fallback_to_vader=fallback_vader,
            dual_model_strategy=dual_model_strategy,
            strong_llm_threshold=strong_llm_threshold,
            enable_sarcasm_detection=enable_sarcasm_detection,
            sarcasm_threshold=sarcasm_threshold,
            sarcasm_dampening_factor=sarcasm_dampening_factor,
            sarcasm_model_name=sarcasm_model_name,
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


def get_sentiment_service() -> HybridSentimentService:
    """
    Alias for get_hybrid_sentiment_service for backward compatibility.

    Returns:
        HybridSentimentService instance
    """
    return get_hybrid_sentiment_service()
