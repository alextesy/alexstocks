from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

import jobs.jobs.daily_status as daily_status
from app.services.daily_summary import (
    DailySummaryArticle,
    DailySummaryResult,
    DailyTickerSummary,
)


class FakeSlackService:
    def __init__(self) -> None:
        self.starts: list[tuple[str, dict[str, Any] | None]] = []
        self.completions: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []

    def notify_job_start(
        self, job_name: str, metadata: dict[str, Any] | None = None
    ) -> str:
        self.starts.append((job_name, metadata))
        return "thread"

    def notify_job_complete(
        self,
        job_name: str,
        status: str,
        duration_seconds: float,
        summary: dict[str, Any] | None = None,
        error: str | None = None,
        thread_ts: str | None = None,
    ) -> None:
        self.completions.append(
            {
                "job_name": job_name,
                "status": status,
                "summary": summary,
                "error": error,
                "thread_ts": thread_ts,
            }
        )

    def send_message(
        self,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        channel: str | None = None,
        thread_ts: str | None = None,
    ) -> str:
        self.messages.append(
            {
                "text": text,
                "blocks": blocks,
                "channel": channel,
                "thread_ts": thread_ts,
            }
        )
        return "msg"


@pytest.fixture
def fake_summary() -> DailySummaryResult:
    article = DailySummaryArticle(
        article_id=1,
        ticker="TSLA",
        title="Tesla momentum builds",
        url="https://reddit.com/tsla",
        text="Tesla stock is surging on strong delivery numbers.",
        published_at=datetime(2024, 5, 2, 15, 0, tzinfo=UTC),
        upvotes=100,
        num_comments=40,
        engagement_score=9.5,
        confidence=0.9,
        source="reddit",
        matched_terms=("tsla",),
        sentiment=0.35,
        subreddit="wallstreetbets",
        author="poster1",
    )
    ticker = DailyTickerSummary(ticker="TSLA", mentions=3, articles=[article])
    return DailySummaryResult(
        window_start=datetime(2024, 5, 2, 11, 0, tzinfo=UTC),
        window_end=datetime(2024, 5, 2, 23, 0, tzinfo=UTC),
        tickers=[ticker],
        total_mentions=3,
        total_ranked_articles=1,
    )


def test_run_status_job_sends_slack(
    monkeypatch: pytest.MonkeyPatch, fake_summary: DailySummaryResult
) -> None:
    fake_slack = FakeSlackService()

    monkeypatch.setattr(daily_status, "SlackService", lambda: fake_slack)
    monkeypatch.setattr(
        daily_status,
        "collect_reddit_status",
        lambda **_: {
            "total_threads": 5,
            "total_comments_scraped": 1234,
            "live_counts_enabled": True,
            "recent_threads": [],
        },
    )
    monkeypatch.setattr(daily_status, "_print_status", lambda *_, **__: None)
    monkeypatch.setattr(daily_status, "print", lambda *_, **__: None)
    monkeypatch.setattr(
        daily_status,
        "generate_daily_summary",
        lambda **_: (fake_summary, ["LLM output"]),
    )

    result = daily_status.run_daily_status_job()

    assert result["summary"]["tickers"] == 1
    assert fake_slack.starts[0][0] == daily_status.JOB_NAME
    assert fake_slack.completions[0]["status"] == "success"
    assert "LLM output" in fake_slack.messages[0]["text"]


def test_run_status_job_handles_summary_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_slack = FakeSlackService()

    monkeypatch.setattr(daily_status, "SlackService", lambda: fake_slack)
    monkeypatch.setattr(
        daily_status,
        "collect_reddit_status",
        lambda **_: {
            "total_threads": 5,
            "total_comments_scraped": 1234,
            "live_counts_enabled": True,
            "recent_threads": [],
        },
    )
    monkeypatch.setattr(daily_status, "_print_status", lambda *_, **__: None)
    monkeypatch.setattr(daily_status, "print", lambda *_, **__: None)
    monkeypatch.setattr(
        daily_status,
        "generate_daily_summary",
        lambda **_: (_ for _ in ()).throw(RuntimeError("fail")),
    )

    with pytest.raises(RuntimeError):
        daily_status.run_daily_status_job()

    assert fake_slack.completions[0]["status"] == "error"
    assert fake_slack.completions[0]["error"] == "fail"
