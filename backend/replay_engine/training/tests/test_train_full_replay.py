import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cs2_sim.core.model import SnapshotValueModel

from backend.replay_engine.training.train_full_replay import (
    _load_or_fit_snapshot_model,
    _resolve_release_version,
    _resolve_tick_rate,
)


class FullReplayTrainerTests(unittest.TestCase):
    @staticmethod
    def _row(label: int = 1) -> dict[str, object]:
        return {
            "label_ct_win": label,
            "snapshot": {
                "map_name": "de_mirage",
                "event_type": "kill",
                "ct_alive": 5,
                "t_alive": 4,
                "bomb_planted": False,
                "bomb_site": "none",
                "elapsed_seconds": 10.0,
                "kills_seen": 1,
            },
        }

    def test_existing_small_model_is_loaded_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "small_snapshot_value.json"
            model = SnapshotValueModel()
            model.observe({**self._row()["snapshot"], "label_round_winner": "ct"})
            model.save(path)
            with patch("backend.replay_engine.training.train_full_replay.SnapshotValueModel.save") as save:
                loaded, artifact_path, source = _load_or_fit_snapshot_model(
                    [self._row()],
                    small_model_path=path,
                    small_model_output=path,
                )

        self.assertEqual(source, "loaded")
        self.assertEqual(artifact_path, path)
        self.assertEqual(loaded.global_sample_count(), 1)
        save.assert_not_called()

    def test_missing_small_model_is_fitted_and_written_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "small_snapshot_value.json"
            model, artifact_path, source = _load_or_fit_snapshot_model(
                [self._row()],
                small_model_path=path,
                small_model_output=path,
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(source, "trained")
        self.assertEqual(artifact_path, path)
        self.assertEqual(model.global_sample_count(), 1)
        self.assertEqual(payload["version"], 2)

    def test_tick_rate_and_release_version_are_configurable_or_inferred(self) -> None:
        row = self._row()
        row["snapshot"]["tick_rate"] = 128
        self.assertEqual(_resolve_tick_rate(None, [], [row]), 128.0)
        self.assertEqual(_resolve_tick_rate(32, [128], [row]), 32.0)
        self.assertEqual(
            _resolve_release_version(
                None,
                output_path=Path("artifacts/v7/full_replay_value.txt"),
                manifest_path=None,
            ),
            "v7",
        )
        self.assertEqual(
            _resolve_release_version(
                "release-2026-08",
                output_path=Path("artifacts/v7/full_replay_value.txt"),
                manifest_path=None,
            ),
            "release-2026-08",
        )


if __name__ == "__main__":
    unittest.main()
