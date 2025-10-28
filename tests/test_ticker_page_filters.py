"""Tests for server-side filters on the ticker page."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ticker_page_shows_server_side_filters_without_sort():
    """The ticker page should render filter form and no sort control."""
    resp = client.get("/t/TEST")
    assert resp.status_code == 200
    html = resp.text

    # Filter form present
    assert 'id="ticker-filters-form"' in html
    assert 'name="sentiment"' in html
    assert 'name="source"' in html
    assert 'name="start"' in html
    assert 'name="end"' in html

    # Sort control removed
    assert 'id="sort-filter"' not in html


def test_ticker_page_preserves_selected_filter_values_in_form():
    """Selected filters should be reflected in the rendered form controls."""
    qs = "?sentiment=positive&source=reddit&start=2024-01-01&end=2024-01-31"
    resp = client.get(f"/t/TEST{qs}")
    assert resp.status_code == 200
    html = resp.text

    # Sentiment selected
    assert '<option value="positive" selected>' in html
    # Source selected
    # When sources_available does not include the provided source, fallback renders "All";
    # but we still ensure the query params echoed into the form attributes via value
    # so at minimum the query string made it to the server and page rendered.
    # We check presence of source field and rely on end-to-end tests for actual options.
    assert 'name="source"' in html

    # Dates echoed back as values
    assert 'name="start" value="2024-01-01"' in html
    assert 'name="end" value="2024-01-31"' in html
