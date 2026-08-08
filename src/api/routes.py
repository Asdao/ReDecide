"""
FastAPI Agent Router endpoints.
"""

from fastapi import APIRouter, HTTPException
from src.api.schemas import (
    AnalysisRequest,
    IntentAdviceResponse,
    RealtimeTelemetryRequest,
    RealtimeCalloutResponse,
)
from src.agent import CS2IntentAgent
from src.utils.disclosures import get_third_party_disclosures
from src.utils.diagnostics import run_garena_diagnostics

router = APIRouter(prefix="/api/agent", tags=["AI Agent"])
agent_instance = CS2IntentAgent()


@router.post("/analyze", response_model=IntentAdviceResponse)
async def analyze_player_intent(payload: AnalysisRequest):
    """Trigger agent analysis and coaching for a target player replay."""
    try:
        advice = agent_instance.analyze(
            analysis_id=payload.analysis_id,
            player_id=payload.target_player_id
        )
        return IntentAdviceResponse(
            analysis_id=payload.analysis_id,
            target_player_id=payload.target_player_id,
            status="success",
            moments=advice.get("moments", []),
            coaching_summary=advice.get("coaching_summary")
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/realtime-callout", response_model=RealtimeCalloutResponse)
async def realtime_tactical_callout(payload: RealtimeTelemetryRequest):
    """Evaluate real-time in-game telemetry snapshot for immediate tactical HUD callout."""
    try:
        res = agent_instance.realtime_assist(payload.model_dump())
        return RealtimeCalloutResponse(**res)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/disclosures")
async def garena_disclosures():
    """Return third-party component and model disclosures for Garena judging."""
    return get_third_party_disclosures()


@router.get("/diagnostics")
async def garena_diagnostics():
    """Run full system diagnostic audit for Garena AI Build Challenge compliance."""
    return run_garena_diagnostics()
