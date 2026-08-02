import unittest
from tempfile import TemporaryDirectory

from cs2_sim.actions import Action, ActionType
from cs2_sim.models import FullLightGBMModel, SmallStatisticalModel
from cs2_sim.state import BombState, GameState, PlayerState, Team


class ModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(
            {
                "t1": PlayerState("t1", Team.T, "MID"),
                "ct1": PlayerState("ct1", Team.CT, "A_SITE"),
            },
            BombState.CARRIED,
        )
        self.legal = (
            Action(ActionType.HOLD),
            Action(ActionType.MOVE_TO_ADJACENT_ZONE, "A_SITE"),
        )

    def test_small_model_prefers_observed_successful_action(self) -> None:
        model = SmallStatisticalModel()
        for _ in range(4):
            model.observe(self.state, "t1", self.legal[1], success=True)
        for _ in range(4):
            model.observe(self.state, "t1", self.legal[0], success=False)
        self.assertEqual(model.choose_action(self.state, "t1", self.legal), self.legal[1])
        self.assertLess(model.normalized_entropy(self.state, "t1", self.legal), 1.0)

    def test_small_model_round_trip(self) -> None:
        model = SmallStatisticalModel()
        model.observe(self.state, "t1", self.legal[1], success=True)
        with TemporaryDirectory() as directory:
            path = f"{directory}/small.json"
            model.save(path)
            loaded = SmallStatisticalModel.load(path)
        self.assertEqual(
            loaded.choose_action(self.state, "t1", self.legal),
            model.choose_action(self.state, "t1", self.legal),
        )

    def test_full_model_falls_back_to_small_model_before_training(self) -> None:
        model = FullLightGBMModel()
        self.assertFalse(model.is_fitted)
        self.assertIn(model.choose_action(self.state, "t1", self.legal), self.legal)

