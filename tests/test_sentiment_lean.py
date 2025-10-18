from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Article, ArticleTicker, Base, Ticker
from app.services.sentiment_analytics import SentimentAnalyticsService


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def add_article(session, sentiment: float | None, ticker: str, days_ago: int = 0):
    t = session.query(Ticker).filter_by(symbol=ticker).first()
    if not t:
        t = Ticker(symbol=ticker, name=ticker)
        session.add(t)
        session.flush()

    a = Article(
        title=f"{ticker} test",
        url=f"https://example.com/{ticker}",
        source="reddit_post",
        published_at=datetime.utcnow() - timedelta(days=days_ago),
        sentiment=sentiment,
    )
    session.add(a)
    session.flush()
    session.add(ArticleTicker(article_id=a.id, ticker=ticker))
    session.commit()


def test_all_neutral_results_in_neutral_label():
    session = make_session()
    add_article(session, 0.0, "AAA")
    add_article(session, 0.01, "AAA")
    add_article(session, -0.01, "AAA")

    svc = SentimentAnalyticsService()
    data = svc.get_sentiment_lean_data(session, ticker="AAA", days=1)
    assert data["leaning_label"] == "Neutral"
    assert data["neutral_dominant"] is True


def test_positive_lean_when_pos_gt_neg_and_neutral_below_threshold():
    session = make_session()
    # 2 positive, 1 negative, 1 neutral -> pos_neg=3, neutral_share=0.25
    add_article(session, 0.2, "BBB")
    add_article(session, 0.1, "BBB")
    add_article(session, -0.2, "BBB")
    add_article(session, 0.0, "BBB")

    svc = SentimentAnalyticsService()
    data = svc.get_sentiment_lean_data(session, ticker="BBB", days=1)
    assert data["leaning_label"] == "Leaning Positive"
    # pos_share_ex_neutral = 2/3
    assert round(data["pos_share_ex_neutral"], 3) == 0.667


def test_bulk_map_returns_expected_keys():
    session = make_session()
    add_article(session, 0.2, "CCC")
    add_article(session, -0.2, "DDD")

    svc = SentimentAnalyticsService()
    m = svc.get_ticker_lean_map(session, ["CCC", "DDD"], days=1)
    assert set(m.keys()) == {"CCC", "DDD"}
