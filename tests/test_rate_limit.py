from fastapi.testclient import TestClient

from app.main import app


def test_health_not_rate_limited():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
