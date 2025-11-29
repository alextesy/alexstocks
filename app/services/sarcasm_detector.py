"""Sarcasm and irony detection utilities for sentiment moderation."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

try:
    from transformers import pipeline

    TRANSFORMERS_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    TRANSFORMERS_AVAILABLE = False
    logger.warning(
        "Transformers not available; sarcasm detection will use heuristics only"
    )


@dataclass
class SarcasmPrediction:
    """Container for sarcasm detection results."""

    probability: float
    is_sarcastic: bool
    source: str


class SarcasmDetector:
    """Detect sarcastic tone in text and provide a probability score.

    The detector prefers a lightweight Hugging Face model and falls back to
    heuristic scoring if transformers are unavailable.
    """

    def __init__(
        self,
        model_name: str = "cardiffnlp/twitter-roberta-base-irony",
        sarcasm_label: str | None = None,
        fallback_threshold: float = 0.6,
    ) -> None:
        self.model_name = model_name
        self.sarcasm_label = sarcasm_label
        self.fallback_threshold = fallback_threshold
        self._classifier: Any = None
        self._model_source = "heuristic"

        if TRANSFORMERS_AVAILABLE:
            try:
                self._classifier = pipeline(
                    "text-classification", model=self.model_name, return_all_scores=True
                )
                self._model_source = self.model_name
                logger.info("Loaded sarcasm detector model: %s", self.model_name)
            except Exception as exc:  # pragma: no cover - model load variability
                logger.warning(
                    "Failed to load sarcasm model (%s); using heuristics. %s",
                    self.model_name,
                    exc,
                )
                self._classifier = None

    def predict(self, text: str) -> SarcasmPrediction:
        if not text or not text.strip():
            raise ValueError("Text cannot be empty or None")

        if self._classifier:
            try:
                return self._predict_with_model(text)
            except Exception as exc:  # pragma: no cover - runtime model errors
                logger.warning(
                    "Sarcasm model inference failed; falling back to heuristics. %s",
                    exc,
                )

        score = self._heuristic_score(text)
        return SarcasmPrediction(
            probability=score,
            is_sarcastic=score >= self.fallback_threshold,
            source="heuristic",
        )

    def _predict_with_model(self, text: str) -> SarcasmPrediction:
        cleaned = text.strip()
        results = self._classifier(cleaned)
        if not results:
            raise RuntimeError("Sarcasm classifier returned no results")

        score_map = {}
        for entry in results[0]:
            label = entry["label"].lower()
            score_map[label] = entry["score"]

        # Determine which label corresponds to sarcasm/irony
        sarcasm_keys = [
            self.sarcasm_label,
            "sarcasm",
            "sarcastic",
            "irony",
            "ironic",
            "label_1",
        ]
        sarcasm_keys = [key.lower() for key in sarcasm_keys if key]

        sarcasm_score = 0.0
        neutral_score = 0.0
        for label, score in score_map.items():
            if any(key in label for key in sarcasm_keys):
                sarcasm_score = max(sarcasm_score, score)
            elif "label_0" == label or "non_sarcastic" in label:
                neutral_score = max(neutral_score, score)

        # Normalize if we have both scores
        probability = sarcasm_score
        if sarcasm_score and neutral_score:
            probability = sarcasm_score / max(sarcasm_score + neutral_score, 1e-6)

        return SarcasmPrediction(
            probability=float(probability),
            is_sarcastic=probability >= self.fallback_threshold,
            source=self._model_source,
        )

    def _heuristic_score(self, text: str) -> float:
        lowered = text.lower()
        cues = [
            "yeah right",
            "totally",
            "sure",
            "as if",
            "obviously",
            "great",
            "amazing",
        ]
        punctuation_boost = 0.1 if "?!" in text or text.count("!") >= 3 else 0.0
        exaggerated_caps = 0.1 if re.search(r"[A-Z]{4,}", text) else 0.0
        cue_score = sum(1 for cue in cues if cue in lowered) * 0.15
        return min(1.0, cue_score + punctuation_boost + exaggerated_caps)


def get_sarcasm_detector() -> SarcasmDetector:
    return SarcasmDetector()


def detect_sarcasm(text: str) -> SarcasmPrediction:
    detector = get_sarcasm_detector()
    return detector.predict(text)
