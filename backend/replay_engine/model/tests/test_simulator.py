import unittest

from cs2_sim.actions import ActionType
from cs2_sim.baseline_policy import BaselinePolicy
from cs2_sim.config import SimConfig
from cs2_sim.simulator import Simulator
from cs2_sim.state import BombState, GameState, PlayerState, Team


class MovePolicy:
    def choose_action(self, state, player_id, legal):
        for action in legal:
            if action.target_zone is not None:
                return action
        return legal[0]


class RelocatingDefusePolicy:
    def choose_action(self, state, player_id, legal):
        for action in legal:
            if action.action_type is ActionType.DEFUSE:
                state.player(player_id).zone = "CT_SPAWN"
                return action
        return legal[0]


def planted_state() -> GameState:
    return GameState(
        players={
            "t1": PlayerState("t1", Team.T, "A_MAIN"),
            "ct1": PlayerState("ct1", Team.CT, "A_SITE"),
        },
        bomb_state=BombState.PLANTED,
        bomb_site="A_SITE",
        bomb_time_remaining=20.0,
    )


class SimulatorTests(unittest.TestCase):
    def test_ct_can_finish_a_defuse(self) -> None:
        result = Simulator(SimConfig(), BaselinePolicy(seed=3)).run(planted_state())
        self.assertEqual(result.winner, Team.CT)
        self.assertTrue(any(event.kind == "action_completed" for event in result.events))

    def test_seeded_runs_are_reproducible(self) -> None:
        state = planted_state()
        first = Simulator(SimConfig(), BaselinePolicy(seed=9)).run(state)
        second = Simulator(SimConfig(), BaselinePolicy(seed=9)).run(state)
        self.assertEqual(first.winner, second.winner)
        self.assertEqual(first.events, second.events)

    def test_bomb_expires_before_a_late_defuse(self) -> None:
        state = planted_state()
        state.bomb_time_remaining = 0.1
        result = Simulator(SimConfig(), BaselinePolicy(seed=3)).run(state)
        self.assertEqual(result.winner, Team.T)

    def test_defuse_is_revalidated_when_action_completes(self) -> None:
        state = planted_state()
        result = Simulator(SimConfig(), RelocatingDefusePolicy()).run(state)
        self.assertEqual(result.winner, Team.T)
        self.assertTrue(any(event.kind == "action_rejected" for event in result.events))

    def test_visible_enemy_interrupts_movement(self) -> None:
        state = planted_state()
        state.players["t1"].visible_enemies.add("ct1")
        result = Simulator(SimConfig(), MovePolicy()).run(state)
        self.assertTrue(any(event.kind == "action_interrupted" for event in result.events))
