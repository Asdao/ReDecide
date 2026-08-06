"""Integration-owned FastAPI gateway for RE:DECIDE.

The exported ``app`` exposes replay upload, asynchronous player analysis, and
the neutral fixture preparation routes through one process. The replay
engine's replay service remains independently testable; this module reuses its
public routes without duplicating its parser, artifact store, or model logic.
"""

from __future__ import annotations

import json
import os
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
from backend.app.coach import HttpCoachAdapter, PiCoachAdapter
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


def create_analysis_app(*, service: AnalysisService | None = None) -> FastAPI:
    """Create the request-contained replay-analysis transport.

    The transport accepts either normalized replay JSON or a ``replay_id``
    created by the upload API. Tests may inject a deterministic service;
    otherwise the live Pi coach adapter is used.
    """

    analysis_app = FastAPI(title="RE:DECIDE Replay Pipeline API", version="1.0")
    analysis = service or AnalysisService(coach_adapter=_default_coach_adapter())

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
    def result(analysis_id: str, player_id: str | None = None) -> dict[str, Any]:
        try:
            return analysis.result(analysis_id, player_id=player_id)
        except AnalysisNotFound as exc:
            raise HTTPException(status_code=404, detail="analysis job not found") from exc
        except AnalysisNotReady as exc:
            raise HTTPException(status_code=202, detail=str(exc)) from exc
        except PlayerSelectionError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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
                if state["status"] in {"ready", "complete", "failed"} and index >= len(
                    updates
                ):
                    break
                time.sleep(0.05)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return analysis_app


def _default_coach_adapter() -> Any:
    """Choose a deployable adapter without changing local Pi behavior."""

    mode = os.getenv("REDECIDE_COACH_MODE", "").strip().lower()
    if mode == "http" or os.getenv("VERCEL") == "1":
        return HttpCoachAdapter()
    return PiCoachAdapter()


def _copy_api_routes(
    target: FastAPI,
    source: FastAPI,
    *,
    prefixes: tuple[str, ...],
    excluded_paths: frozenset[str] = frozenset(),
) -> None:
    """Expose selected teammate-owned routes through the public gateway."""

    for route in source.router.routes:
        path = str(getattr(route, "path", ""))
        if path not in excluded_paths and any(
            path.startswith(prefix) for prefix in prefixes
        ):
            target.router.routes.append(route)


def create_app(
    *,
    service: AnalysisService | None = None,
    orchestrator: FixtureOrchestrator | None = None,
) -> FastAPI:
    """Create the single public API while preserving component ownership.

    Replay routes come from ``backend.replay_api`` unchanged, analysis routes
    come from this module's injected-service factory, and the neutral fixture
    preparation routes remain available as a deterministic fallback. The
    obsolete fixture-only ``POST /api/analyze-json`` route stays available to
    ``create_fixture_app()`` for frozen-contract tests but is deliberately not
    exposed by this public gateway.
    """

    gateway = FastAPI(title="RE:DECIDE API", version="1.0")
    allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "REDECIDE_API_ALLOWED_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    ]
    gateway.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @gateway.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    fixture_app = create_fixture_app(orchestrator=orchestrator)
    analysis_app = create_analysis_app(service=service)

    # Preserve the typed frozen-contract error handlers on the unified app.
    gateway.exception_handlers.update(fixture_app.exception_handlers)

    _copy_api_routes(
        gateway,
        fixture_app,
        prefixes=("/api/samples", "/api/analyze"),
        excluded_paths=frozenset({"/api/analyze-json"}),
    )
    _copy_api_routes(gateway, analysis_app, prefixes=("/api/analysis",))

    # Import lazily to keep the teammate-owned replay service independently
    # importable and to avoid loading its native parser during module import.
    from backend.replay_api.main import create_app as create_replay_app

    replay_app = create_replay_app()
    _copy_api_routes(gateway, replay_app, prefixes=("/api/replay",))

    # Keep Vercel Blob ingestion absent until explicitly enabled. This is safer
    # than commented-out code because the route remains executable and tested.
    from backend.app.blob_import import (
        blob_import_enabled,
        create_blob_import_router,
    )

    if blob_import_enabled():
        gateway.include_router(create_blob_import_router())
    return gateway


app = create_app()

__all__ = ["app", "create_analysis_app", "create_app", "create_fixture_app"]
