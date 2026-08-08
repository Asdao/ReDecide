"""
Core CS2 Intent Coaching Agent class.
"""

from typing import Dict, Any, Optional
from src.agent.executor import AgentExecutor
from src.agent.memory import AnalysisMemoryStore
from backend.app.coach.intent_engine import IntentCoachingEngine


class CS2IntentAgent:
    """CS2 Decision Coaching AI Agent."""

    def __init__(self, mode: str = "http"):
        self.memory = AnalysisMemoryStore()
        self.executor = AgentExecutor(mode=mode)
        self.intent_engine = IntentCoachingEngine()

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

    def realtime_assist(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate real-time in-game telemetry snapshot for instant tactical callout."""
        return self.intent_engine.evaluate_realtime_assist(telemetry)
