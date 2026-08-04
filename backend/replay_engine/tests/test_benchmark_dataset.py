import json
import sqlite3
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.replay_engine.training.benchmark_dataset import DemoCandidate, select_unseen_demos, write_benchmark_manifest
from backend.replay_engine.training.evaluate_benchmark import _verify_manifest_overlap


class BenchmarkDatasetTests(unittest.TestCase):
    def _candidate(self, path: str, map_name: str, size: int = 100) -> DemoCandidate:
        return DemoCandidate(path, "new-" + path, map_name, size, 24, 180, 2, date(2026, 1, 1))

    def test_selection_excludes_training_keys_and_respects_budget(self):
        candidates = [
            self._candidate("demos/old.dem", "de_mirage", 100),
            self._candidate("demos/new-a.dem", "de_mirage", 300),
            self._candidate("demos/new-b.dem", "de_nuke", 300),
        ]
        selected = select_unseen_demos(
            candidates,
            excluded_keys={"old.dem", "new-demos/old.dem"},
            max_files=2,
            max_bytes=600,
            seed=3,
        )
        self.assertEqual({item.repo_path for item in selected}, {"demos/new-a.dem", "demos/new-b.dem"})

    def test_manifest_overlap_check_rejects_training_demo(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "training.sqlite"
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE replays(source_path TEXT, demo_file TEXT, match_id TEXT)")
            connection.execute("INSERT INTO replays VALUES (?,?,?)", ("old.dem", "old.dem", "old"))
            connection.commit()
            connection.close()
            output = root / "benchmark"
            demo = output / "demos" / "new.dem"
            demo.parent.mkdir(parents=True)
            demo.write_bytes(b"demo")
            manifest = output / "manifest.json"
            candidate = self._candidate("demos/new.dem", "de_mirage", 4)
            write_benchmark_manifest(
                manifest,
                output_root=output,
                selected=[candidate],
                training_database=database,
            )
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            _verify_manifest_overlap(payload, manifest)
            payload["files"][0]["repo_path"] = "old.dem"
            with self.assertRaises(ValueError):
                _verify_manifest_overlap(payload, manifest)


if __name__ == "__main__":
    unittest.main()
