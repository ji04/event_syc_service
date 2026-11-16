from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_meetings_endpoint():
    response = client.get("/api/meetings")
    assert response.status_code == 200
    assert "meetings" in response.json()


def test_stats_endpoint():
    response = client.get("/api/meetings/stats")
    assert response.status_code == 200
    assert response.json()["total_meetings"] > 0
