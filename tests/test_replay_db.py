import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from training.build_replay_db import build_database


class ReplayDatabaseTests(unittest.TestCase):
    def test_builds_queryable_replay_round_and_snapshot_tables(self) -> None:
        record = {
            "parser": "awpy",
            "demo_file": "sample.dem",
            "header": {"map_name": "de_mirage", "tick_rate": 10},
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
                }
            ],
            "bomb": [],
            "ticks": [
                {"tick": 20, "round_num": 1, "team_name": "CT", "health": 100, "X": 1, "Y": 2},
                {"tick": 20, "round_num": 1, "team_name": "T", "health": 100, "X": 3, "Y": 4},
            ],
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "records.jsonl"
            input_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            database_path = root / "replays.sqlite"
            stats = build_database(input_path, database_path, sample_every=1)
            self.assertEqual(stats["replays"], 1)
            connection = sqlite3.connect(database_path)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM replays").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM rounds").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 1)
            finally:
                connection.close()
