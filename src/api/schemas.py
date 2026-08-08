"""
Pydantic API request and response schemas for agent endpoints.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    analysis_id: str
    target_player_id: str
    overrides: Optional[Dict[str, Any]] = None


class IntentAdviceResponse(BaseModel):
    analysis_id: str
    target_player_id: str
    status: str
    moments: List[Dict[str, Any]] = Field(default_factory=list)
    coaching_summary: Optional[str] = None


class RealtimeTelemetryRequest(BaseModel):
    hp: int = 100
    teammates_alive: int = 1
    enemies_alive: int = 1
    bomb_planted: bool = False
    bomb_time_seconds: float = 40.0
    round_time_seconds: float = 115.0
    active_zone: str = "A_SITE"
    utility_count: int = 0


class RealtimeCalloutResponse(BaseModel):
    tactical_mode: str
    threat_level: str
    callout: str
    recommended_actions: List[str]
    urgency: str
    timestamp_seconds: float
