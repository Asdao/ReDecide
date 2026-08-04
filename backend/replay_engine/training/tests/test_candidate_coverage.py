import json
import tempfile
import unittest
from pathlib import Path

from backend.replay_engine.training.candidate_coverage import (
    aggregate_candidate_coverage,
    analyze_candidate_coverage,
    load_json_inputs,
)


class CandidateCoverageTests(unittest.TestCase):
    def _report(self) -> dict:
        return {
            "report_type": "combined_replay_analysis",
            "map_name": "de_mirage",
            "config": {"min_support": 5},
            "summary": {"kill_count": 2},
            "full_match": {
                "events": [
                    {
                        "event_id": "event-1",
                        "category": "kill",
                        "round_num": 1,
                        "tick": 64,
                        "attacker_id": "ct1",
                        "victim_id": "t1",
                        "side": "ct",
                    },
                    {
                        "event_id": "event-2",
                        "category": "kill",
                        "round_num": 1,
                        "tick": 128,
                        "attacker_id": "ct2",
                        "victim_id": "t2",
                        "side": "ct",
                    },
                ],
                "event_counts": {"kill": 2},
            },
            "moments": [
                {
                    "round_num": 1,
                    "tick": 64,
                    "decision_tick": 64,
                    "events": [
                        {
                            "event_id": "event-1",
                            "category": "kill",
                            "round_num": 1,
                            "tick": 64,
                            "attacker_id": "ct1",
                            "victim_id": "t1",
                            "side": "ct",
                        }
                    ],
                    "snapshot": {
                        "map_name": "de_mirage",
                        "elapsed_seconds": 1.0,
                        "bomb_planted": 0,
                        "bomb_site": "none",
                        "alive_difference": 1,
                    },
                    "candidate_actions": [
                        {"action": "hold", "sample_count": 10, "supported": True},
                        {"action": "peek", "sample_count": 1, "supported": False},
                    ],
                },
                {
                    "round_num": 1,
                    "tick": 128,
                    "decision_tick": 128,
                    "events": [
                        {
                            "event_id": "event-2",
                            "category": "kill",
                            "round_num": 1,
                            "tick": 128,
                            "attacker_id": "ct2",
                            "victim_id": "t2",
                            "side": "ct",
                        }
                    ],
                    "snapshot": {
                        "map_name": "de_mirage",
                        "elapsed_seconds": 2.0,
                        "bomb_planted": 0,
                        "bomb_site": "none",
                        "alive_difference": 2,
                    },
                    "candidate_actions": [
                        {"action": "hold", "sample_count": 0, "supported": False},
                    ],
                },
            ],
            "kill_analysis": [
                {"event_id": "event-1", "round_num": 1, "tick": 64},
                {"event_id": "event-2", "round_num": 1, "tick": 128},
            ],
        }

    def test_combined_report_counts_rows_and_groups_missing_support(self) -> None:
        result = analyze_candidate_coverage(self._report())

        self.assertEqual(result["total_kills"], 2)
        self.assertEqual(result["analyzed_kills"], 2)
        self.assertEqual(result["candidate_moment_count"], 2)
        self.assertEqual(result["candidate_row_count"], 3)
        self.assertEqual(result["supported_candidate_rows"], 1)
        self.assertEqual(result["unsupported_candidate_rows"], 2)
        self.assertEqual(result["supported_kills"], 0)
        self.assertEqual(result["partially_supported_kills"], 1)
        self.assertEqual(result["unsupported_kills"], 1)
        self.assertEqual(result["supported_kill_rate"], 0.0)

        groups = result["missing_support_by_state"]
        self.assertTrue(
            any(group["reason"] == "support_below_threshold" for group in groups)
        )
        self.assertTrue(any(group["alive_difference"] == "2" for group in groups))
        self.assertTrue(
            all("map" in group and "time_bucket" in group for group in groups)
        )

    def test_canonical_record_reports_unanalysed_kill_dimensions(self) -> None:
        record = {
            "demo_file": "fixture.dem",
            "header": {"map_name": "de_ancient", "tick_rate": 64},
            "kills": [
                {
                    "round_num": 2,
                    "tick": 64,
                    "attacker_steamid": "ct1",
                    "victim_steamid": "t1",
                    "attacker_side": "ct",
                    "weapon": "m4a1",
                }
            ],
            "ticks": [
                {
                    "round_num": 2,
                    "tick": 0,
                    "steamid": "ct1",
                    "side": "ct",
                    "health": 100,
                    "alive": True,
                    "place": "B_SITE",
                },
                {
                    "round_num": 2,
                    "tick": 0,
                    "steamid": "t1",
                    "side": "t",
                    "health": 100,
                    "alive": True,
                    "place": "B_MAIN",
                },
            ],
        }
        result = analyze_candidate_coverage(record)

        self.assertEqual(result["source_kind"], "canonical_replay_record")
        self.assertEqual(result["total_kills"], 1)
        self.assertEqual(result["analyzed_kills"], 0)
        self.assertEqual(result["unanalysed_kills"], 1)
        self.assertEqual(result["candidate_row_count"], 0)
        group = result["missing_support_by_state"][0]
        self.assertEqual(group["reason"], "not_analyzed")
        self.assertEqual(group["map"], "de_ancient")
        self.assertEqual(group["side"], "ct")
        self.assertEqual(group["zone"], "B_SITE")

    def test_jsonl_loading_and_aggregation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coverage.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps(item) for item in [self._report(), self._report()]
                ),
                encoding="utf-8",
            )
            payloads = load_json_inputs(path)
        result = aggregate_candidate_coverage(payloads)
        self.assertEqual(result["input_count"], 2)
        self.assertEqual(result["total_kills"], 4)
        self.assertEqual(result["candidate_row_count"], 6)
        self.assertEqual(result["supported_candidate_rows"], 2)

    def test_candidate_state_report_exposes_extraction_skips(self) -> None:
        result = analyze_candidate_coverage(
            {
                "schema_version": "candidate_state_v1",
                "source": "fixture.dem",
                "summary": {
                    "schema_version": "candidate_state_v1",
                    "kills_seen": 4,
                    "rows_emitted": 3,
                    "kills_skipped": 1,
                    "skip_reasons": {"missing_strict_pre_event_snapshot": 1},
                },
                "rows": [{"schema_version": "candidate_state_v1"}] * 3,
            }
        )
        self.assertEqual(result["source_kind"], "candidate_state_extraction")
        self.assertEqual(result["total_kills"], 4)
        self.assertEqual(result["analyzed_kills"], 3)
        self.assertIsNone(result["supported_kill_rate"])
        self.assertFalse(result["support_applicable"])
        self.assertEqual(
            result["missing_support_by_state"][0]["reason"],
            "missing_strict_pre_event_snapshot",
        )

    def test_player_death_stream_is_counted_once_for_canonical_records(self) -> None:
        record = {
            "events": {
                "player_death": [
                    {
                        "round_num": 1,
                        "tick": 64,
                        "attacker_id": "ct1",
                        "victim_id": "t1",
                    }
                ]
            }
        }
        result = analyze_candidate_coverage(record)
        self.assertEqual(result["total_kills"], 1)


if __name__ == "__main__":
    unittest.main()
