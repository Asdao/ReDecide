"""
FastAPI Agent Router endpoints.
"""

from fastapi import APIRouter, HTTPException
from src.api.schemas import AnalysisRequest, IntentAdviceResponse
from src.agent import CS2IntentAgent

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
