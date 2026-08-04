import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "agent-harness" / "src" / "cs2_sim" / "agent_bridge.py"
BRIDGE_MODULE_NAME = "ghackathon_agent_bridge"
BRIDGE_SPEC = importlib.util.spec_from_file_location(BRIDGE_MODULE_NAME, BRIDGE)
assert BRIDGE_SPEC is not None and BRIDGE_SPEC.loader is not None
BRIDGE_MODULE = importlib.util.module_from_spec(BRIDGE_SPEC)
sys.modules[BRIDGE_MODULE_NAME] = BRIDGE_MODULE
BRIDGE_SPEC.loader.exec_module(BRIDGE_MODULE)
handle_request = BRIDGE_MODULE.handle_request


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

    def test_replay_path_can_be_pinned_for_a_model_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approved = root / "approved.json"
            other = root / "other.json"
            approved.write_text(json.dumps({}), encoding="utf-8")
            other.write_text(json.dumps({}), encoding="utf-8")
            with patch.dict(os.environ, {"HARNESS_REPLAY_FILE": str(approved)}):
                response = handle_request({
                    "version": 1,
                    "operation": "analyze_replay",
                    "arguments": {"replay_path": str(other)},
                })
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "REPLAY_NOT_ALLOWED")

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

    def test_demo_path_uses_sidecar_and_indexes_every_player_from_first_damage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            demo = root / "demo.dem"
            demo.write_bytes(b"sidecar-backed demo")
            sidecar = {
                "schema_version": 1,
                "demo_file": demo.name,
                "header": {"map_name": "de_mirage", "tick_rate": 64},
                "rounds": [{"round_num": 1, "start": 100, "end": 300, "winner": "CT"}],
                "damages": [{
                    "round_num": 1,
                    "tick": 164,
                    "attacker_steamid": "t1",
                    "victim_steamid": "ct1",
                    "attacker_side": "T",
                    "victim_side": "CT",
                    "weapon": "ak47",
                    "dmg_health": 20,
                }],
                "kills": [{
                    "round_num": 1,
                    "tick": 240,
                    "attacker_steamid": "t1",
                    "victim_steamid": "ct1",
                    "attacker_side": "T",
                    "victim_side": "CT",
                    "weapon": "ak47",
                }],
                "ticks": [
                    {"round_num": 1, "tick": 100, "steamid": "t1", "player_name": "T One", "team_name": "T", "health": 100, "alive": True, "X": 1, "Y": 1},
                    {"round_num": 1, "tick": 100, "steamid": "ct1", "player_name": "CT One", "team_name": "CT", "health": 100, "alive": True, "X": 2, "Y": 2},
                    {"round_num": 1, "tick": 164, "steamid": "t1", "player_name": "T One", "team_name": "T", "health": 100, "alive": True, "X": 1, "Y": 1},
                    {"round_num": 1, "tick": 164, "steamid": "ct1", "player_name": "CT One", "team_name": "CT", "health": 80, "alive": True, "X": 2, "Y": 2},
                    {"round_num": 1, "tick": 240, "steamid": "t1", "player_name": "T One", "team_name": "T", "health": 100, "alive": True, "X": 1, "Y": 1},
                    {"round_num": 1, "tick": 240, "steamid": "ct1", "player_name": "CT One", "team_name": "CT", "health": 0, "alive": False, "X": 2, "Y": 2},
                ],
            }
            demo.with_suffix(".analysis.json").write_text(json.dumps(sidecar), encoding="utf-8")
            response = handle_request({
                "version": 1,
                "operation": "analyze_replay",
                "arguments": {"replay_path": str(demo), "max_decisions": 10, "max_timeline_points": 4},
            })
            decision_id = response["data"]["decision_candidates"][0]["decision_id"]
            selected_response = handle_request({
                "version": 1,
                "operation": "analyze_replay",
                "arguments": {"replay_path": str(demo), "decision_id": decision_id, "max_timeline_points": 4},
            })

        self.assertTrue(response["ok"], response)
        data = response["data"]
        self.assertEqual(data["summary"]["anchor"], "first_damage_contact")
        self.assertTrue({player["player_id"] for player in data["players"]} >= {"t1", "ct1"})
        self.assertEqual({candidate["player_id"] for candidate in data["decision_candidates"]}, {"t1", "ct1"})
        self.assertEqual({candidate["display_name"] for candidate in data["decision_candidates"]}, {"T One", "CT One"})
        self.assertTrue(all(candidate["decision_open_tick"] == candidate["contact_tick"] for candidate in data["decision_candidates"]))
        self.assertTrue(all(candidate["action_close_tick"] > candidate["contact_tick"] for candidate in data["decision_candidates"]))
        self.assertNotIn("round_won", json.dumps(data["decision_candidates"]))
        self.assertNotIn("outcome", json.dumps(data["decision_candidates"]))
        self.assertNotIn("events", data)
        self.assertTrue(all(event["is_coaching_anchor"] for event in data["key_events"]))
        self.assertTrue(data["ui_handoff"]["events_omitted_from_model"])
        self.assertNotIn("timeline", data["win_estimator"])
        self.assertTrue(data["win_estimator"]["timeline_omitted_from_model"])
        self.assertTrue(selected_response["ok"], selected_response)
        self.assertNotIn("round_won", json.dumps(selected_response["data"]["selected_decision"]))
        self.assertNotIn("outcome", json.dumps(selected_response["data"]["selected_decision"]))


if __name__ == "__main__":
    unittest.main()
