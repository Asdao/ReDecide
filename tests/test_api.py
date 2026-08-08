"""
Unit tests for FastAPI Agent API routes.
"""

from fastapi.testclient import TestClient
from fastapi import FastAPI
from src.api.routes import router

app = FastAPI()
app.include_router(router)

client = TestClient(app)


def test_agent_api_router_exists():
    assert router.prefix == "/api/agent"


def test_realtime_callout_endpoint():
    payload = {
        "hp": 80,
        "teammates_alive": 3,
        "enemies_alive": 2,
        "bomb_planted": False,
        "active_zone": "B_SITE",
        "utility_count": 2,
    }
    response = client.post("/api/agent/realtime-callout", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "tactical_mode" in data
    assert "callout" in data
    assert "recommended_actions" in data
