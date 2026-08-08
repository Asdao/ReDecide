"""
Core CS2 Intent Coaching Agent class.
"""

from typing import Dict, Any, Optional
from src.agent.executor import AgentExecutor
from src.agent.memory import AnalysisMemoryStore


class CS2IntentAgent:
    """CS2 Decision Coaching AI Agent."""

    def __init__(self, mode: str = "http"):
        self.memory = AnalysisMemoryStore()
        self.executor = AgentExecutor(mode=mode)

    def analyze(self, analysis_id: str, player_id: str) -> Dict[str, Any]:
        """Analyze a replay session for a given player and generate intent advice."""
        analysis_record = self.memory.get_analysis(analysis_id)
        if not analysis_record:
            raise ValueError(f"Analysis payload not found for ID: {analysis_id}")

        advice = self.executor.execute_replay_coaching(
            analysis_record=analysis_record,
            player_id=player_id
        )

        self.memory.save_intent_advice(analysis_id, advice)
        return advice
