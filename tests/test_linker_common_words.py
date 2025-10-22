from typing import cast
from unittest.mock import Mock, patch

import pytest

from app.db.models import Article, Ticker
from jobs.ingest.linker import TickerLinker


@pytest.fixture()
def linker() -> TickerLinker:
    mock_tickers = [
        Mock(symbol=s)
        for s in [
            "FAT",
            "NERD",
            "CUT",
            "CHAT",
            "PICK",
            "AIN",
            "CAR",
            "SELF",
            "WEN",
            "CUZ",
            "FLOW",
            "THO",
            "PRE",
            "RULE",
            "BROS",
            "WILD",
            "COKE",
            "DOG",
            "TIP",
            "TBH",
            "FAN",
            "WEED",
            "VS",
            "WEST",
            "PM",
            "DD",
            "YOLO",
            "A",
            "TAX",
            "AGO",
        ]
    ]

    with (
        patch("jobs.ingest.linker.get_content_scraper") as mock_scraper,
        patch("jobs.ingest.linker.get_context_analyzer") as mock_ctx,
    ):
        mock_scraper.return_value = Mock()
        mock_ctx.return_value = Mock()
        return TickerLinker(cast(list[Ticker], mock_tickers))


def make_article(source: str, title: str, text: str) -> Article:
    a = Mock()
    a.source = source
    a.title = title
    a.text = text
    a.url = "https://example.com"
    return cast(Article, a)


def test_aint_not_linked(linker: TickerLinker):
    matches = linker._find_ticker_matches("That ain't it chief")
    assert "AIN" not in matches


def test_arent_not_linked(linker: TickerLinker):
    matches = linker._find_ticker_matches("We aren't going there")
    assert "AREN" not in matches


@pytest.mark.parametrize(
    "word",
    [
        "FAT",
        "NERD",
        "CUT",
        "CHAT",
        "PICK",
        "CAR",
        "SELF",
        "WEN",
        "CUZ",
        "FLOW",
        "THO",
        "PRE",
        "RULE",
        "BROS",
        "WILD",
        "COKE",
        "DOG",
        "TIP",
        "TBH",
        "FAN",
        "WEED",
        "VS",
        "WEST",
    ],
)
def test_common_words_only_all_caps_or_cashtag(linker: TickerLinker, word: str):
    # lower/mixed should not link
    assert word.lower() not in linker._find_ticker_matches(
        f"i like {word.lower()} a lot"
    )
    assert word.lower() not in linker._find_ticker_matches(
        f"I like {word.title()} a lot"
    )

    # ALL CAPS standalone should link
    matches_caps = linker._find_ticker_matches(f"Thinking about {word} today")
    assert word in matches_caps

    # cashtag should link regardless of case
    matches_cash = linker._find_ticker_matches(f"I like ${word.lower()} here")
    assert word in matches_cash


@pytest.mark.parametrize("acro", ["PM", "DD", "YOLO"])
def test_acronyms_require_cashtag(linker: TickerLinker, acro: str):
    # Plain uppercase should not link
    assert acro not in linker._find_ticker_matches(f"I will do some {acro} later")
    # Cashtag should link
    matches = linker._find_ticker_matches(f"Looking at ${acro} now")
    assert acro in matches


@pytest.mark.parametrize("word", ["TAX", "AGO"])
def test_lowercase_does_not_link_but_caps_or_cashtag_does(
    linker: TickerLinker, word: str
):
    # lower-case should not link
    assert word not in linker._find_ticker_matches(
        f"i paid some {word.lower()} yesterday"
    )
    # ALL CAPS standalone should link
    caps = linker._find_ticker_matches(f"Thinking about {word} today")
    assert word in caps
    # cashtag should link
    cash = linker._find_ticker_matches(f"Considering ${word.lower()} too")
    assert word in cash


def test_single_letter_only_cashtag(linker: TickerLinker):
    # Single-letter A should not link unless cashtag
    assert "A" not in linker._find_ticker_matches("This is a test A word")
    matches = linker._find_ticker_matches("I like $A today")
    assert "A" in matches


def test_reddit_comment_lowercase_ago_not_linked(linker: TickerLinker):
    article = make_article(
        "reddit_comment",
        "",
        "I am no bear and never will be. But… Why is all of WSB going crazy over one speculative WSJ article from 2 days ago?",
    )
    # Fast path for reddit comments must not link AGO here
    links = linker.link_article(article, use_title_only=True)
    assert all(link.ticker != "AGO" for link in links)


def test_reddit_comment_lowercase_tax_not_linked(linker: TickerLinker):
    article = make_article(
        "reddit_comment",
        "",
        (
            "The ones who actually need IVF are the ones who tried to actually build a nest "
            "egg before making a baby.  The scumbags who just keep nutting no pull out and "
            "need child care tax credit are the ones you should be angry with. "
        ),
    )
    # Fast path for reddit comments must not link TAX here
    links = linker.link_article(article, use_title_only=True)
    assert all(link.ticker != "TAX" for link in links)
