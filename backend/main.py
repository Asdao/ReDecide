"""Vercel Services entrypoint for the unified FastAPI gateway."""

from backend.app.main import app

__all__ = ["app"]
