"""Simple Slack notification service for admin alerts."""

import logging
from datetime import UTC, datetime
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.config import settings

logger = logging.getLogger(__name__)


class SlackService:
    """Simple service for sending notifications to Slack."""

    def __init__(self) -> None:
        """Initialize Slack service."""
        self._client: WebClient | None = None
        self._default_channel: str | None = None
        self._users_channel: str | None = None
        self._reddit_channel: str | None = None

        if not settings.slack_bot_token:
            logger.debug("Slack bot token not configured, notifications disabled")
            return

        try:
            self._client = WebClient(token=settings.slack_bot_token)
            self._default_channel = settings.slack_default_channel
            self._users_channel = (
                settings.slack_users_channel or settings.slack_default_channel
            )
            self._reddit_channel = settings.slack_reddit_channel
        except Exception as e:
            logger.warning(f"Failed to initialize Slack client: {e}")
            self._client = None

    def _get_channel(self, job_name: str | None = None) -> str | None:
        """Get channel ID for a job or use default."""
        if job_name:
            if (
                job_name.startswith("reddit_scraper")
                and self._reddit_channel
                and self._reddit_channel.strip()
            ):
                return self._reddit_channel
        return self._default_channel

    def send_message(
        self,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        channel: str | None = None,
        thread_ts: str | None = None,
    ) -> str | None:
        """Send a message to Slack.

        Args:
            text: Fallback text for the message
            blocks: Optional Slack blocks for rich formatting
            channel: Channel ID (uses default if not provided)
            thread_ts: Optional thread timestamp to reply in thread

        Returns:
            Message timestamp (ts) if successful, None otherwise
        """
        if not self._client:
            return None

        target_channel = channel or self._default_channel
        if not target_channel:
            logger.debug("No Slack channel configured")
            return None

        try:
            kwargs: dict[str, Any] = {
                "channel": target_channel,
                "text": text,
            }
            if blocks:
                kwargs["blocks"] = blocks  # type: ignore[arg-type]
            if thread_ts:
                kwargs["thread_ts"] = thread_ts

            response = self._client.chat_postMessage(**kwargs)  # type: ignore[arg-type]

            if response.get("ok"):
                return response.get("ts")
            return None

        except SlackApiError as e:
            logger.error(f"Slack API error: {e.response}")
            return None
        except Exception as e:
            logger.error(f"Failed to send Slack message: {e}")
            return None

    def notify_job_start(
        self,
        job_name: str,
        environment: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Notify that a job has started.

        Args:
            job_name: Name of the job
            environment: Environment name (e.g., 'production')
            metadata: Optional metadata dict

        Returns:
            Message timestamp (ts) for threading, or None
        """
        env = environment or getattr(settings, "environment", "development")

        metadata_text = ""
        if metadata:
            items = [f"• {k}: {v}" for k, v in metadata.items()]
            metadata_text = "\n" + "\n".join(items)

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚀 Job Started: {job_name}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Environment:*\n{env}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Started:*\n{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                    },
                ],
            },
        ]

        if metadata_text:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Details:*{metadata_text}",
                    },
                }
            )

        return self.send_message(
            text=f"Job {job_name} started in {env}",
            blocks=blocks,
            channel=self._get_channel(job_name),
        )

    def notify_job_complete(
        self,
        job_name: str,
        status: str,
        duration_seconds: float,
        environment: str | None = None,
        summary: dict[str, Any] | None = None,
        error: str | None = None,
        thread_ts: str | None = None,
    ) -> None:
        """Notify that a job has completed.

        Args:
            job_name: Name of the job
            status: 'success', 'failure', or 'error'
            duration_seconds: Job duration in seconds
            environment: Environment name
            summary: Optional summary dict with metrics
            error: Optional error message
            thread_ts: Thread timestamp to reply in thread
        """
        env = environment or getattr(settings, "environment", "development")

        status_emoji = {"success": "✅", "failure": "⚠️", "error": "❌"}.get(
            status, "🔔"
        )

        summary_text = ""
        if summary:
            items = [f"• {k}: {v}" for k, v in summary.items()]
            summary_text = "\n" + "\n".join(items)

        error_text = ""
        if error:
            error_text = f"\n\n*Error:*\n```{error[:500]}```"

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{status_emoji} Job Completed: {job_name}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Status:*\n{status.upper()}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Duration:*\n{duration_seconds:.2f}s",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Finished:*\n{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Environment:*\n{env}",
                    },
                ],
            },
        ]

        if summary_text:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Summary:*{summary_text}",
                    },
                }
            )

        if error_text:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": error_text},
                }
            )

        self.send_message(
            text=f"Job {job_name} completed with status {status}",
            blocks=blocks,
            channel=self._get_channel(job_name),
            thread_ts=thread_ts,
        )

    def notify_user_created(
        self,
        user_id: int,
        email: str,
        display_name: str | None,
        total_users: int,
        environment: str | None = None,
    ) -> None:
        """Notify that a new user has registered (first login).

        Args:
            user_id: User ID
            email: User email
            display_name: User display name (if available)
            total_users: Total number of active users
            environment: Environment name
        """
        env = environment or getattr(settings, "environment", "development")

        display_name_text = f" ({display_name})" if display_name else ""

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "👤 New User Registered",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Email:*\n{email}{display_name_text}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*User ID:*\n{user_id}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Total Users:*\n{total_users}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Environment:*\n{env}",
                    },
                ],
            },
        ]

        self.send_message(
            text=f"New user registered: {email}",
            blocks=blocks,
            channel=self._users_channel,
        )


def get_slack_service() -> SlackService:
    """Get Slack service instance."""
    return SlackService()
