from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.models import Article, ArticleTicker, Ticker
from app.services.mention_stats import MentionStatsService


def _insert(
    session: Session, *, sym: str, ts: datetime, url_suffix: str, source: str = "reddit"
) -> None:
    art = Article(
        source=source,
        url=f"https://example.com/{url_suffix}",
        published_at=ts,
        title=f"Post about {sym}",
        text=f"I like ${sym}",
        lang="en",
    )
    session.add(art)
    session.flush()
    session.add(ArticleTicker(article_id=art.id, ticker=sym, confidence=1.0))


def test_mentions_hourly_zero_fill_and_alignment(db_session: Session):
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    # Insert AAPL at now-2h and now
    _insert(db_session, sym="AAPL", ts=now - timedelta(hours=2), url_suffix="aapl-1")
    _insert(db_session, sym="AAPL", ts=now, url_suffix="aapl-2")
    # Insert TSLA at now-1h twice
    _insert(db_session, sym="TSLA", ts=now - timedelta(hours=1), url_suffix="tsla-1")
    _insert(db_session, sym="TSLA", ts=now - timedelta(hours=1), url_suffix="tsla-2")

    db_session.add_all(
        [Ticker(symbol="AAPL", name="Apple"), Ticker(symbol="TSLA", name="Tesla")]
    )
    db_session.commit()

    service = MentionStatsService(db_session)
    payload = service.get_mentions_hourly(["AAPL", "TSLA"], hours=3)

    assert payload.hours == 3
    assert len(payload.labels) == 3
    # Labels should be hourly and end at current hour
    assert payload.labels[-1].endswith(":00:00+00:00")

    series = {s.symbol: s.data for s in payload.series}
    assert series["AAPL"] == [1, 0, 1]  # -2h:1, -1h:0, 0h:1
    assert series["TSLA"] == [0, 2, 0]  # -2h:0, -1h:2, 0h:0


