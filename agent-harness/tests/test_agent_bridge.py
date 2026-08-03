import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "agent-harness" / "src" / "cs2_sim" / "agent_bridge.py"
sys.path.insert(0, str(BRIDGE.parent.parent))

from cs2_sim.agent_bridge import handle_request  # noqa: E402


class AgentBridgeTests(unittest.TestCase):
    def test_seeded_response_is_reproducible(self):
        request = {"version": 1, "operation": "simulate_round", "arguments": {"seed": 7}}
        first = handle_request(request)
        second = handle_request(request)
        self.assertEqual(first, second)
        self.assertTrue(first["ok"])

    def test_example_request_returns_bounded_success(self):
        response = handle_request(
            {
                "version": 1,
                "operation": "simulate_round",
                "arguments": {"seed": 7, "scenario": "example", "policy": "baseline", "max_events": 3},
            }
        )
        self.assertTrue(response["ok"])
        self.assertLessEqual(len(response["data"]["key_events"]), 3)
        self.assertIn(response["data"]["winner"], {"ct", "t", None})

    def test_validation_errors_are_stable(self):
        cases = [
            ("{", "INVALID_JSON"),
            (b"\xff", "INVALID_JSON"),
            ({"version": 2, "operation": "simulate_round"}, "UNSUPPORTED_VERSION"),
            ({"version": 1, "operation": "unknown"}, "UNKNOWN_OPERATION"),
            ({"version": 1, "operation": "simulate_round", "arguments": {"scenario": "nope"}}, "INVALID_SCENARIO"),
            ({"version": 1, "operation": "simulate_round", "arguments": {"seed": True}}, "INVALID_SEED"),
        ]
        for request, code in cases:
            with self.subTest(code=code):
                response = handle_request(request)
                self.assertFalse(response["ok"])
                self.assertEqual(response["error"]["code"], code)

    def test_unknown_fields_fail_closed(self):
        response = handle_request({"version": 1, "operation": "simulate_round", "arguments": {"shell": "x"}})
        self.assertEqual(response["error"]["code"], "INVALID_ARGUMENTS")

    def test_cli_emits_only_one_json_envelope(self):
        request = {"version": 1, "operation": "simulate_round", "arguments": {"seed": 1, "max_events": 1}}
        completed = subprocess.run(
            [sys.executable, str(BRIDGE)],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(completed.stderr, "")
        response = json.loads(completed.stdout)
        self.assertTrue(response["ok"])


if __name__ == "__main__":
    unittest.main()
