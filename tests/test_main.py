"""Tests for main application endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    """Test the health endpoint returns ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_home_page():
    """Test the home page loads without error."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Market Pulse" in response.text


def test_ticker_page():
    """Test a ticker page loads without error."""
    response = client.get("/t/AAPL")
    assert response.status_code == 200
    assert "AAPL" in response.text
