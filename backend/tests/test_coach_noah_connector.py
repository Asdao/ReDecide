import unittest
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


if __name__ == "__main__":
    unittest.main()
