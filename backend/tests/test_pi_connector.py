from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import httpx

from backend.app.coach.pi_connector import (
    MAX_KNOWN_EVENTS_PER_DECISION,
    MAX_PROMPT_BYTES,
    HttpCoachAdapter,
    PiCoachAdapter,
    PiCoachError,
    PiCoachTimeoutError,
    build_coach_prompt,
)


def _pipeline_result() -> dict:
    return {
        "selected_decision": {
            "decision_id": "r1:psteam-secret:t164",
            "round_number": 1,
            "player_id": "steam-secret",
            "display_name": "Secret Name",
            "side": "t",
            "role": "attacker",
            "event_category": "damage",
            "decision_open_tick": 164,
            "contact_tick": 164,
            "action_close_tick": 324,
            "opponent_id": "opponent-secret",
            "observed_action": "hold",
            "observed_action_confidence": 0.88,
            "evidence": ["displacement_below_threshold"],
        },
        "key_events": [
            {
                "event_id": "real-event-id",
                "event_type": "damage",
                "key_event_type": "first_damage_contact",
                "round_number": 1,
                "tick": 164,
                "participant_ids": ["steam-secret", "opponent-secret"],
                "is_coaching_anchor": True,
            },
            {
                "event_id": "future-event-id",
                "event_type": "kill",
                "round_number": 1,
                "tick": 400,
                "participant_ids": ["steam-secret", "opponent-secret"],
                "is_coaching_anchor": False,
            },
        ],
        "win_estimator": {
            "timeline": [
                {"tick": 100, "ct_probability": 0.55, "t_probability": 0.45, "uncertainty": 0.1},
                {"tick": 200, "ct_probability": 0.7, "t_probability": 0.3, "uncertainty": 0.2},
            ]
        },
    }


