import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from training import TrainingConfig, TrainingError, TrainingPipeline


class TrainingPipelineApiTests(unittest.TestCase):
    def test_facade_builds_database_with_shared_configuration(self) -> None:
        config = TrainingConfig(sample_every=8, decision_window_seconds=4.0, action_window_seconds=1.5)
        pipeline = TrainingPipeline(config)
        with patch("training.api.build_database", return_value={"replays": 3}) as build:
            result = pipeline.prepare_database("input.jsonl", "replays.sqlite", replace=True)
        self.assertEqual(result.counts["replays"], 3)
        build.assert_called_once_with(
            Path("input.jsonl"),
            Path("replays.sqlite"),
            sample_every=8,
            decision_window_seconds=4.0,
            action_window_seconds=1.5,
            replace=True,
            clean=False,
        )

    def test_facade_returns_stable_replay_artifact_paths(self) -> None:
        with TemporaryDirectory() as directory:
            pipeline = TrainingPipeline(TrainingConfig(artifact_dir=Path(directory)))
            with patch("training.api.train_replay_value") as train:
                artifacts = pipeline.train_replay_model("replays.sqlite")
            self.assertEqual(artifacts.manifest, Path(directory) / "full_replay_value.manifest.json")
            self.assertEqual(artifacts.bayesian, Path(directory) / "small_snapshot_value.json")
            self.assertEqual(train.call_count, 1)

    def test_facade_exposes_one_public_error_type(self) -> None:
        pipeline = TrainingPipeline()
        with patch("training.api.build_database", side_effect=ValueError("bad input")):
            with self.assertRaises(TrainingError):
                pipeline.prepare_database("bad.jsonl", "replays.sqlite")


if __name__ == "__main__":
    unittest.main()
