import json
import tempfile
import unittest
from pathlib import Path

from Blackbox.training.data_paths import DataPaths
from Blackbox.training.migrate_data_layout import migrate


class DataLayoutTests(unittest.TestCase):
    def test_migration_is_non_overwriting_and_rewrites_public_benchmark_refs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / "public"
            private = root / "private"
            paths = DataPaths(public=public, private=private)

            (root / "data/full/processed").mkdir(parents=True)
            (root / "data/full/processed/cs2_replays_v2.sqlite").write_bytes(b"db")
            (root / "data/benchmark/demos/match").mkdir(parents=True)
            (root / "data/benchmark/demos/match/demo.dem").write_bytes(b"demo")
            (root / "data/benchmark/manifest.json").write_text(
                json.dumps({
                    "type": "held_out_native_demo_benchmark",
                    "training_database": "old.db",
                    "files": [{"local_path": "demos/match/demo.dem"}],
                }),
                encoding="utf-8",
            )

            statuses = migrate(root, apply=True, paths=paths)

            self.assertTrue((private / "databases/cs2_replays_v2.sqlite").is_file())
            manifest = json.loads((public / "benchmark_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["training_database"], "private:databases/cs2_replays_v2.sqlite")
            self.assertEqual(
                manifest["files"][0]["local_path"],
                "private:benchmark_cache/demos/match/demo.dem",
            )
            self.assertTrue((public / "layout_manifest.json").is_file())
            self.assertTrue(any(item["status"] == "moved" for item in statuses))

    def test_migration_refuses_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / "public"
            private = root / "private"
            paths = DataPaths(public=public, private=private)
            source = root / "data/maps"
            source.mkdir(parents=True)
            (source / "manifest.json").write_text("{}", encoding="utf-8")
            paths.public_maps.mkdir(parents=True)
            with self.assertRaises(FileExistsError):
                migrate(root, apply=False, paths=paths)


if __name__ == "__main__":
    unittest.main()
