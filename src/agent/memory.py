"""
Analysis Memory Store for AI Agent state and replay histories.
"""

from typing import Dict, Any, Optional
from backend.app.analysis_store import (
    load_analysis_state,
    save_analysis_state,
    load_analysis_result,
    save_analysis_result
)


class AnalysisMemoryStore:
    """Agent Memory manager backed by persistent AnalysisStore."""

    def get_analysis(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        return load_analysis_state(analysis_id)

    def save_analysis(self, analysis_id: str, record: Dict[str, Any]) -> None:
        save_analysis_state(analysis_id, record)

    def get_intent_advice(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        return load_analysis_result(analysis_id)

    def save_intent_advice(self, analysis_id: str, advice_record: Dict[str, Any]) -> None:
        save_analysis_result(analysis_id, advice_record)
