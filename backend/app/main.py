"""FastAPI walking skeleton for the RE:DECIDE integration path."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
from backend.app.orchestration import FixtureOrchestrator


app = FastAPI(title="RE:DECIDE API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

orchestrator = FixtureOrchestrator()


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


@app.exception_handler(IntegrationError)
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


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, _error: RequestValidationError
) -> JSONResponse:
    return _error_response(
        code=APIErrorCode.CONTRACT_VALIDATION_FAILED,
        message="Request body does not match the RE:DECIDE API contract",
        retryable=False,
        status_code=422,
    )


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="redecide-backend",
        schema_version="1.0",
        mode="fixture",
    )


@app.get("/api/samples", response_model=SamplesResponse)
def samples() -> SamplesResponse:
    return orchestrator.list_samples()


@app.post("/api/analyze", response_model=AnalysisPreparationResponse)
def analyze(request: AnalyzeRequest) -> AnalysisPreparationResponse:
    """Prepare a neutral fixture packet; never perform coaching here."""

    return orchestrator.prepare(request)


@app.post("/api/analyze-json", response_model=AnalysisResponse)
def analyze_json(request: AnalyzeJsonRequest) -> AnalysisResponse:
    """Apply the fixture coach only after packet and intent are both present."""

    return orchestrator.analyze_json(request)
