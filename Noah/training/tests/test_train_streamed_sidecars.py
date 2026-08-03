import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Noah.training.train_streamed_sidecars import train_from_stream


class TrainStreamedSidecarsTests(unittest.TestCase):
    def test_orchestrates_stream_snapshot_and_full_training(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch(
                    "Noah.training.train_streamed_sidecars.select_and_stream",
                    return_value={"files_processed": 2, "snapshot_rows": 8},
                ) as stream,
                patch("Noah.training.train_streamed_sidecars.train_snapshot_model") as small,
                patch("Noah.training.train_streamed_sidecars.train_full_replay") as full,
            ):
                result = train_from_stream(
                    metadata_dir=root / "metadata",
                    snapshot_output=root / "snapshots.jsonl",
                    release_dir=root / "release",
                    max_files=2,
                    max_bytes=100,
                )

        stream.assert_called_once()
        small.assert_called_once()
        full.assert_called_once()
        self.assertEqual(result["stream"]["snapshot_rows"], 8)
        self.assertEqual(result["release_dir"], str(root / "release"))
        self.assertIsNone(result["calibrator"])
        self.assertIn("replay-value models only", result["note"])


if __name__ == "__main__":
    unittest.main()
