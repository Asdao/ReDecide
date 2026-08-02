import unittest

from training.full_features import FULL_FEATURE_NAMES, record_to_event_rows, record_to_rows


class FullFeatureTests(unittest.TestCase):
    def test_tick_rows_include_position_and_round_labels(self) -> None:
        record = {
            "demo_file": "sample.dem",
            "header": {"map_name": "de_mirage", "tick_rate": 128},
            "rounds": [{"round_num": 1, "start": 100, "end": 200, "winner": "CT"}],
            "kills": [],
            "bomb": [],
            "ticks": [
                {"tick": 100, "round_num": 1, "team_name": "CT", "health": 100, "X": 1, "Y": 2},
                {"tick": 100, "round_num": 1, "team_name": "T", "health": 80, "X": 3, "Y": 4},
                {"tick": 132, "round_num": 1, "team_name": "CT", "health": 90, "X": 2, "Y": 3},
                {"tick": 132, "round_num": 1, "team_name": "T", "health": 70, "X": 4, "Y": 5},
            ],
        }
        rows = record_to_rows(record)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["label_ct_win"], 1)
        self.assertEqual(tuple(rows[0]["features"]), FULL_FEATURE_NAMES)
        self.assertEqual(rows[1]["features"]["ct_avg_health"], 90.0)

    def test_sidecar_record_can_create_event_only_rows(self) -> None:
        record = {
            "demo_file": "sample.dem",
            "header": {"map_name": "de_mirage"},
            "match": {"map_name": "de_mirage", "tick_rate": 128, "teams": []},
            "rounds": [
                {
                    "round_num": 1,
                    "start": 100,
                    "end": 200,
                    "winner": "ct",
                    "bomb_plant": None,
                    "bomb_site": "not_planted",
                }
            ],
            "kills": [],
        }
        rows = record_to_event_rows(record)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["label_ct_win"], 1)
        self.assertEqual(rows[0]["features"]["ct_avg_x"], 0.0)
