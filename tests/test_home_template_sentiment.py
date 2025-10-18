from jinja2 import Environment, FileSystemLoader


def test_card_uses_lean_label_when_available(tmp_path):
    # Load template
    env = Environment(loader=FileSystemLoader("app/templates"))
    tmpl = env.get_template("home.html")

    # Minimal context simulating one ticker with leaning positive
    tickers = [
        {
            "symbol": "XYZ",
            "name": "XYZ Inc",
            "article_count": 10,
            "avg_sentiment": 0.01,
            "velocity": None,
            "stock_data": None,
            "sentiment_lean": {
                "leaning_score": 0.5,
                "pos_share_ex_neutral": 0.75,
                "neg_share_ex_neutral": 0.25,
                "neutral_dominant": False,
                "confidence": 0.9,
                "counts": {"positive": 3, "negative": 1, "neutral": 0, "total": 4},
            },
        }
    ]

    html = tmpl.render(
        request=None,
        tickers=tickers,
        sentiment_histogram={
            "total": 10,
            "percentages": {"neutral": 10},
            "display_data": [],
        },
        overall_lean={
            "leaning_score": 0.2,
            "pos_share_ex_neutral": 0.6,
            "neg_share_ex_neutral": 0.4,
            "confidence": 0.7,
        },
    )

    assert "Leaning Positive" in html
