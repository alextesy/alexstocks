"""Simple wrapper for adding Slack notifications to jobs."""

import logging
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

# Add project root to path
sys.path.append(".")

from app.services.slack_service import get_slack_service

logger = logging.getLogger(__name__)


def run_with_slack(
    job_name: str,
    job_func: Callable[[], Any] | Callable[[], Awaitable[Any]],
    metadata: dict[str, Any] | None = None,
) -> Any:
    """Run a job function with Slack start/complete notifications.

    Args:
        job_name: Name of the job for Slack notifications
        job_func: Job function (sync or async)
        metadata: Optional metadata to include in start message

    Returns:
        Result from job function
    """
    import asyncio

    slack = get_slack_service()
    start_time = datetime.now(UTC)

    # Send start notification
    thread_ts = slack.notify_job_start(job_name, metadata=metadata)

    status = "success"
    error_msg: str | None = None
    summary: dict[str, Any] | None = None

    try:
        # Execute job
        if asyncio.iscoroutinefunction(job_func):
            result = asyncio.run(job_func())
        else:
            result = job_func()

        # Extract summary from result if it's a dict
        if isinstance(result, dict):
            summary = {
                k: v
                for k, v in result.items()
                if k
                in (
                    "success",
                    "failed",
                    "processed",
                    "count",
                    "duration",
                    "new_comments",
                    "articles_created",
                )
            }

        return result

    except Exception as e:
        status = "error"
        error_msg = str(e)
        logger.exception(f"Job {job_name} failed")
        raise

    finally:
        # Send completion notification
        duration = (datetime.now(UTC) - start_time).total_seconds()
        slack.notify_job_complete(
            job_name=job_name,
            status=status,
            duration_seconds=duration,
            summary=summary,
            error=error_msg,
            thread_ts=thread_ts,
        )
