"""
Unit tests for AI Agent tools.
"""

from src.tools.cs2_simulator import run_cs2_simulation
from src.tools.search import query_replay_moments
from cs2_sim import SimConfig
from cs2_sim.simulator import Simulator
from cs2_sim.baseline_policy import BaselinePolicy
from cs2_sim.state import GameState, PlayerState, BombState, Team


def test_cs2_simulator_tool():
    players = {
        "t1": PlayerState("t1", Team.T, zone="A_SITE", has_bomb=True),
        "ct1": PlayerState("ct1", Team.CT, zone="CT_SPAWN"),
    }
    state = GameState(players=players, bomb_state=BombState.CARRIED, bomb_site="A_SITE")
    result = run_cs2_simulation(state, seed=42)
    assert "winner" in result
    assert "events" in result
    assert isinstance(result["events"], list)


def test_query_replay_moments():
    moments = [
        {"actor_id": "p1", "win_probability_delta": 0.12},
        {"actor_id": "p2", "win_probability_delta": 0.02},
        {"actor_id": "p1", "win_probability_delta": -0.08},
    ]
    filtered = query_replay_moments(moments, min_win_prob_diff=0.05, player_id="p1")
    assert len(filtered) == 2
    assert all(m["actor_id"] == "p1" for m in filtered)
