import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from cs2_sim.core.model import ActionFrequencyModel, ReplayValueEnsemble, ZoneTransitionModel
from training.calibration import PlattCalibrator
from training.replay_cleaning import CleaningOptions, clean_record
from training.statistical_baselines import GaussianNaiveBayes, LogisticBaseline
from training.infer_actions import infer_actions
from training.full_features import record_to_rows
from training.map_regions import NavRegionIndex, RadarTransform
from training.replay_extractor_adapter import normalize_extractor_record


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

    def test_nav_regions_and_radar_transform(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            nav_path = root / "de_test.json"
            nav_path.write_text(
                json.dumps(
                    {
                        "areas": {
                            "1": {
                                "area_id": 1,
                                "corners": [
                                    {"x": 0, "y": 0, "z": 0},
                                    {"x": 100, "y": 0, "z": 0},
                                    {"x": 100, "y": 100, "z": 0},
                                    {"x": 0, "y": 100, "z": 0},
                                ],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            index = NavRegionIndex.from_path(nav_path)
            self.assertEqual(index.lookup(50, 50), "nav_area_1")
            transform = RadarTransform({"de_test": {"pos_x": 0, "pos_y": 100, "scale": 2}})
            self.assertEqual(transform.world_to_radar("de_test", 20, 40), (10.0, 30.0, 0.0))

    def test_replacement_extractor_adapter_is_in_memory_only(self) -> None:
        source = {
                "parser": "replacement",
                "demo_file": "sample.dem",
                "header": {"map_name": "de_mirage", "tick_rate": 10},
                "rounds": [{"round_num": 1, "start": 0, "end": 20, "winner": "ct"}],
                "kills": [{
                    "round_num": 1,
                    "tick": 0,
                    "attacker_steamid": "p1",
                    "victim_steamid": "p2",
                    "weapon": "ak47",
                }],
                "damages": [],
                "bomb": [],
                "events": {"weapon_fire": [{"round_num": 1, "tick": 0, "weapon": "ak47"}]},
                "ticks": [
                    {
                        "round_num": 1,
                        "tick": 0,
                        "steamid": "p1",
                        "team_name": "CT",
                        "X": 10,
                        "Y": 20,
                        "health": 100,
                        "armor": 50,
                    },
                    {
                        "round_num": 1,
                        "tick": 0,
                        "steamid": "p2",
                        "team_name": "T",
                        "X": 100,
                        "Y": 120,
                        "health": 100,
                        "armor": 25,
                    },
                ],
            }
        record = normalize_extractor_record(source)
        self.assertEqual(record["header"]["map_name"], "de_mirage")
        self.assertEqual(record["ticks"][0]["steamid"], "p1")
        self.assertEqual(record["rounds"][0]["winner"], "ct")
        source_rows = record_to_rows(source, sample_every=1, decision_window_seconds=5, include_terminal=False)
        adapted_rows = record_to_rows(record, sample_every=1, decision_window_seconds=5, include_terminal=False)
        self.assertEqual(len(source_rows), len(adapted_rows))
        self.assertEqual([row["features"] for row in source_rows], [row["features"] for row in adapted_rows])