class PiCoachAdapterTests(unittest.TestCase):
    def test_prompt_is_anonymized_and_stops_at_the_decision_boundary(self) -> None:
        adapter = PiCoachAdapter(repository_root=Path(__file__).parents[2], node_executable="node")
        prompt = adapter.build_prompt(_pipeline_result())

        self.assertNotIn("steam-secret", prompt)
        self.assertNotIn("opponent-secret", prompt)
        self.assertNotIn("Secret Name", prompt)
        self.assertNotIn("future-event-id", prompt)
        self.assertIn('"decision_id":"decision_001"', prompt)
        self.assertIn('"tick":100', prompt)
        self.assertNotIn('"tick":200', prompt)

    def test_calls_pi_without_replay_tool_and_returns_its_json(self) -> None:
        captured: dict = {}

        def runner(command, **kwargs):
            captured["command"] = command
            captured.update(kwargs)
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "decision_id": "decision_001",
                        "what_could_be_done_better": "Reset behind cover before re-engaging.",
                    }
                ),
                stderr="",
            )

        adapter = PiCoachAdapter(
            repository_root=Path(__file__).parents[2],
            node_executable="node",
            runner=runner,
        )
        response = adapter(_pipeline_result())

        self.assertIn('"decision_id": "decision_001"', response)
        self.assertEqual(captured["command"][-1], "--no-tools")
        self.assertTrue(captured["command"][1].endswith("cli.mjs"))
        self.assertNotIn("--replay", captured["command"])
        self.assertNotIn("pnpm", " ".join(captured["command"]).lower())
        self.assertIn("DECISION_PAYLOAD=", captured["input"])

    def test_normalizes_relaxed_deepseek_object_to_strict_json(self) -> None:
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=(
                    "{decision_id:decision_001,"
                    "what_could_be_done_better:Hold cover before re-engaging.}"
                ),
                stderr="",
            )

        adapter = PiCoachAdapter(
            repository_root=Path(__file__).parents[2],
            node_executable="node",
            runner=runner,
        )

        self.assertEqual(
            json.loads(adapter(_pipeline_result())),
            {
                "decision_id": "decision_001",
                "what_could_be_done_better": "Hold cover before re-engaging.",
            },
        )

    def test_passes_repository_dotenv_to_every_pi_process(self) -> None:
        captured: dict = {}

        def runner(command, **kwargs):
            captured.update(kwargs)
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"decision_id":"decision_001","what_could_be_done_better":"Reset."}',
                stderr="",
            )

        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            (repository / ".env").write_text("TEST_ONLY_KEY=not-a-secret\n", encoding="utf-8")
            adapter = PiCoachAdapter(
                repository_root=repository,
                node_executable="node",
                runner=runner,
            )
            adapter(_pipeline_result())

        self.assertEqual(
            captured["env"]["HARNESS_ENV_FILE"],
            str((repository / ".env").resolve()),
        )

    def test_rejects_wrong_decision_reference(self) -> None:
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"decision_id":"decision_999","what_could_be_done_better":"Reset."}',
                stderr="",
            )

        adapter = PiCoachAdapter(
            repository_root=Path(__file__).parents[2],
            node_executable="node",
            runner=runner,
        )
        with self.assertRaises(PiCoachError):
            adapter(_pipeline_result())

    def test_batches_multiple_selected_decisions_and_normalizes_analyses(self) -> None:
        pipeline = _pipeline_result()
        second = deepcopy(pipeline["selected_decision"])
        second.update(
            {
                "decision_id": "r2:psteam-secret:t364",
                "round_number": 2,
                "decision_open_tick": 364,
                "contact_tick": 364,
                "action_close_tick": 524,
            }
        )
        pipeline["selected_decisions"] = [pipeline["selected_decision"], second]
        captured: dict = {}

        def runner(command, **kwargs):
            captured.update(kwargs)
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "analyses": [
                            {
                                "decision_id": "decision_001",
                                "what_could_be_done_better": "Reset behind cover.",
                            },
                            {
                                "decision_id": "decision_002",
                                "what_could_be_done_better": "Clear the angle first.",
                            },
                        ]
                    }
                ),
                stderr="",
            )

        adapter = PiCoachAdapter(
            repository_root=Path(__file__).parents[2],
            node_executable="node",
            runner=runner,
        )
        response = json.loads(adapter(pipeline))

        self.assertEqual([item["decision_id"] for item in response["analyses"]], [
            "decision_001",
            "decision_002",
        ])
        self.assertIn('"decisions":[', captured["input"])
        self.assertIn('"decision_id":"decision_002"', captured["input"])

    def test_full_match_prompt_keeps_all_decisions_with_round_local_evidence(self) -> None:
        pipeline = _pipeline_result()
        selected_rounds = [1, 4, 7, 10, 13, 16, 19, 22, 25, 29]
        decisions = []
        key_events = []
        for round_number in range(1, 30):
            round_tick = round_number * 10_000
            for event_number in range(30):
                key_events.append(
                    {
                        "event_id": f"r{round_number}:event:{event_number}",
                        "event_type": "damage",
                        "key_event_type": "first_damage_contact",
                        "round_number": round_number,
                        "tick": round_tick + event_number,
                        "participant_ids": ["steam-secret", "opponent-secret"],
                        "is_coaching_anchor": event_number == 29,
                    }
                )
            if round_number in selected_rounds:
                decision = deepcopy(pipeline["selected_decision"])
                decision.update(
                    {
                        "decision_id": f"r{round_number}:psteam-secret:t{round_tick}",
                        "round_number": round_number,
                        "decision_open_tick": round_tick,
                        "contact_tick": round_tick,
                        "action_close_tick": round_tick + 100,
                    }
                )
                decisions.append(decision)

        pipeline["selected_decision"] = decisions[0]
        pipeline["selected_decisions"] = decisions
        pipeline["key_events"] = key_events

        prompt = build_coach_prompt(pipeline)
        payload = json.loads(prompt.split("DECISION_PAYLOAD=", 1)[1])

        self.assertLessEqual(len(prompt.encode("utf-8")), MAX_PROMPT_BYTES)
        self.assertEqual(len(payload["decisions"]), len(selected_rounds))
        for decision_payload, expected_round in zip(
            payload["decisions"], selected_rounds, strict=True
        ):
            known_events = decision_payload["known_events"]
            self.assertEqual(len(known_events), MAX_KNOWN_EVENTS_PER_DECISION)
            self.assertTrue(
                all(event["round_number"] == expected_round for event in known_events)
            )


