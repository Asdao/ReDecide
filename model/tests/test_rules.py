import unittest

from cs2_sim.actions import ActionType
from cs2_sim.config import SimConfig
from cs2_sim.rules import legal_actions, round_winner
from cs2_sim.state import BombState, GameState, PlayerState, Team


class RulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(
            players={
                "t1": PlayerState("t1", Team.T, "A_SITE", has_bomb=True),
                "ct1": PlayerState("ct1", Team.CT, "A_SITE"),
            },
            bomb_state=BombState.CARRIED,
            bomb_site="A_SITE",
        )

    def test_bomb_carrier_can_plant_at_site(self) -> None:
        self.assertIn(ActionType.PLANT, {a.action_type for a in legal_actions(self.state, "t1")})

    def test_elimination_ends_unplanted_round(self) -> None:
        self.state.players["ct1"].alive = False
        self.assertEqual(round_winner(self.state, SimConfig()), Team.T)

    def test_planted_bomb_can_end_round(self) -> None:
        self.state.bomb_state = BombState.PLANTED
        self.state.bomb_time_remaining = 0
        self.assertEqual(round_winner(self.state, SimConfig()), Team.T)

    def test_ct_can_only_defuse_at_the_bomb_site(self) -> None:
        self.state.bomb_state = BombState.PLANTED
        self.state.bomb_time_remaining = 20
        self.state.players["ct1"].zone = "CT_SPAWN"
        self.assertNotIn(ActionType.DEFUSE, {a.action_type for a in legal_actions(self.state, "ct1")})
