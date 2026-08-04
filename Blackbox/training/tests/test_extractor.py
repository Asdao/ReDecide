import unittest

from Blackbox.training.extract_features import extract_snapshots


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

    def test_decision_window_removes_round_end_and_terminal_states(self) -> None:
        document = {
            "match": {"map_name": "de_mirage", "tick_rate": 10, "teams": []},
            "rounds": [{"round_num": 1, "start": 0, "end": 100, "winner": "ct"}],
            "kills": [
                {
                    "tick": 20,
                    "round_num": 1,
                    "attacker_steamid": "ct1",
                    "victim_steamid": "t1",
                    "attacker_side": "ct",
                    "victim_side": "t",
                    "weapon": "m4a1",
                },
                {
                    "tick": 80,
                    "round_num": 1,
                    "attacker_steamid": "ct2",
                    "victim_steamid": "t2",
                    "attacker_side": "ct",
                    "victim_side": "t",
                    "weapon": "m4a1",
                },
            ],
        }
        rows = extract_snapshots(
            document,
            "sample.analysis.json",
            decision_window_seconds=5,
            include_round_start=False,
            include_round_end=False,
            include_terminal=False,
        )
        self.assertEqual([row["tick"] for row in rows], [20])
        self.assertEqual(rows[0]["seconds_since_contact"], 0.0)
