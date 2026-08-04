import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from Blackbox.training.sidecar_catalog import SidecarCandidate
from Blackbox.training.stream_sidecars import stream_sidecars_to_snapshots


class StreamSidecarTests(unittest.TestCase):
    @staticmethod
    def _candidate() -> SidecarCandidate:
        return SidecarCandidate(
            repo_path="data/mirage/match.analysis.json",
            map_name="de_mirage",
            rounds=24,
            kills=120,
            stars=1,
            match_date=date(2025, 1, 1),
            size=100,
        )

    @staticmethod
    def _document() -> dict[str, object]:
        return {
            "demo_file": "match.dem",
            "match": {
                "map_name": "de_mirage",
                "tick_rate": 64,
                "teams": [
                    {"side_start": "ct", "players": [{"name": f"ct{index}"} for index in range(5)]},
                    {"side_start": "t", "players": [{"name": f"t{index}"} for index in range(5)]},
                ],
            },
            "rounds": [
                {"round_num": 1, "start": 0, "end": 512, "winner": "ct"},
            ],
            "kills": [
                {
                    "round_num": 1,
                    "tick": 64,
                    "attacker_steamid": "ct1",
                    "victim_steamid": "t1",
                    "attacker_side": "ct",
                    "victim_side": "t",
                    "weapon": "m4a1",
                }
            ],
        }

    def test_streams_one_sidecar_into_compact_jsonl(self) -> None:
        payload = json.dumps(self._document()).encode()

        def fetcher(repo_path, **kwargs):
            self.assertEqual(repo_path, "data/mirage/match.analysis.json")
            yield payload

        with TemporaryDirectory() as directory:
            output = Path(directory) / "snapshots.jsonl"
            result = stream_sidecars_to_snapshots(
                [self._candidate()],
                output,
                max_bytes=1000,
                fetcher=fetcher,
            )
            rows = [json.loads(line) for line in output.read_text().splitlines()]

        self.assertEqual(result["files_processed"], 1)
        self.assertEqual(result["snapshot_rows"], 1)
        self.assertEqual(rows[0]["map_name"], "de_mirage")
        self.assertEqual(rows[0]["event_type"], "kill")

    def test_cache_is_optional(self) -> None:
        payload = json.dumps(self._document()).encode()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "snapshots.jsonl"
            cache = root / "cache"
            stream_sidecars_to_snapshots(
                [self._candidate()],
                output,
                max_bytes=1000,
                cache_dir=cache,
                fetcher=lambda _repo_path, **_kwargs: iter((payload,)),
            )
            self.assertTrue((cache / "data" / "mirage" / "match.analysis.json").is_file())


if __name__ == "__main__":
    unittest.main()
