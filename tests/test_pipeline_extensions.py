import unittest

from cs2_sim.core.model import ActionFrequencyModel, ReplayValueEnsemble, ZoneTransitionModel
from training.calibration import PlattCalibrator
from training.replay_cleaning import CleaningOptions, clean_record
from training.statistical_baselines import GaussianNaiveBayes, LogisticBaseline
from training.infer_actions import infer_actions


class PipelineExtensionTests(unittest.TestCase):
    def test_cleaning_drops_long_round_and_duplicate_player_tick(self) -> None:
        record = {
            "parser": "awpy",
            "demo_file": "sample.dem",
            "header": {"map_name": "de_mirage", "tick_rate": 10},
            "rounds": [{"round_num": 1, "start": 0, "end": 3000, "winner": "ct"}],
            "ticks": [
                {"round_num": 1, "tick": 10, "steamid": "p1", "health": 100},
                {"round_num": 1, "tick": 10, "steamid": "p1", "health": 100},
            ],
        }
        cleaned, report = clean_record(record, options=CleaningOptions(max_round_seconds=180))
        self.assertGreaterEqual(report["warning_count"], 2)
        self.assertEqual(cleaned["rounds"], [])
        self.assertEqual(cleaned["ticks"], [])
        self.assertNotIn("cleaning_version", record)

    def test_baselines_and_calibration_fit(self) -> None:
        features = [[0.0, 0.0], [0.1, 0.2], [1.0, 1.0], [1.1, 0.9]]
        labels = [0, 0, 1, 1]
        gaussian = GaussianNaiveBayes().fit(features, labels)
        logistic = LogisticBaseline(iterations=20).fit(features, labels)
        self.assertGreater(gaussian.predict_probability([1.0, 1.0]), 0.5)
        self.assertGreater(logistic.predict_probability([1.0, 1.0]), 0.5)
        calibrator = PlattCalibrator().fit(logistic.predict(features), labels)
        self.assertEqual(len(calibrator.predict([0.5, 0.8])), 2)

    def test_runtime_and_transition_models_have_safe_fallbacks(self) -> None:
        snapshot = {
            "map_name": "de_mirage",
            "event_type": "tick",
            "ct_alive": 3,
            "t_alive": 2,
            "bomb_planted": False,
            "bomb_site": "none",
            "elapsed_seconds": 20,
            "kills_seen": 1,
            "label_round_winner": "ct",
        }
        ensemble = ReplayValueEnsemble()
        ensemble.bayesian.observe(snapshot)
        prediction = ensemble.predict(snapshot)
        self.assertGreater(prediction.probability, 0.5)
        actions = ActionFrequencyModel()
        actions.observe("ct|A", "hold")
        self.assertEqual(actions.choose_action("ct|A", ["hold", "move"]), "hold")
        transitions = ZoneTransitionModel()
        transitions.observe("A", "MID", side="ct")
        self.assertEqual(transitions.predict_next("A", side="ct"), "MID")

    def test_action_inference_uses_future_window(self) -> None:
        record = {
            "demo_file": "sample.dem",
            "header": {"tick_rate": 10},
            "ticks": [
                {"round_num": 1, "tick": 0, "steamid": "p1", "team_name": "CT", "health": 100, "X": 0, "Y": 0, "last_place_name": "A"},
                {"round_num": 1, "tick": 10, "steamid": "p1", "team_name": "CT", "health": 100, "X": 30, "Y": 0, "last_place_name": "MID"},
            ],
        }
        rows = infer_actions(record, window_seconds=1.0, movement_threshold=20.0)
        self.assertEqual(rows[0]["action"], "move")
        self.assertEqual(rows[0]["next_zone"], "MID")
