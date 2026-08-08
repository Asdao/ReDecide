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
