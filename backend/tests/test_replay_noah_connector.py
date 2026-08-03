import unittest
from typing import Any

from backend.app.replay.noah_extractor import (
    NoahExtractorConnector,
    NoahExtractorError,
)
from replay_extractor import ReplayExtractor


class NoahExtractorConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw: dict[str, Any] = {
            "parser": "test",
            "demo_file": "match.dem",
            "header": {"map_name": "de_mirage", "tick_rate": 128},
            "rounds": [{"round_num": 1, "start": 100, "end": 500, "winner": "CT"}],
            "kills": [
                {
                    "round_num": 1,
                    "tick": 220,
                    "attacker_steamid": "attacker",
                    "victim_steamid": "victim",
                }
            ],
            "ticks": [
                {
                    "round_num": 1,
                    "tick": 220,
                    "steamid": "attacker",
                    "team_name": "CT",
                    "X": 512,
                    "Y": 768,
                    "health": 100,
                }
            ],
        }

    def test_normalize_returns_noah_canonical_record_and_segments(self) -> None:
        result = NoahExtractorConnector().normalize(self.raw)

        self.assertEqual(result.replay.metadata.map_name, "de_mirage")
        self.assertEqual(result.replay.metadata.tick_rate, 128)
        self.assertEqual(len(result.replay.events), 1)
        self.assertEqual(len(result.replay.player_ticks), 1)
        self.assertEqual(len(result.segments.heatmap_points), 1)

    def test_missing_source_is_a_stable_connector_error(self) -> None:
        with self.assertRaises(NoahExtractorError) as context:
            NoahExtractorConnector().extract("missing-match.dem")

        self.assertIn("does not exist", str(context.exception))
        self.assertEqual(context.exception.source, "missing-match.dem")

    def test_parse_and_segment_failures_are_wrapped(self) -> None:
        class FailingExtractor(ReplayExtractor):
            def parse(self, path: str) -> Any:
                raise RuntimeError("parser unavailable")

        with self.assertRaises(NoahExtractorError) as context:
            NoahExtractorConnector(extractor=FailingExtractor()).extract(__file__)

        self.assertIn("could not extract replay", str(context.exception))


if __name__ == "__main__":
    unittest.main()
