import sqlite3
import tempfile
import unittest
from pathlib import Path

from replay_extractor.normalize import normalize_record
from replay_extractor.repository import ReplayRepository
from replay_extractor.segmenter import events_for_round, segment_replay


class ReplayExtractorTests(unittest.TestCase):
    def test_normalizes_and_segments_events_ticks_and_heatmap_points(self) -> None:
        record = normalize_record({
            "parser": "test",
            "demo_file": "match.dem",
            "header": {"map_name": "de_mirage", "tick_rate": 128},
            "rounds": [{"round_num": 1, "start": 100, "end": 500, "winner": "CT"}],
            "kills": [{"round_num": 1, "tick": 220, "attacker_steamid": "a", "victim_steamid": "b"}],
            "ticks": [{"round_num": 1, "tick": 220, "steamid": "a", "team_name": "CT", "X": 512, "Y": 768, "health": 100}],
        })
        segments = segment_replay(record, heatmap_cell_size=256)
        self.assertEqual(record.metadata.map_name, "de_mirage")
        self.assertEqual(len(events_for_round(segments, 1)), 1)
        self.assertEqual(segments.heatmap_points[0].cell_x, 2)
        self.assertEqual(segments.heatmap_points[0].cell_y, 3)

    def test_repository_writes_queryable_projection(self) -> None:
        record = normalize_record({"demo_file": "match.dem", "header": {"map_name": "de_inferno"}})
        segments = segment_replay(record)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vault.sqlite"
            repository = ReplayRepository(path)
            repository.write(segments)
            self.assertEqual(repository.stats()["replays"], 1)
            repository.close()
            connection = sqlite3.connect(path)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM replays").fetchone()[0], 1)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
