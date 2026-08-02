import unittest

from training.extract_features import extract_snapshots


class ExtractorTests(unittest.TestCase):
    def test_extracts_ordered_round_snapshots_and_filters_setup_kills(self) -> None:
        document = {
            "demo_file": "sample.dem",
            "header": {"map_name": "de_mirage", "patch_version": "1"},
            "match": {
                "map_name": "de_mirage",
                "patch_version": "1",
                "tick_rate": 128,
                "teams": [
                    {"side_start": "ct", "players": [{"name": str(i)} for i in range(5)]},
                    {"side_start": "t", "players": [{"name": str(i)} for i in range(5)]},
                ],
            },
            "rounds": [
                {
                    "round_num": 1,
                    "start": 100,
                    "end": 500,
                    "winner": "ct",
                    "bomb_plant": 300,
                    "bomb_site": "bombsite_a",
                }
            ],
            "kills": [
                {
                    "tick": 101,
                    "round_num": 1,
                    "attacker_steamid": "same",
                    "victim_steamid": "same",
                    "attacker_side": "t",
                    "victim_side": "t",
                    "weapon": "world",
                },
                {
                    "tick": 200,
                    "round_num": 1,
                    "attacker_steamid": "t1",
                    "victim_steamid": "ct1",
                    "attacker_side": "t",
                    "victim_side": "ct",
                    "weapon": "ak47",
                    "headshot": True,
                },
            ],
        }
        rows = extract_snapshots(document, "sample.analysis.json")
        self.assertEqual([row["event_type"] for row in rows], ["round_start", "kill", "bomb_plant", "round_end"])
        self.assertEqual(rows[1]["ct_alive"], 4)
        self.assertTrue(rows[2]["bomb_planted"])
        self.assertEqual(rows[-1]["label_round_winner"], "ct")
