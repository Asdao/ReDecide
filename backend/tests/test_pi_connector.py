from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from backend.app.coach.pi_connector import PiCoachAdapter, PiCoachError


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


if __name__ == "__main__":
    unittest.main()
