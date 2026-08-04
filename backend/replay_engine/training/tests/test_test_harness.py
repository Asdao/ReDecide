import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.replay_engine import analyze_replay
from backend.replay_engine.training.test_harness import (
    format_kill_analysis,
    load_replay_record,
    run_replay_test,
)


class TestHarnessInputTests(unittest.TestCase):
    def test_portable_demo_spec_reproduces_v5_summary(self) -> None:
        repository = Path(__file__).resolve().parents[4]
        spec_path = (
            repository
            / "backend"
            / "replay_engine"
            / "model"
            / "artifacts"
            / "releases"
            / "v5"
            / "replay_model_demo_test.json"
        )
        spec = json.loads(spec_path.read_text(encoding="utf-8"))

        input_path = repository / spec["input"]
        release_dir = repository / spec["release_dir"]
        self.assertFalse(Path(spec["input"]).is_absolute())
        self.assertFalse(Path(spec["release_dir"]).is_absolute())
        self.assertTrue(input_path.is_file())

        runner = spec["runner"]
        report = run_replay_test(
            input_path,
            release_dir=release_dir,
            version=spec["version"],
            moment_threshold=runner["moment_threshold"],
            max_moments=runner["max_moments"],
            sample_every=runner["sample_every"],
        )

        expected = spec["expected"]
        self.assertEqual(report["report_type"], expected["report_type"])
        self.assertEqual(report["schema_version"], expected["report_schema_version"])
        self.assertEqual(report["source"], expected["source"])
        self.assertEqual(report["map_name"], expected["map_name"])
        self.assertEqual(report["summary"], expected["summary"])

    def test_parses_native_demo_through_replacement_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "match.dem"
            path.write_bytes(b"native demo placeholder")
            with patch(
                "backend.replay_engine.training.replay_extractor_adapter.parse_extractor_demo",
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

    def test_normalizes_canonical_extractor_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "extractor.json"
            path.write_text(
                json.dumps(
                    {
                        "metadata": {
                            "map_name": "de_mirage",
                            "tick_rate": 64,
                            "parser": "replacement-extractor",
                        },
                        "rounds": [],
                        "player_ticks": [],
                        "events": [],
                    }
                ),
                encoding="utf-8",
            )
            record = load_replay_record(path)
            self.assertEqual(record["header"]["map_name"], "de_mirage")
            self.assertEqual(record["tick_rate"], 64)

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
        self.assertIn("candidate_model_path", analyze_replay.__annotations__)
        self.assertIn("candidate_model_path", run_replay_test.__annotations__)

    def test_top_level_function_accepts_a_replay_mapping(self) -> None:
        class Runtime:
            def analyse_replay(self, replay, **kwargs):
                return {"replay": replay, "options": kwargs}

        with patch("cs2_sim.ReplayModel.load", return_value=Runtime()) as load:
            result = analyze_replay(
                {"header": {"map_name": "de_mirage"}},
                version="v9",
                max_moments=None,
                sample_every=1,
            )

        self.assertEqual(result["replay"]["header"]["map_name"], "de_mirage")
        self.assertIsNone(result["options"]["max_moments"])
        self.assertEqual(result["options"]["sample_every"], 1)
        self.assertEqual(load.call_args.args[0].version, "v9")

    def test_top_level_function_can_project_outcome_blind_report(self) -> None:
        class Runtime:
            def analyse_replay(self, replay, **kwargs):
                return {
                    "report_type": "combined_replay_analysis",
                    "full_match": {"round_winner": "ct"},
                    "kill_analysis": [{"tick": 20, "victim_id": "p1"}],
                    "summary": {"kill_count": 1, "moment_count": 1},
                    "moments": [
                        {
                            "tick": 20,
                            "decision_tick": 10,
                            "events": [{"category": "kill", "tick": 20}],
                            "engagement_window": {
                                "label_death": True,
                                "death_tick": 20,
                                "health": 34,
                            }
                        }
                    ],
                }

        with patch("cs2_sim.ReplayModel.load", return_value=Runtime()):
            result = analyze_replay(
                {"header": {"map_name": "de_mirage"}},
                outcome_blind=True,
            )

        self.assertTrue(result["outcome_blind"])
        self.assertNotIn("full_match", result)
        self.assertNotIn("kill_analysis", result)
        self.assertNotIn("kill_count", result["summary"])
        self.assertNotIn("moment_count", result["summary"])
        self.assertNotIn("events", result["moments"][0])
        self.assertNotIn("tick", result["moments"][0])
        self.assertNotIn("label_death", result["moments"][0]["engagement_window"])
        self.assertNotIn("death_tick", result["moments"][0]["engagement_window"])
        self.assertEqual(result["moments"][0]["engagement_window"]["health"], 34)

    def test_legacy_runner_delegates_to_top_level_function(self) -> None:
        with patch(
            "backend.replay_engine.training.test_harness.analyze_replay",
            return_value={"summary": {}},
        ) as analyze:
            result = run_replay_test("match.json", version="v8")

        self.assertEqual(result, {"summary": {}})
        analyze.assert_called_once_with(
            "match.json",
            record_index=0,
            release_dir=None,
            version="v8",
            candidate_model_path=None,
            moment_threshold=0.08,
            max_moments=25,
            sample_every=8,
        )


if __name__ == "__main__":
    unittest.main()
