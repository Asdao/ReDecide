from __future__ import annotations

import json
from typing import Any
import unittest

from backend.app.coach.intent_engine import (
    IntentCoachingEngine,
    IntentDecisionNotFoundError,
    IntentInsufficientEvidenceError,
    IntentMalformedOutputError,
    IntentProviderTimeoutError,
    IntentProviderUnavailableError,
)
from backend.app.coach.pi_connector import PiCoachError


class RecordingProvider:
    def __init__(self, response: dict[str, Any] | Exception) -> None:
        self.response = response
        self.prompts: list[str] = []

    def run_prompt(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if isinstance(self.response, Exception):
            raise self.response
        return json.dumps(self.response)


def _valid_response(fact_id: str) -> dict[str, Any]:
    return {
        "intent_feasibility": "Plausible, but exposed to an isolated duel.",
        "coordination_gap": "The replay cannot confirm the stated callout.",
        "recommended_cs2_adjustment": "Confirm support before re-engaging.",
        "in_depth_coaching": "Reset behind cover, confirm the trade setup, then choose the next peek.",
        "facts_referenced": [fact_id],
    }


def _decision(decision_id: str, player_id: str, tick: int, round_number: int) -> dict[str, Any]:
    return {
        "decision_id": decision_id,
        "round_number": round_number,
        "player_id": player_id,
        "side": "t",
        "role": "victim",
        "event_category": "damage",
        "decision_open_tick": tick,
        "contact_tick": tick,
        "action_close_tick": tick + 160,
        "opponent_id": "opponent-secret",
        # These post-contact classifier fields must not enter the prompt.
        "observed_action": "RE_ENGAGE",
        "evidence": ["post_contact_displacement"],
    }


def _production_result() -> dict[str, Any]:
    first = _decision("r1:p1:t100", "p1", 100, 1)
    requested = _decision("r2:p1:t500", "p1", 500, 2)
    return {
        "selected_decision": first,
        "analyses": [
            {"selected_decision": first, "coach_analysis": {"decision_id": first["decision_id"]}},
            {
                "selected_decision": requested,
                "coach_analysis": {"decision_id": requested["decision_id"]},
            },
        ],
        "decision_candidates": [first, requested],
        "key_events": [
            {
                "event_id": "first-anchor",
                "round_number": 1,
                "tick": 100,
                "event_type": "damage",
                "key_event_type": "first_damage_contact",
                "participant_ids": ["p1", "opponent-secret"],
                "is_coaching_anchor": True,
            },
            {
                "event_id": "requested-anchor",
                "round_number": 2,
                "tick": 500,
                "event_type": "damage",
                "key_event_type": "first_damage_contact",
                "participant_ids": ["p1", "opponent-secret"],
                "is_coaching_anchor": True,
            },
            {
                "event_id": "future-death",
                "round_number": 2,
                "tick": 501,
                "event_type": "kill",
                "key_event_type": "kill_marker",
                "participant_ids": ["p1", "opponent-secret"],
                "is_coaching_anchor": False,
            },
            {
                "event_id": "other-player",
                "round_number": 2,
                "tick": 450,
                "event_type": "damage",
                "participant_ids": ["p2", "p3"],
            },
        ],
        "round_outcome": "t_win",
        "match_winner": "secret future result",
    }


class IntentEngineTests(unittest.TestCase):
    def test_selects_exact_nonfirst_production_analysis_and_bounds_prompt(self) -> None:
        provider = RecordingProvider(_valid_response("requested-anchor"))
        engine = IntentCoachingEngine(provider)

        result = engine.evaluate_intent(
            _production_result(),
            "I thought my teammate would trade me.",
            player_id="p1",
            decision_id="r2:p1:t500",
        )

        self.assertEqual(result["decision_id"], "r2:p1:t500")
        self.assertEqual(result["player_id"], "p1")
        self.assertEqual(result["knowledge_cutoff_tick"], 500)
        self.assertEqual(result["facts_referenced"], ["requested-anchor"])
        prompt = provider.prompts[0]
        self.assertIn("requested-anchor", prompt)
        self.assertNotIn("first-anchor", prompt)
        self.assertNotIn("future-death", prompt)
        self.assertNotIn("other-player", prompt)
        self.assertNotIn("post_contact_displacement", prompt)
        self.assertNotIn("secret future result", prompt)
        self.assertNotIn("opponent-secret", prompt)
        self.assertIn('"decision_open_tick":500', prompt)

    def test_rejects_missing_or_wrong_player_decision(self) -> None:
        engine = IntentCoachingEngine(RecordingProvider(_valid_response("requested-anchor")))
        cases = [("does-not-exist", "p1"), ("r2:p1:t500", "different-player")]
        for decision_id, player_id in cases:
            with self.subTest(decision_id=decision_id, player_id=player_id):
                with self.assertRaises(IntentDecisionNotFoundError):
                    engine.evaluate_intent(
                        _production_result(),
                        "I wanted to take space.",
                        player_id=player_id,
                        decision_id=decision_id,
                    )

    def test_rejects_context_without_citable_predecision_evidence(self) -> None:
        context = {
            "selected_decision": _decision("r2:p1:t500", "p1", 500, 2),
            "key_events": [
                {
                    "event_id": "future-only",
                    "round_number": 2,
                    "tick": 501,
                    "participant_ids": ["p1"],
                }
            ],
        }
        engine = IntentCoachingEngine(RecordingProvider(_valid_response("future-only")))

        with self.assertRaises(IntentInsufficientEvidenceError):
            engine.evaluate_intent(
                context,
                "I wanted to reset.",
                player_id="p1",
                decision_id="r2:p1:t500",
            )

    def test_accepts_explicit_ticked_predecision_evidence(self) -> None:
        selected = _decision("r2:p1:t500", "p1", 500, 2)
        selected["known_before_decision"] = [
            {"evidence_id": "health-at-contact", "tick": 500, "statement": "health was 35"},
            {"evidence_id": "future-health", "tick": 501, "statement": "health later reached 0"},
        ]
        provider = RecordingProvider(_valid_response("health-at-contact"))
        result = IntentCoachingEngine(provider).evaluate_intent(
            {"selected_decision": selected},
            "I wanted to reset.",
            player_id="p1",
            decision_id="r2:p1:t500",
        )

        self.assertEqual(result["facts_referenced"], ["health-at-contact"])
        self.assertNotIn("future-health", provider.prompts[0])

    def test_fails_closed_when_provider_is_unavailable(self) -> None:
        for error in (PiCoachError("provider failed"), ValueError("bad provider state")):
            with self.subTest(error=type(error).__name__):
                provider = RecordingProvider(error)
                with self.assertRaises(IntentProviderUnavailableError):
                    IntentCoachingEngine(provider).evaluate_intent(
                        _production_result(),
                        "I wanted to reset.",
                        player_id="p1",
                        decision_id="r2:p1:t500",
                    )

    def test_fails_closed_when_provider_times_out(self) -> None:
        provider = RecordingProvider(TimeoutError("provider timed out"))

        with self.assertRaises(IntentProviderTimeoutError):
            IntentCoachingEngine(provider).evaluate_intent(
                _production_result(),
                "I wanted to reset.",
                player_id="p1",
                decision_id="r2:p1:t500",
            )

    def test_rejects_malformed_or_ungrounded_provider_output(self) -> None:
        cases = [
            {"intent_feasibility": "missing the other required fields"},
            {**_valid_response("requested-anchor"), "unexpected": "not allowed"},
            _valid_response("invented-fact"),
            {**_valid_response("requested-anchor"), "facts_referenced": []},
        ]
        for response in cases:
            with self.subTest(response=response):
                engine = IntentCoachingEngine(RecordingProvider(response))
                with self.assertRaises(IntentMalformedOutputError):
                    engine.evaluate_intent(
                        _production_result(),
                        "I wanted to reset.",
                        player_id="p1",
                        decision_id="r2:p1:t500",
                    )


if __name__ == "__main__":
    unittest.main()
