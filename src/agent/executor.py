"""
Agent Executor loop and decision moment pipeline processing.
"""

from typing import Dict, Any
from backend.app.orchestration import AnalysisService


class AgentExecutor:
    """Execution engine for processing replay telemetry and running the coaching pipeline."""

    def __init__(self, mode: str = "http"):
        self.mode = mode
        self.service = AnalysisService()

    def execute_replay_coaching(
        self,
        analysis_record: Dict[str, Any],
        player_id: str,
        overrides: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Execute the full agent coaching loop over an extracted analysis record."""
        return self.service.analyze_player(
            analysis_id=analysis_record.get("analysis_id", "default"),
            target_player_id=player_id
        )
