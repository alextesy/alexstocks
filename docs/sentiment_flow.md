# Sentiment job flow

This page documents how the scheduled sentiment analysis task moves from the
Terraform definition to the Python services that score Reddit content.

1. **ECS task definition** (`infrastructure/terraform/ecs.tf`)
   - The `sentiment_analysis` task runs `python jobs/analyze_sentiment.py --source reddit --max-workers 2`.
   - Environment now includes `SENTIMENT_STRATEGY`, which defaults to `hybrid` and can be overridden per environment.

2. **Job entrypoint** (`jobs/jobs/analyze_sentiment.py`)
   - Parses CLI flags (including `--strategy` or `--no-sarcasm`) and loads defaults from `SentimentConfig.from_env()`.
   - Builds a single analyzer instance via `build_sentiment_service(config)` and reuses it across worker threads.
   - Fetches articles lacking sentiment, runs the analyzer, and persists scores.

3. **Service selection** (`app/services/sentiment_config.py`, `app/services/sentiment_selector.py`)
   - `SentimentConfig` captures strategy + sarcasm settings with sensible defaults.
   - `build_sentiment_service` maps the config to either VADER-only, LLM-only, or the existing `HybridSentimentService` with sarcasm dampening.

4. **Analysis engines**
   - `app/services/hybrid_sentiment.py`: LLM-first with VADER fallback and sarcasm adjustment.
   - `app/services/llm_sentiment.py`: Transformer-backed scorer (used inside the hybrid service).
   - `app/services/sentiment.py`: VADER-only scorer.
   - `app/services/sarcasm_detector.py`: Optional sarcasm probability used by the hybrid analyzer.

To change the behavior, tweak either the ECS environment variable, pass a CLI
flag, or adjust `SentimentConfig` defaults—no deeper code changes are needed
for common tweaks.
