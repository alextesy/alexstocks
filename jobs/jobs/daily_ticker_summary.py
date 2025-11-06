"""Batch job that prepares the daily ticker summary LLM payload."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from typing import Any

sys.path.append(".")

from app.config import settings
from app.db.session import SessionLocal
from app.services.daily_summary import DailySummaryResult, DailySummaryService
from app.services.slack_service import SlackService

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)

JOB_NAME = "daily_ticker_summary"


def run_daily_summary(framework: str = "langchain") -> dict[str, Any]:
    """Execute the daily summary job and return metrics."""

    start = datetime.now(UTC)
    slack = SlackService()
    metadata = {
        "framework": framework,
        "start_offset_min": settings.daily_summary_start_offset_minutes,
        "end_offset_min": settings.daily_summary_end_offset_minutes,
    }
    thread_ts = slack.notify_job_start(JOB_NAME, metadata=metadata)

    session = SessionLocal()
    try:
        service = DailySummaryService(session)
        summary = service.load_previous_day_summary()
        payload = _build_payload(service, summary, framework)

        llm_responses: list[str] = []
        if framework == "langchain":
            llm_responses = service.generate_langchain_summary(summary)

        metrics = {
            "tickers": len(summary.tickers),
            "articles": summary.total_ranked_articles,
            "mentions": summary.total_mentions,
            "window_start": summary.window_start.isoformat(),
            "window_end": summary.window_end.isoformat(),
            "framework": framework,
            "llm_responses": len(llm_responses),
        }

        logger.info(
            "Daily ticker summary payload generated",
            extra={"metrics": metrics},
        )

        if llm_responses:
            slack.send_message(
                text="\n\n".join(llm_responses),
                thread_ts=thread_ts,
            )

        duration = (datetime.now(UTC) - start).total_seconds()
        slack.notify_job_complete(
            job_name=JOB_NAME,
            status="success",
            duration_seconds=duration,
            summary=metrics,
            thread_ts=thread_ts,
        )
        return {"payload": payload, "metrics": metrics, "responses": llm_responses}
    except Exception as exc:  # noqa: BLE001
        duration = (datetime.now(UTC) - start).total_seconds()
        logger.exception(
            "Daily ticker summary job failed", extra={"framework": framework}
        )
        slack.notify_job_complete(
            job_name=JOB_NAME,
            status="error",
            duration_seconds=duration,
            summary={"framework": framework},
            error=str(exc),
            thread_ts=thread_ts,
        )
        raise
    finally:
        session.close()


def _build_payload(
    service: DailySummaryService,
    summary: DailySummaryResult,
    framework: str,
) -> dict[str, Any]:
    if framework == "langchain":
        return service.build_langchain_payload(summary)
    if framework == "langgraph":
        return service.build_langgraph_payload(summary)
    raise ValueError("Unsupported framework. Choose 'langchain' or 'langgraph'.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the daily ticker summary")
    parser.add_argument(
        "--framework",
        choices=["langchain", "langgraph"],
        default="langchain",
        help="Payload format to emit",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run_daily_summary(framework=args.framework)
    except Exception:  # noqa: BLE001
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
