from unittest import TestCase
import json
from fastapi.testclient import TestClient

from backend.app.contracts import IntentCoachingRequest, IntentCoachingResponse
from backend.app.coach.pi_connector import PiCoachAdapter
from backend.app.coach.intent_engine import IntentCoachingEngine
from backend.app.main import create_app
from backend.app.orchestration import AnalysisService, FIXTURE_ANALYSIS_ID


class IntentCoachingTests(TestCase):
    def setUp(self) -> None:
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_pi_adapter_builds_intent_prompt_with_knowledge_cutoff(self) -> None:
        adapter = PiCoachAdapter()
        pipeline_result = {
            "selected_decision": {
                "decision_id": "r1:p1:t2500",
                "observed_action": "HOLD_FOR_SUPPORT",
                "decision_open_tick": 2500,
                "action_close_tick": 2600,
                "known_before_decision": [
                    {"evidence_id": "displacement_below_threshold", "tick": 2400, "category": "movement", "statement": "low movement", "value": 0.1, "source": "telemetry"}
                ]
            }
        }
        prompt = adapter.build_intent_prompt(pipeline_result, "I expected my teammate to swing with me")
        self.assertIn("I expected my teammate to swing with me", prompt)
        self.assertIn("facts known BEFORE action_close_tick", prompt)
        self.assertIn("HOLD_FOR_SUPPORT", prompt)

    def test_intent_engine_temporal_cutoff_and_subjective_framing(self) -> None:
        engine = IntentCoachingEngine()
        pipeline_result = {
            "selected_decision": {
                "decision_id": "r1:p1:t2500",
                "observed_action": "HOLD_FOR_SUPPORT",
                "decision_open_tick": 2500,
                "known_before_decision": [
                    {"evidence_id": "valid_past_fact", "tick": 2400},
                    {"evidence_id": "future_fact_should_be_stripped", "tick": 2600},
                ]
            }
        }
        selected, valid_ids, open_tick = engine._extract_decision_context(pipeline_result)
        self.assertEqual(open_tick, 2500)
        self.assertIn("valid_past_fact", valid_ids)
        self.assertNotIn("future_fact_should_be_stripped", valid_ids)

        prompt = engine.build_intent_prompt(selected, "I wanted to flash for entry", open_tick)
        self.assertIn("subjective post-hoc explanation", prompt)
        self.assertIn("BEFORE or AT decision_open_tick", prompt)

    def test_intent_engine_filters_hallucinated_facts(self) -> None:
        raw_facts = ["valid_past_fact", "hallucinated_nonexistent_fact", "another_fake_id"]
        valid_ids = {"valid_past_fact", "another_real_fact"}
        validated = IntentCoachingEngine._validate_and_filter_facts(raw_facts, valid_ids)
        self.assertEqual(validated, ["valid_past_fact"])

    def test_pi_adapter_evaluates_intent_offline_fallback(self) -> None:
        adapter = PiCoachAdapter()
        pipeline_result = {
            "selected_decision": {
                "decision_id": "r1:p1:t2500",
                "decision_open_tick": 2500,
                "action_close_tick": 2600,
            }
        }
        result = adapter.evaluate_intent(pipeline_result, "I expected my teammate to swing with me")
        self.assertEqual(result["user_intent"], "I expected my teammate to swing with me")
        self.assertIn("Moderate Risk", result["intent_feasibility"])
        self.assertIn("tick 2500", result["coordination_gap"])
        self.assertEqual(result["knowledge_cutoff_tick"], 2500)

    def test_intent_endpoint_returns_contextual_coaching(self) -> None:
        replay_payload = {
            "map": {"name": "de_inferno", "tick_rate": 64},
            "players": [{"player_id": "p1", "display_name": "flameZ", "side_by_round": {"1": "t"}}],
            "rounds": [{"round_num": 1, "start": 100, "end": 3000}],
            "damages": [{"round_num": 1, "tick": 2579, "attacker_id": "p2", "victim_id": "p1", "damage_health": 80}],
            "ticks": [{"tick": 2579, "players": [{"player_id": "p1", "side": "t", "X": 0, "Y": 0, "Z": 0, "health": 20, "alive": True}]}]
        }
        prepare_resp = self.client.post("/api/analysis/prepare", json={"replay": replay_payload})
        self.assertIn(prepare_resp.status_code, (200, 202))
        analysis_id = prepare_resp.json()["analysis_id"]

        intent_payload = {
            "analysis_id": analysis_id,
            "player_id": "p1",
            "decision_id": "r1:p1:t2579",
            "intent_text": "I expected my teammate to swing with me from Banana."
        }
        resp = self.client.post(f"/api/analysis/{analysis_id}/intent", json=intent_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["analysis_id"], analysis_id)
        self.assertEqual(data["user_intent"], "I expected my teammate to swing with me from Banana.")
        self.assertTrue(len(data["in_depth_coaching"]) > 20)
