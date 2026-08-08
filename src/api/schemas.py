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
