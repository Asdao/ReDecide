"""
Unit and integration tests for AI Agent core.
"""

import pytest
from src.agent import CS2IntentAgent
from src.agent.state import AgentState, DecisionMomentState


def test_agent_state_initialization():
    state = AgentState(
        analysis_id="test_001",
        player_id="player_a",
        map_name="de_mirage"
    )
    assert state.analysis_id == "test_001"
    assert state.player_id == "player_a"
    assert len(state.moments) == 0


def test_decision_moment_state():
    moment = DecisionMomentState(
        tick=1280,
        time_seconds=20.5,
        actor_id="player_a",
        zone="A_SITE",
        win_probability=0.65,
        choice_taken="RETREAT"
    )
    assert moment.tick == 1280
    assert moment.win_probability == 0.65
    assert moment.choice_taken == "RETREAT"


def test_realtime_assist():
    agent = CS2IntentAgent()
    telemetry = {
        "hp": 25,
        "teammates_alive": 1,
        "enemies_alive": 2,
        "bomb_planted": True,
        "bomb_time_seconds": 12.0,
        "round_time_seconds": 35.0,
        "active_zone": "A_SITE",
        "utility_count": 1,
    }
    res = agent.realtime_assist(telemetry)
    assert res["tactical_mode"] == "CLUTCH_1v2"
    assert res["threat_level"] == "CRITICAL"
    assert "CLUTCH_1v2" in res["callout"]
    assert res["urgency"] == "HIGH"
