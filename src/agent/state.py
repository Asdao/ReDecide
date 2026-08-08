"""
Agent state definitions and data structures.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class PlayerStateModel(BaseModel):
    player_id: str
    team: str
    zone: str
    hp: int = 100
    has_bomb: bool = False


class DecisionMomentState(BaseModel):
    tick: int
    time_seconds: float
    actor_id: str
    zone: str
    win_probability: float
    choice_taken: str
    optimal_choice: Optional[str] = None
    context_signals: Dict[str, Any] = Field(default_factory=dict)


class AgentState(BaseModel):
    analysis_id: str
    player_id: str
    map_name: str = "de_mirage"
    moments: List[DecisionMomentState] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
