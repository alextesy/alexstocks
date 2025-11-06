from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

import jobs.jobs.daily_ticker_summary as job_module
from app.services.daily_summary import (
    DailySummaryArticle,
    DailySummaryResult,
    DailyTickerSummary,
)


def _fake_summary() -> DailySummaryResult:
    article = DailySummaryArticle(
        article_id=1,
        ticker="TSLA",
        title="Tesla momentum builds",
        url="https://reddit.com/tsla",
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
        window_start=datetime(2024, 5, 2, 0, 0, tzinfo=UTC),
        window_end=datetime(2024, 5, 3, 0, 0, tzinfo=UTC),
        tickers=[ticker],
        total_mentions=3,
        total_ranked_articles=1,
    )


class FakeSession:
    closed = False

    def close(self) -> None:  # pragma: no cover - simple close
        self.closed = True


class FakeSlackService:
    instances: list[FakeSlackService] = []

    def __init__(self) -> None:
        self.__class__.instances.append(self)
        self.starts: list[tuple[str, dict[str, Any] | None]] = []
        self.completions: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []

    def notify_job_start(
        self, job_name: str, metadata: dict[str, Any] | None = None
    ) -> str:
        self.starts.append((job_name, metadata))
        return "thread-1"

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
        return "msg-1"


class FakeSummaryService:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.summary = _fake_summary()

    def load_previous_day_summary(self) -> DailySummaryResult:
        return self.summary

    def build_langchain_payload(self, summary: DailySummaryResult) -> dict[str, Any]:
        return {
            "framework": "langchain",
            "llm": {"api_key": "sk-test"},
            "prompt": "test",
        }

    def build_langgraph_payload(self, summary: DailySummaryResult) -> dict[str, Any]:
        return {
            "framework": "langgraph",
            "config": {},
        }

    def generate_langchain_summary(self, summary: DailySummaryResult) -> list[str]:
        return ["Summary text"]


class FailingSummaryService(FakeSummaryService):
    def load_previous_day_summary(self) -> DailySummaryResult:
        raise RuntimeError("boom")


def test_run_daily_summary_success(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSlackService.instances.clear()
    monkeypatch.setattr(job_module, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(job_module, "SlackService", FakeSlackService)
    monkeypatch.setattr(job_module, "DailySummaryService", FakeSummaryService)
    monkeypatch.setattr(job_module.settings, "daily_summary_start_offset_minutes", 15)
    monkeypatch.setattr(job_module.settings, "daily_summary_end_offset_minutes", 45)

    result = job_module.run_daily_summary(framework="langchain")

    assert result["metrics"]["tickers"] == 1
    fake_slack = FakeSlackService.instances[-1]
    assert fake_slack.starts[0][0] == job_module.JOB_NAME
    assert fake_slack.completions[0]["status"] == "success"
    assert fake_slack.completions[0]["summary"]["framework"] == "langchain"
    assert result["responses"] == ["Summary text"]
    assert fake_slack.messages[0]["text"] == "Summary text"


def test_run_daily_summary_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSlackService.instances.clear()
    monkeypatch.setattr(job_module, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(job_module, "SlackService", FakeSlackService)
    monkeypatch.setattr(job_module, "DailySummaryService", FailingSummaryService)
    monkeypatch.setattr(job_module.settings, "daily_summary_start_offset_minutes", 15)
    monkeypatch.setattr(job_module.settings, "daily_summary_end_offset_minutes", 45)

    with pytest.raises(RuntimeError):
        job_module.run_daily_summary(framework="langchain")

    fake_slack = FakeSlackService.instances[-1]
    assert fake_slack.completions[0]["status"] == "error"
    assert fake_slack.completions[0]["error"] == "boom"


def test_main_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(job_module, "run_daily_summary", lambda framework: None)
    assert job_module.main(["--framework", "langgraph"]) == 0

    def _raise(_: str) -> None:
        raise RuntimeError("fail")

    monkeypatch.setattr(job_module, "run_daily_summary", _raise)
    assert job_module.main(["--framework", "langchain"]) == 1
