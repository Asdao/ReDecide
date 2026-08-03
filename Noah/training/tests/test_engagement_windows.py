import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from Noah.training.build_replay_db import build_database
from Noah.training.engagement_windows import (
    extract_database,
    extract_engagement_windows,
)


class EngagementWindowTests(unittest.TestCase):
    def _record(self):
        return {
            "demo_file": "engagement.dem",
            "source_path": "engagement.dem",
            "header": {"map_name": "de_mirage", "tick_rate": 10},
            "rounds": [{"round_num": 1, "start": 0, "end": 140, "winner": "ct"}],
            "damages": [
                {
                    "round_num": 1,
                    "tick": 100,
                    "attacker_steamid": "t1",
                    "victim_steamid": "ct1",
                    "attacker_side": "t",
                    "victim_side": "ct",
                    "weapon": "ak47",
                    "dmg_health_real": 20,
                    "attacker_health": 100,
                    "victim_health": 80,
                    "distance": 50,
                },
                # Same pair within the engagement horizon; this must not make
                # a second overlapping anchor.
                {
                    "round_num": 1,
                    "tick": 102,
                    "attacker_steamid": "t1",
                    "victim_steamid": "ct1",
                    "attacker_side": "t",
                    "victim_side": "ct",
                    "weapon": "ak47",
                    "dmg_health_real": 10,
                },
            ],
            "kills": [
                {
                    "round_num": 1,
                    "tick": 100,
                    "attacker_steamid": "t1",
                    "victim_steamid": "ct1",
                    "attacker_side": "t",
                    "victim_side": "ct",
                    "weapon": "ak47",
                },
                {
                    "round_num": 1,
                    "tick": 110,
                    "attacker_steamid": "t1",
                    "victim_steamid": "ct1",
                    "attacker_side": "t",
                    "victim_side": "ct",
                    "weapon": "ak47",
                },
                {
                    "round_num": 1,
                    "tick": 112,
                    "attacker_steamid": "ct2",
                    "victim_steamid": "t1",
                    "attacker_side": "ct",
                    "victim_side": "t",
                    "weapon": "m4a1",
                },
            ],
        }

    def test_labels_are_future_only_and_trade_is_detected(self):
        rows = extract_engagement_windows(self._record(), horizon_seconds=5, trade_window_seconds=3)
        self.assertEqual(len(rows), 2)
        by_player = {row["player_id"]: row for row in rows}
        attacker = by_player["t1"]
        victim = by_player["ct1"]
        self.assertTrue(attacker["label_kill"])
        self.assertTrue(attacker["label_death"])
        self.assertFalse(attacker["label_trade"])
        self.assertTrue(victim["label_death"])
        self.assertTrue(victim["label_trade"])
        self.assertFalse(victim["label_kill"])
        self.assertEqual(victim["death_tick"], 110)
        self.assertEqual(victim["trade_tick"], 112)
        self.assertEqual(attacker["label_end_tick"], 140)
        self.assertEqual(attacker["label_cutoff_tick"], 100)
        self.assertEqual(attacker["label_horizon_ticks"], 40)
        self.assertEqual(attacker["label_horizon"]["seconds"], 4.0)
        self.assertTrue(victim["round_won"])
        self.assertFalse(attacker["round_won"])
        self.assertTrue(victim["survived_after_kill"] is None)
        self.assertTrue(attacker["survived_after_kill"] is False)
        self.assertIsNone(attacker["round_value_delta"])
        # The kill at the anchor tick 100 is deliberately excluded.
        self.assertEqual(attacker["kill_tick"], 110)
        self.assertEqual(attacker["features"]["damage_health"], 20.0)

    def test_same_cutoff_kill_does_not_create_positive_label(self):
        record = self._record()
        record["kills"] = [dict(record["kills"][0])]
        rows = extract_engagement_windows(record, horizon_seconds=5)
        self.assertEqual(len(rows), 2)
        self.assertFalse(any(row["label_kill"] for row in rows))
        self.assertFalse(any(row["label_death"] for row in rows))

    def test_value_delta_is_only_filled_by_explicit_predictor(self):
        seen_inputs = []

        def predictor(row):
            seen_inputs.append(row)
            return 0.25 if row["role"] == "attacker" else None

        rows = extract_engagement_windows(
            self._record(),
            horizon_seconds=5,
            round_value_predictor=predictor,
        )
        by_player = {row["player_id"]: row for row in rows}
        self.assertEqual(by_player["t1"]["round_value_delta"], 0.25)
        self.assertIsNone(by_player["ct1"]["round_value_delta"])
        self.assertTrue(seen_inputs)
        self.assertTrue(all("label_kill" not in row and "round_won" not in row for row in seen_inputs))

    def test_database_adapter_reads_existing_event_schema_without_rebuild(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "records.jsonl"
            input_path.write_text(json.dumps(self._record()) + "\n", encoding="utf-8")
            database_path = root / "events.sqlite"
            build_database(input_path, database_path, sample_every=1)
            output_path = root / "engagement.jsonl"
            count = extract_database(database_path, output_path, horizon_seconds=5)
            self.assertEqual(count, 2)
            rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual({row["player_id"] for row in rows}, {"t1", "ct1"})


if __name__ == "__main__":
    unittest.main()
