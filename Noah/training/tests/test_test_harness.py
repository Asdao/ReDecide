import json
import tempfile
import unittest
from pathlib import Path

from Noah.training.test_harness import load_replay_record


class TestHarnessInputTests(unittest.TestCase):
    def test_loads_single_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.json"
            path.write_text(json.dumps({"header": {"map_name": "de_mirage"}}), encoding="utf-8")
            self.assertEqual(load_replay_record(path)["header"]["map_name"], "de_mirage")

    def test_selects_jsonl_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replays.jsonl"
            path.write_text(
                "\n".join(json.dumps({"index": index}) for index in range(2)),
                encoding="utf-8",
            )
            self.assertEqual(load_replay_record(path, record_index=1)["index"], 1)

    def test_rejects_missing_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replays.jsonl"
            path.write_text(json.dumps({"index": 0}), encoding="utf-8")
            with self.assertRaises(IndexError):
                load_replay_record(path, record_index=1)


if __name__ == "__main__":
    unittest.main()
