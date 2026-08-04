"""FastAPI transport for the two-stage replay analysis job."""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, Field, model_validator

from backend.app.coach import PiCoachAdapter
from backend.app.orchestration import (
    AnalysisNotFound,
    AnalysisNotReady,
    AnalysisService,
    PlayerSelectionError,
)

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import PlainTextResponse, StreamingResponse
except ImportError as exc:  # pragma: no cover - dependency boundary
    raise RuntimeError("FastAPI is required to run backend.app.main; install the backend API dependencies") from exc


class PrepareRequest(BaseModel):
    replay: dict[str, Any] | None = Field(default=None, description="Normalized replay JSON object")
    replay_id: str | None = Field(default=None, description="Replay artifact created by the Replay API")

    @model_validator(mode="after")
    def require_exactly_one_source(self) -> "PrepareRequest":
        if (self.replay is None) == (self.replay_id is None):
            raise ValueError("provide exactly one of replay or replay_id")
        return self


class PlayerSelectionRequest(BaseModel):
    player_id: str | None = None
    player_name: str | None = None


def create_app(*, service: AnalysisService | None = None) -> FastAPI:
    app = FastAPI(title="RE:DECIDE API", version="1.0")
    analysis = service or AnalysisService(coach_adapter=PiCoachAdapter())

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/analysis/prepare", status_code=202)
    def prepare(request: PrepareRequest) -> dict[str, Any]:
        if request.replay_id:
            from backend.replay_api.store import load_coaching_replay

            try:
                replay = load_coaching_replay(request.replay_id)
            except (FileNotFoundError, ValueError) as exc:
                raise HTTPException(status_code=404, detail="replay coaching artifact not found") from exc
        elif request.replay is not None:
            replay = request.replay
        else:
            raise HTTPException(status_code=422, detail="replay or replay_id is required")
        if request.replay_id:
            return analysis.prepare(replay, source_replay_id=request.replay_id)
        return analysis.prepare(replay)

    @app.get("/api/analysis/{analysis_id}")
    def metadata(analysis_id: str) -> dict[str, Any]:
        try:
            return analysis.metadata(analysis_id)
        except AnalysisNotFound as exc:
            raise HTTPException(status_code=404, detail="analysis job not found") from exc

    @app.get("/api/analysis/{analysis_id}/players")
    def players(analysis_id: str) -> dict[str, Any]:
        try:
            return analysis.players(analysis_id)
        except AnalysisNotFound as exc:
            raise HTTPException(status_code=404, detail="analysis job not found") from exc
        except AnalysisNotReady as exc:
            raise HTTPException(status_code=202, detail=str(exc)) from exc

    @app.post("/api/analysis/{analysis_id}/run")
    def run(analysis_id: str, request: PlayerSelectionRequest) -> dict[str, Any]:
        try:
            result = analysis.select_player(
                analysis_id,
                player_id=request.player_id,
                player_name=request.player_name,
            )
            replay_id = analysis.source_replay_id(analysis_id)
            if replay_id:
                from backend.replay_api.store import unlock_visualization

                unlock_visualization(replay_id)
            return result
        except AnalysisNotFound as exc:
            raise HTTPException(status_code=404, detail="analysis job not found") from exc
        except AnalysisNotReady as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PlayerSelectionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/analysis/{analysis_id}/result")
    def result(analysis_id: str) -> dict[str, Any]:
        try:
            return analysis.result(analysis_id)
        except AnalysisNotFound as exc:
            raise HTTPException(status_code=404, detail="analysis job not found") from exc
        except AnalysisNotReady as exc:
            raise HTTPException(status_code=202, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/analysis/{analysis_id}/logs", response_class=PlainTextResponse)
    def logs(analysis_id: str) -> str:
        try:
            return analysis.logs(analysis_id)
        except AnalysisNotFound as exc:
            raise HTTPException(status_code=404, detail="analysis job not found") from exc

    @app.get("/api/analysis/{analysis_id}/events")
    def events(analysis_id: str) -> StreamingResponse:
        try:
            analysis.metadata(analysis_id)
        except AnalysisNotFound as exc:
            raise HTTPException(status_code=404, detail="analysis job not found") from exc

        def stream():
            index = 0
            while True:
                updates = analysis.updates(analysis_id)
                for update in updates[index:]:
                    index += 1
                    event_name = "complete" if update.get("stage") == "complete" else "log"
                    yield f"event: {event_name}\ndata: {json.dumps(update)}\n\n"
                state = analysis.metadata(analysis_id)
                if state["status"] in {"complete", "failed"} and index >= len(updates):
                    break
                time.sleep(0.05)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


app = create_app()

__all__ = ["app", "create_app"]
