import unittest
from tempfile import TemporaryDirectory

from cs2_sim.actions import Action, ActionType
from cs2_sim.core.model import (
    FullLightGBMModel,
    SmallStatisticalModel,
    SnapshotValueModel,
    TrainingExample,
)
from cs2_sim.models import SnapshotValueModel as LegacySnapshotValueModel
from cs2_sim.state import BombState, GameState, PlayerState, Team

from Noah.training.train_models import small_decision_metrics


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

    def test_small_model_backs_off_for_unseen_exact_state(self) -> None:
        model = SmallStatisticalModel()
        for _ in range(6):
            model.observe(self.state, "t1", self.legal[1], success=True)

        unseen = GameState(
            {
                "t1": PlayerState("t1", Team.T, "MID"),
                "ct1": PlayerState("ct1", Team.CT, "A_SITE", alive=False, health=0),
            },
            BombState.CARRIED,
        )
        support = model.action_support_info(unseen, "t1")

        self.assertEqual(support["level"], "backoff")
        self.assertGreater(support["support"], 0)
        self.assertIn(model.choose_action(unseen, "t1", self.legal), self.legal)

    def test_full_model_falls_back_to_small_model_before_training(self) -> None:
        model = FullLightGBMModel()
        self.assertFalse(model.is_fitted)
        self.assertIn(model.choose_action(self.state, "t1", self.legal), self.legal)

    def test_snapshot_value_model_uses_ct_and_t_labels(self) -> None:
        model = SnapshotValueModel()
        snapshot = {
            "map_name": "de_mirage",
            "event_type": "kill",
            "ct_alive": 3,
            "t_alive": 2,
            "bomb_planted": False,
            "bomb_site": None,
            "elapsed_seconds": 30,
            "kills_seen": 3,
            "label_round_winner": "ct",
        }
        model.observe(snapshot)
        self.assertEqual(model.sample_count(snapshot), 1)
        self.assertGreater(model.predict_ct_win(snapshot), 0.5)

    def test_legacy_model_import_path_is_compatible(self) -> None:
        self.assertIs(SnapshotValueModel, LegacySnapshotValueModel)

    def test_snapshot_model_backs_off_for_an_unseen_exact_state(self) -> None:
        model = SnapshotValueModel()
        observed = {
            "map_name": "de_mirage",
            "event_type": "kill",
            "ct_alive": 5,
            "t_alive": 4,
            "bomb_planted": False,
            "elapsed_seconds": 40,
            "kills_seen": 1,
            "label_round_winner": "ct",
        }
        for _ in range(20):
            model.observe(observed)
        unseen = dict(observed, event_type="bomb_plant", bomb_site="bombsite_a")
        self.assertEqual(model.sample_count(unseen), 0)
        self.assertGreater(model.predict_ct_win(unseen), 0.5)

    def test_small_decision_metrics_compare_with_simulator_labels(self) -> None:
        model = SmallStatisticalModel()
        model.observe(self.state, "t1", self.legal[0], success=False)
        model.observe(self.state, "t1", self.legal[1], success=True)
        group = [
            TrainingExample(self.state, "t1", self.legal[0], False),
            TrainingExample(self.state, "t1", self.legal[1], True),
        ]
        metrics = small_decision_metrics(model, [group], seed=7)
        self.assertEqual(metrics["legal_action_rate"], 1.0)
        self.assertEqual(metrics["oracle_opportunity_accuracy"], 1.0)
