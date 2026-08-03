import unittest
from pathlib import Path
from typing import Any

from backend.app.coach.noah_connector import NoahCoachConnector, NoahCoachError


class _FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def analyse_replay(self, replay: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        self.calls.append((replay, kwargs))
        return {
            "report_type": "combined_replay_analysis",
            "schema_version": "replay_analysis_v1",
            "moments": [],
            "summary": {"moment_count": 0},
        }


class NoahCoachConnectorTests(unittest.TestCase):
    def test_forwards_normalized_replay_to_deployed_runtime(self) -> None:
        runtime = _FakeRuntime()
        connector = NoahCoachConnector(runtime=runtime)
        replay = {"header": {"map_name": "de_mirage"}, "rounds": [], "ticks": []}

        report = connector.analyse(replay, max_moments=3)

        self.assertEqual(report["report_type"], "combined_replay_analysis")
        self.assertEqual(runtime.calls, [(replay, {"max_moments": 3})])

    def test_accepts_json_payload_and_alias(self) -> None:
        runtime = _FakeRuntime()
        connector = NoahCoachConnector(runtime=runtime)

        report = connector.analyse_json('{"header": {}, "rounds": [], "ticks": []}')

        self.assertEqual(report["summary"]["moment_count"], 0)

    def test_rejects_invalid_input_and_runtime_reports(self) -> None:
        connector = NoahCoachConnector(runtime=_FakeRuntime())
        with self.assertRaises(NoahCoachError):
            connector.analyse([])  # type: ignore[arg-type]
        with self.assertRaises(NoahCoachError):
            connector.analyse_json("not-json")

    def test_runtime_and_config_are_mutually_exclusive(self) -> None:
        with self.assertRaises(ValueError):
            NoahCoachConnector(runtime=_FakeRuntime(), model_config=object())

    def test_checked_in_fixture_flows_through_real_connector(self) -> None:
        """Exercise the same JSON-shaped payload that the backend receives."""

        fixture = Path(__file__).parent / "fixtures" / "coach_replay.json"
        payload = fixture.read_text(encoding="utf-8")

        report = NoahCoachConnector().analyse_json(
            payload,
            max_moments=2,
            posterior_samples=100,
            posterior_seed=7,
        )

        self.assertEqual(report["report_type"], "combined_replay_analysis")
        self.assertIn("probability_label_schema_version", report)
        self.assertIn("probability_decision_classes", report["summary"])
        self.assertGreaterEqual(report["summary"]["moment_count"], 0)

    def test_full_fixture_keeps_every_kill_in_report_and_moments(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "coach_full_replay.json"
        payload = fixture.read_text(encoding="utf-8")

        report = NoahCoachConnector().analyse_json(
            payload,
            max_moments=None,
            sample_every=1,
            posterior_samples=100,
            posterior_seed=7,
        )

        self.assertEqual(report["full_match"]["event_counts"]["kill"], 4)
        self.assertEqual(report["summary"]["moment_count"], 4)
        kill_moments = [
            event
            for moment in report["moments"]
            for event in moment["events"]
            if event["category"] == "kill"
        ]
        self.assertEqual(len(kill_moments), 4)
        self.assertEqual(
            {event["tick"] for event in kill_moments},
            {64, 128, 320, 384},
        )
        self.assertEqual(len(report["kill_analysis"]), 4)
        self.assertIn(
            report["kill_analysis"][0]["recommended_action"],
            {"hold", "move", "peek", "move_to_adjacent_zone"},
        )
        self.assertIn("round_win_probability", report["kill_analysis"][0])


if __name__ == "__main__":
    unittest.main()
