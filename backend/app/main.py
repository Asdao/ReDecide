"""FastAPI transports for the frozen API and replay-pipeline integration.

``app`` is the default RE:DECIDE application.  It exposes only the four
endpoints agreed with the frontend and remains fixture-backed until the replay
pipeline emits a frozen ``DecisionPacket``.

``create_app(service=...)`` preserves the incoming replay-job transport for
pipeline integration tests.  That transport returns an internal replay report,
not the frozen packet/card response, so it is deliberately not mounted on the
default application yet.
"""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator

from backend.app.contracts import (
    APIErrorCode,
    APIErrorDetail,
    APIErrorResponse,
    AnalysisPreparationResponse,
    AnalysisResponse,
    AnalyzeJsonRequest,
    AnalyzeRequest,
    HealthResponse,
    SamplesResponse,
)
from backend.app.errors import IntegrationError
from backend.app.coach import PiCoachAdapter
from backend.app.orchestration import (
    AnalysisNotFound,
    AnalysisNotReady,
    AnalysisService,
    FixtureOrchestrator,
    PlayerSelectionError,
)


class PrepareRequest(BaseModel):
    """Internal replay-pipeline request; not a frozen product contract."""

    replay: dict[str, Any] | None = Field(
        default=None, description="Normalized replay JSON object"
    )
    replay_id: str | None = Field(
        default=None, description="Replay artifact created by the Replay API"
    )

    @model_validator(mode="after")
    def require_exactly_one_source(self) -> "PrepareRequest":
        if (self.replay is None) == (self.replay_id is None):
            raise ValueError("provide exactly one of replay or replay_id")
        return self


class PlayerSelectionRequest(BaseModel):
    """Internal replay-pipeline player selection request."""

    player_id: str | None = None
    player_name: str | None = None


def _error_response(
    *,
    code: APIErrorCode,
    message: str,
    retryable: bool,
    status_code: int,
    decision_id: str | None = None,
) -> JSONResponse:
    payload = APIErrorResponse(
        error=APIErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
            decision_id=decision_id,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
    )


def create_fixture_app(
    *, orchestrator: FixtureOrchestrator | None = None
) -> FastAPI:
    """Create the default four-endpoint API backed by frozen fixtures."""

    fixture = orchestrator or FixtureOrchestrator()
    fixture_app = FastAPI(title="RE:DECIDE API", version="0.1.0")
    fixture_app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @fixture_app.exception_handler(IntegrationError)
    async def integration_error_handler(
        _request: Request, error: IntegrationError
    ) -> JSONResponse:
        return _error_response(
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            status_code=error.status_code,
            decision_id=error.decision_id,
        )

    @fixture_app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            code=APIErrorCode.CONTRACT_VALIDATION_FAILED,
            message="Request body does not match the RE:DECIDE API contract",
            retryable=False,
            status_code=422,
        )

    @fixture_app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service="redecide-backend",
            schema_version="1.0",
            mode="fixture",
        )

    @fixture_app.get("/api/samples", response_model=SamplesResponse)
    def samples() -> SamplesResponse:
        return fixture.list_samples()

    @fixture_app.post("/api/analyze", response_model=AnalysisPreparationResponse)
    def analyze(request: AnalyzeRequest) -> AnalysisPreparationResponse:
        """Prepare a neutral fixture packet; never perform coaching here."""

        return fixture.prepare(request)

    @fixture_app.post("/api/analyze-json", response_model=AnalysisResponse)
    def analyze_json(request: AnalyzeJsonRequest) -> AnalysisResponse:
        """Apply fixture coaching only after packet and intent are present."""

        return fixture.analyze_json(request)

    return fixture_app


def create_app(*, service: AnalysisService | None = None) -> FastAPI:
    """Create the internal asynchronous replay-job transport.

    The transport accepts either normalized replay JSON or a ``replay_id``
    created by the upload API. Tests may inject a deterministic service;
    otherwise the live Pi coach adapter is used.
    """

    analysis_app = FastAPI(title="RE:DECIDE Replay Pipeline API", version="1.0")
    analysis = service or AnalysisService(coach_adapter=PiCoachAdapter())

    @analysis_app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @analysis_app.post("/api/analysis/prepare", status_code=202)
    def prepare(request: PrepareRequest) -> dict[str, Any]:
        if request.replay_id:
            from backend.replay_api.store import load_coaching_replay

            try:
                replay = load_coaching_replay(request.replay_id)
            except (FileNotFoundError, ValueError) as exc:
                raise HTTPException(
                    status_code=404,
                    detail="replay coaching artifact not found",
                ) from exc
        elif request.replay is not None:
            replay = request.replay
        else:
            raise HTTPException(status_code=422, detail="replay or replay_id is required")
        if request.replay_id:
            return analysis.prepare(replay, source_replay_id=request.replay_id)
        return analysis.prepare(replay)

    @analysis_app.get("/api/analysis/{analysis_id}")
    def metadata(analysis_id: str) -> dict[str, Any]:
        try:
            return analysis.metadata(analysis_id)
        except AnalysisNotFound as exc:
            raise HTTPException(status_code=404, detail="analysis job not found") from exc

    @analysis_app.get("/api/analysis/{analysis_id}/players")
    def players(analysis_id: str) -> dict[str, Any]:
        try:
            return analysis.players(analysis_id)
        except AnalysisNotFound as exc:
            raise HTTPException(status_code=404, detail="analysis job not found") from exc
        except AnalysisNotReady as exc:
            raise HTTPException(status_code=202, detail=str(exc)) from exc

    @analysis_app.post("/api/analysis/{analysis_id}/run")
    def run(
        analysis_id: str, request: PlayerSelectionRequest
    ) -> dict[str, Any]:
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

    @analysis_app.get("/api/analysis/{analysis_id}/result")
    def result(analysis_id: str) -> dict[str, Any]:
        try:
            return analysis.result(analysis_id)
        except AnalysisNotFound as exc:
            raise HTTPException(status_code=404, detail="analysis job not found") from exc
        except AnalysisNotReady as exc:
            raise HTTPException(status_code=202, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @analysis_app.get(
        "/api/analysis/{analysis_id}/logs", response_class=PlainTextResponse
    )
    def logs(analysis_id: str) -> str:
        try:
            return analysis.logs(analysis_id)
        except AnalysisNotFound as exc:
            raise HTTPException(status_code=404, detail="analysis job not found") from exc

    @analysis_app.get("/api/analysis/{analysis_id}/events")
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
                    event_name = (
                        "complete" if update.get("stage") == "complete" else "log"
                    )
                    yield f"event: {event_name}\ndata: {json.dumps(update)}\n\n"
                state = analysis.metadata(analysis_id)
                if state["status"] in {"complete", "failed"} and index >= len(
                    updates
                ):
                    break
                time.sleep(0.05)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return analysis_app


app = create_fixture_app()

__all__ = ["app", "create_app", "create_fixture_app"]