class HttpCoachAdapterTests(unittest.TestCase):
    def _adapter(self, handler, **kwargs):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        return HttpCoachAdapter(
            base_url="https://api.example.test/v1",
            api_key="test-key",
            model="test-model",
            client=client,
            **kwargs,
        )

    def test_posts_shared_anonymized_outcome_blind_prompt_and_normalizes_response(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["auth"] = request.headers["authorization"]
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "decision_id": "decision_001",
                                        "what_could_be_done_better": "Reset behind cover before re-engaging.",
                                    }
                                )
                            }
                        }
                    ]
                },
            )

        response = self._adapter(handler)(_pipeline_result())
        self.assertEqual(captured["url"], "https://api.example.test/v1/chat/completions")
        self.assertEqual(captured["auth"], "Bearer test-key")
        self.assertEqual(captured["body"]["model"], "test-model")
        self.assertEqual(captured["body"]["response_format"], {"type": "json_object"})
        prompt = captured["body"]["messages"][0]["content"]
        self.assertNotIn("steam-secret", prompt)
        self.assertNotIn("opponent-secret", prompt)
        self.assertNotIn('"tick":400', prompt)
        self.assertIn('"tick":164', prompt)
        self.assertEqual(
            json.loads(response),
            {
                "decision_id": "decision_001",
                "what_could_be_done_better": "Reset behind cover before re-engaging.",
            },
        )

    def test_timeout_and_network_errors_are_safe_pi_errors(self):
        def timeout_handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out")

        with self.assertRaisesRegex(
            PiCoachTimeoutError, "HTTP coaching provider failed"
        ):
            self._adapter(timeout_handler, timeout_seconds=1)(_pipeline_result())

        def network_handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline")

        with self.assertRaisesRegex(PiCoachError, "HTTP coaching provider failed"):
            self._adapter(network_handler, timeout_seconds=1)(_pipeline_result())

    def test_provider_http_error_is_not_leaked(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": {"message": "secret provider detail"}})

        with self.assertRaisesRegex(PiCoachError, "HTTP coaching provider failed") as raised:
            self._adapter(handler)(_pipeline_result())
        self.assertNotIn("secret provider detail", str(raised.exception))

    def test_rejects_malformed_provider_response(self):
        for body in (
            {},
            {"choices": []},
            {"choices": [{"message": {"content": 123}}]},
            {"choices": [{"message": {"content": "not json"}}]},
        ):
            with self.subTest(body=body):
                def handler(request: httpx.Request, body=body) -> httpx.Response:
                    return httpx.Response(200, json=body)

                with self.assertRaises(PiCoachError):
                    self._adapter(handler)(_pipeline_result())

    def test_rejects_wrong_decision_id_from_http_provider(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": '{"decision_id":"decision_999","what_could_be_done_better":"Reset."}'
                            }
                        }
                    ]
                },
            )

        with self.assertRaisesRegex(PiCoachError, "selected decision"):
            self._adapter(handler)(_pipeline_result())

    def test_shared_prompt_helper_matches_pi_adapter_and_redacts_free_form_ids(self):
        result = _pipeline_result()
        result["selected_decision"]["evidence"] = ["steam-secret held after opponent-secret contact"]
        prompt = build_coach_prompt(result)
        self.assertIn("player_01 held after player_02 contact", prompt)
        self.assertNotIn("steam-secret", prompt)
        self.assertNotIn("opponent-secret", prompt)


if __name__ == "__main__":
    unittest.main()
