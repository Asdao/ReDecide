import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Noah.training.test_harness import (
    format_kill_analysis,
    load_replay_record,
    run_replay_test,
)


class TestHarnessInputTests(unittest.TestCase):
    def test_parses_native_demo_through_replacement_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "match.dem"
            path.write_bytes(b"native demo placeholder")
            with patch(
                "Noah.training.replay_extractor_adapter.parse_extractor_demo",
                return_value={"header": {"map_name": "de_mirage"}},
            ) as parse_demo:
                record = load_replay_record(path)
            parse_demo.assert_called_once_with(path)
            self.assertEqual(record["header"]["map_name"], "de_mirage")

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

    def test_formats_per_kill_probability_rows(self) -> None:
        lines = format_kill_analysis(
            {
                "kill_analysis": [
                    {
                        "kill_number": 1,
                        "round_num": 2,
                        "tick": 320,
                        "attacker_id": "t1",
                        "victim_id": "ct1",
                        "weapon": "ak47",
                        "observed_action": "hold",
                        "recommended_action": "peek",
                        "least_death_risk_action": "hold",
                        "least_death_probability": 0.34,
                        "least_death_risk_upper_bound": 0.48,
                        "recommendation_supported": True,
                        "recommendation_sample_count": 12,
                        "recommendation_support_level": "exact",
                        "round_win_probability": 0.62,
                        "round_loss_probability_proxy": 0.38,
                        "probability_of_improvement": 0.84,
                        "probability_decision_class": "good",
                    }
                ]
            }
        )
        self.assertIn("R2 tick 320", lines[1])
        self.assertIn("best_estimate=peek", lines[1])
        self.assertIn("least_death_risk=hold", lines[1])
        self.assertIn("P(death proxy)=34.0%", lines[1])
        self.assertIn("upper=48.0%", lines[1])
        self.assertIn("P(round win)=62.0%", lines[1])
        self.assertIn("P(improvement)=84.0%", lines[1])
        self.assertIn("support=12 (exact, supported)", lines[1])

    def test_candidate_model_override_is_exposed(self) -> None:
        self.assertIn("candidate_model_path", run_replay_test.__annotations__)


if __name__ == "__main__":
    unittest.main()
