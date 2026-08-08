"""
Agent prompt construction utilities.
"""

from typing import Dict, Any


def build_decision_prompt(player_name: str, moment_data: Dict[str, Any]) -> str:
    """Build a formatted user prompt for evaluating a player decision moment."""
    zone = moment_data.get("zone", "UNKNOWN")
    choice = moment_data.get("choice_taken", "UNKNOWN")
    win_prob = moment_data.get("win_probability", 0.5)
    return (
        f"Player {player_name} at zone '{zone}' chose action '{choice}'. "
        f"Estimated win probability for this decision state: {win_prob:.2%}. "
        f"Analyze whether this was optimal and explain the tactical recommendation."
    )
