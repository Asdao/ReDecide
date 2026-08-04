import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from replay_extractor import ExtractorConfig, ReplayExtractor


class ReplayExtractorApiTests(unittest.TestCase):
    def test_facade_normalizes_segments_and_ingests(self) -> None:
        raw = {
            "parser": "test",
            "demo_file": "match.dem",
            "header": {"map_name": "de_mirage", "tick_rate": 128},
            "rounds": [{"round_num": 1, "start": 100, "end": 500, "winner": "CT"}],
            "kills": [{"round_num": 1, "tick": 220, "attacker_steamid": "a", "victim_steamid": "b"}],
            "ticks": [{"round_num": 1, "tick": 220, "steamid": "a", "team_name": "CT", "X": 512, "Y": 768}],
        }
        extractor = ReplayExtractor(ExtractorConfig(heatmap_cell_size=256))
        replay = extractor.normalize(raw)
        segments = extractor.segment(replay)
        self.assertEqual(replay.metadata.map_name, "de_mirage")
        self.assertEqual(segments.heatmap_points[0].cell_x, 2)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "replays.jsonl"
            source.write_text(json.dumps(raw) + "\n", encoding="utf-8")
            result = extractor.ingest(source, root / "vault.sqlite")
            self.assertEqual(result.ingested, 1)
            self.assertEqual(result.stats["replays"], 1)

    def test_parse_uses_marked_sidecar_fallback_when_native_parser_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            demo = root / "match.dem"
            demo.write_bytes(b"not-a-native-demo")
            demo.with_suffix(".analysis.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "demo_file": demo.name,
                        "header": {"map_name": "de_mirage"},
                        "rounds": [],
                        "ticks": [],
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "replay_extractor.api.parse_demo",
                side_effect=RuntimeError("native parser unavailable"),
            ):
                replay = ReplayExtractor().parse(demo)

        self.assertEqual(replay.metadata.parser, "analysis_sidecar")
        self.assertEqual(replay.metadata.map_name, "de_mirage")


if __name__ == "__main__":
    unittest.main()
