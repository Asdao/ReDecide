import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from training.parse_demos import parse_directory, sidecar_record


class DemoParserTests(unittest.TestCase):
    def test_sidecar_fallback_is_marked(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sample.analysis.json"
            path.write_text(json.dumps({"demo_file": "sample.dem"}), encoding="utf-8")
            record = sidecar_record(path)
        self.assertEqual(record["parser"], "analysis_sidecar")

    def test_directory_falls_back_to_sidecar_when_binary_backend_unavailable(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.dem").write_bytes(b"not-a-real-demo")
            (root / "sample.analysis.json").write_text(
                json.dumps({"demo_file": "sample.dem"}), encoding="utf-8"
            )
            output = root / "out.jsonl"
            parsed, fallback = parse_directory(root, output)
            self.assertEqual((parsed, fallback), (1, 1))
            self.assertEqual(json.loads(output.read_text())["parser"], "analysis_sidecar")

