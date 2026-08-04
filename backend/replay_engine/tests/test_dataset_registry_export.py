import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.replay_engine.training.build_replay_db import SCHEMA
from backend.replay_engine.training.dataset_registry import (
    DatasetRecord,
    DatasetRegistry,
    DatasetRegistryError,
)
from backend.replay_engine.training.export_parquet import export_sqlite_to_parquet


class DatasetRegistryExportTests(unittest.TestCase):
    def _database(self, root: Path) -> Path:
        path = root / "replays.sqlite"
        connection = sqlite3.connect(path)
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT INTO matches(match_id,map_name,payload_json) VALUES (?,?,?)",
            ("match-a", "de_mirage", "{}"),
        )
        connection.execute(
            "INSERT INTO replays(replay_id,source_path,demo_file,parser,map_name,tick_rate,tick_count,round_count,checksum,match_id,header_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (1, "private/raw/a.dem", "a.dem", "test", "de_mirage", 64.0, 100, 1, "checksum", "match-a", "{}"),
        )
        features = {"map_code": 1.0, "time_seconds": 3.0, "ct_alive": 4.0}
        connection.execute(
            "INSERT INTO snapshots(snapshot_id,replay_id,round_num,tick,map_name,elapsed_seconds,ct_alive,t_alive,alive_difference,kills_seen,bomb_planted,bomb_site,label_ct_win,features_json,snapshot_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, 1, 1, 10, "de_mirage", 3.0, 4, 3, 1, 0, 0, None, 1, json.dumps(features), json.dumps({"map_name": "de_mirage", "ct_alive": 4, "t_alive": 3})),
        )
        connection.execute(
            "INSERT INTO inferred_actions(action_id,replay_id,round_num,tick,next_tick,player_id,side,current_zone,next_zone,action,horizon_ticks,legal_actions_json,outcome_json,payload_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (1, 1, 1, 10, 20, "p1", "ct", "A", "B", "move", 10, '["hold","move"]', '{"moved":true}', "{}"),
        )
        connection.executemany(
            "INSERT INTO dataset_metadata(key,value) VALUES (?,?)",
            [("schema_version", "2"), ("feature_schema_version", "2"), ("default_tick_rate", "64")],
        )
        connection.commit()
        connection.close()
        return path

    def test_registry_round_trip_and_group_overlap_protection(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            registry = DatasetRegistry(path)
            registry.register(
                DatasetRecord(
                    dataset_id="demo",
                    role="training",
                    visibility="private",
                    path="private:features/demo",
                    groups=("match-a",),
                )
            )
            with self.assertRaises(DatasetRegistryError):
                registry.register(
                    DatasetRecord(
                        dataset_id="demo-holdout",
                        role="validation",
                        visibility="private",
                        path="private:features/holdout",
                        groups=("match-a",),
                    )
                )
            registry.save()
            loaded = DatasetRegistry.load(path)
            self.assertEqual(loaded.records[0].groups, ("match-a",))
            with self.assertRaises(DatasetRegistryError):
                DatasetRecord(
                    dataset_id="bad",
                    role="rejected",
                    visibility="private",
                    path="private:features/bad",
                    groups=("match-b",),
                )

    def test_export_streams_snapshot_and_action_rows_with_metadata(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = self._database(root)
            output = root / "features"
            registry_path = root / "registry.json"
            result = export_sqlite_to_parquet(
                database,
                output,
                dataset_id="replay-v1",
                role="training",
                visibility="private",
                registry_path=registry_path,
                batch_size=1,
            )
            self.assertEqual((result.snapshot_rows, result.action_rows), (1, 1))
            self.assertEqual(result.match_ids, ("match-a",))
            self.assertTrue(result.snapshots_path.is_file())
            self.assertTrue(result.actions_path.is_file())

            from pyarrow import parquet

            snapshots = parquet.read_table(result.snapshots_path)
            actions = parquet.read_table(result.actions_path)
            self.assertEqual(snapshots.column("match_id").to_pylist(), ["match-a"])
            self.assertEqual(actions.column("action").to_pylist(), ["move"])
            self.assertEqual(snapshots.schema.metadata[b"role"], b'"training"')
            self.assertEqual(snapshots.schema.metadata[b"feature_schema_version"], b'"2"')
            registered = DatasetRegistry.load(registry_path)
            self.assertEqual(registered.records[0].rows, {"snapshots": 1, "actions": 1})

    def test_public_export_hides_source_path_but_keeps_stable_hash(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = self._database(root)
            result = export_sqlite_to_parquet(
                database,
                root / "public-features",
                dataset_id="public-v1",
                role="benchmark",
                visibility="public",
            )
            from pyarrow import parquet

            table = parquet.read_table(result.snapshots_path)
            actions = parquet.read_table(result.actions_path)
            self.assertIsNone(table.column("source_path").to_pylist()[0])
            self.assertTrue(table.column("source_hash").to_pylist()[0])
            self.assertNotEqual(actions.column("player_id").to_pylist()[0], "p1")
            self.assertTrue(actions.column("player_id").to_pylist()[0].startswith("player:"))


if __name__ == "__main__":
    unittest.main()
