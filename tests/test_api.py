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
