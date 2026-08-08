"""
Replay moment search and filter tools.
"""

from typing import List, Dict, Any


def query_replay_moments(
    moments: List[Dict[str, Any]],
    min_win_prob_diff: float = 0.05,
    player_id: str = None
) -> List[Dict[str, Any]]:
    """Filter decision moments by win probability impact and actor ID."""
    results = []
    for moment in moments:
        if player_id and moment.get("actor_id") != player_id:
            continue
        prob_diff = abs(moment.get("win_probability_delta", 0.0))
        if prob_diff >= min_win_prob_diff:
            results.append(moment)
    return results
