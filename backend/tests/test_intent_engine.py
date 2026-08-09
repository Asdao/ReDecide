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
    _classify_stated_intent,
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
        "intent_assessment": "NOT_ESTABLISHED",
        "coordination_assessment": "NOT_ESTABLISHED",
        "recommended_adjustment": "RESET_BEHIND_COVER",
        "evidence_claims": [
            {
                "evidence_id": fact_id,
                "supports": "recommended_cs2_adjustment",
            },
            {"evidence_id": fact_id, "supports": "in_depth_coaching"},
        ],
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
        # These fields are deterministic observations from the bounded reaction
        # window and must enter the prompt without later round outcomes.
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


def _bounded_replay() -> dict[str, Any]:
    return {
        "tick_rate": 64.0,
        "header": {"map_name": "de_ancient"},
        "damages": [
            {
                "tick": 500,
                "round_num": 2,
                "victim_steamid": "p1",
                "attacker_steamid": "opponent-secret",
                "victim_place": "MainHall",
                "victim_health": 100,
                "health": 80,
                "victim_armor": 100,
                "armor": 92,
                "dmg_health_real": 20,
                "dmg_armor": 8,
                "hitgroup": "chest",
                "victim_X": 100.0,
                "victim_Y": 200.0,
                "victim_Z": 10.0,
                "victim_inventory": ["AK-47", "Flashbang"],
            }
        ],
        "ticks": [
            {
                "tick": 480,
                "round_num": 2,
                "steamid": "p1",
                "side": "t",
                "health": 100,
                "armor": 100,
                "place": "MainHall",
                "X": 100.0,
                "Y": 200.0,
                "Z": 10.0,
                "inventory": ["AK-47", "Flashbang"],
            },
            {
                "tick": 640,
                "round_num": 2,
                "steamid": "p1",
                "side": "t",
                "health": 80,
                "armor": 92,
                "place": "SideHall",
                "X": 220.0,
                "Y": 260.0,
                "Z": 10.0,
                "inventory": ["AK-47", "Flashbang"],
            },
            {
                "tick": 480,
                "round_num": 2,
                "steamid": "teammate-secret",
                "side": "t",
                "health": 100,
                "place": "MainHall",
                "X": 300.0,
                "Y": 200.0,
                "Z": 10.0,
            },
            {
                "tick": 900,
                "round_num": 2,
                "steamid": "p1",
                "side": "t",
                "health": 0,
                "place": "future-secret-place",
                "X": 900.0,
                "Y": 900.0,
                "Z": 0.0,
            },
        ],
        "round_winner": "future-secret-winner",
    }


class IntentEngineTests(unittest.TestCase):
    def test_classifies_explicit_tactical_goals_conservatively(self) -> None:
        cases = {
            "I just wanted information.": "GATHER_INFORMATION",
            "I was trying to escape and reset.": "ESCAPE_RESET",
            "I wanted to take the duel.": "TAKE_DUEL",
            "I expected my teammate to trade me.": "HOLD_FOR_SUPPORT",
            "I wanted to create space with a flash.": "CREATE_SPACE_WITH_UTILITY",
            "I wanted to reposition.": "REPOSITION",
            "I had a plan.": "UNCLEAR",
            "I did not want to fight.": "ESCAPE_RESET",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(_classify_stated_intent(text), expected)

    def test_selects_exact_nonfirst_production_analysis_and_bounds_prompt(self) -> None:
        provider = RecordingProvider(_valid_response("decision:observed-action"))
        engine = IntentCoachingEngine(provider)

        result = engine.evaluate_intent(
            _production_result(),
            "I thought my teammate would trade me.",
            player_id="p1",
            decision_id="r2:p1:t500",
        )

        self.assertEqual(result["decision_id"], "r2:p1:t500")
        self.assertEqual(result["player_id"], "p1")
        self.assertEqual(result["knowledge_cutoff_tick"], 660)
        self.assertEqual(result["facts_referenced"], ["decision:observed-action"])
        prompt = provider.prompts[0]
        self.assertIn("requested-anchor", prompt)
        self.assertNotIn("first-anchor", prompt)
        self.assertNotIn("future-death", prompt)
        self.assertNotIn("other-player", prompt)
        self.assertIn("post_contact_displacement", prompt)
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
        decision = _decision("r2:p1:t500", "p1", 500, 2)
        decision["observed_action"] = "unknown"
        decision["evidence"] = ["no_action_window_observation"]
        context = {
            "selected_decision": decision,
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
            {**_valid_response("requested-anchor"), "intent_assessment": "SUPPORTED"},
            {
                **_valid_response("requested-anchor"),
                "coordination_assessment": "GAP_OBSERVED",
            },
            _valid_response("invented-fact"),
            {**_valid_response("requested-anchor"), "evidence_claims": []},
            {
                **_valid_response("requested-anchor"),
                "evidence_claims": [
                    {
                        "evidence_id": "requested-anchor",
                        "supports": "in_depth_coaching",
                    }
                ],
            },
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

    def test_projects_contact_reaction_utility_and_teammate_spacing(self) -> None:
        context = _production_result()
        context["_intent_source_replay"] = _bounded_replay()
        provider = RecordingProvider(_valid_response("telemetry:reaction-movement"))

        result = IntentCoachingEngine(provider).evaluate_intent(
            context,
            "I was trying to escape.",
            player_id="p1",
            decision_id="r2:p1:t500",
        )

        self.assertEqual(result["knowledge_cutoff_tick"], 660)
        prompt = provider.prompts[0]
        self.assertIn("telemetry:contact-state", prompt)
        self.assertIn("telemetry:reaction-movement", prompt)
        self.assertIn("telemetry:teammate-spacing", prompt)
        self.assertIn("MainHall", prompt)
        self.assertIn('"available_utility":["flash"]', prompt)
        self.assertIn('"displacement_units":134.2', prompt)
        self.assertNotIn("future-secret-place", prompt)
        self.assertNotIn("future-secret-winner", prompt)
        self.assertNotIn("teammate-secret", prompt)
        self.assertNotIn("opponent-secret", prompt)

    def test_each_public_coaching_field_requires_substantive_evidence(self) -> None:
        response = _valid_response("decision:observed-action")
        response["evidence_claims"] = [
            {
                "evidence_id": "requested-anchor",
                "supports": "recommended_cs2_adjustment",
            },
            {
                "evidence_id": "decision:observed-action",
                "supports": "in_depth_coaching",
            },
        ]

        with self.assertRaises(IntentMalformedOutputError):
            IntentCoachingEngine(RecordingProvider(response)).evaluate_intent(
                _production_result(),
                "I wanted to reset.",
                player_id="p1",
                decision_id="r2:p1:t500",
            )

    def test_utility_adjustment_must_cite_bounded_inventory_evidence(self) -> None:
        context = _production_result()
        context["_intent_source_replay"] = _bounded_replay()
        response = _valid_response("telemetry:reaction-movement")
        response["recommended_adjustment"] = "USE_AVAILABLE_UTILITY"

        with self.assertRaises(IntentMalformedOutputError):
            IntentCoachingEngine(RecordingProvider(response)).evaluate_intent(
                context,
                "I wanted to create space with utility.",
                player_id="p1",
                decision_id="r2:p1:t500",
            )

    def test_backend_ignores_provider_prose_and_renders_its_own_text(self) -> None:
        response = _valid_response("decision:observed-action")
        response["in_depth_coaching"] = "Use a two-stage pathâ€”then reset â€“ safely."

        response.pop("in_depth_coaching")
        result = IntentCoachingEngine(RecordingProvider(response)).evaluate_intent(
            _production_result(),
            "I wanted to reset.",
            player_id="p1",
            decision_id="r2:p1:t500",
        )

        self.assertIn("Because you said you wanted to escape and reset", result["in_depth_coaching"])
        self.assertNotIn("two-stage", result["in_depth_coaching"])

    def test_rejects_representative_hallucinated_or_invalid_tactical_claims(self) -> None:
        context = _production_result()
        context["_intent_source_replay"] = _bounded_replay()
        invalid_phrases = [
            "Without replay telemetry, use the line of sight.",
            "Throw a stun grenade before leaving.",
            "There was no movement after contact.",
            "Smoke the chokepoint before escaping.",
            "You survived the engagement.",
        ]
        for phrase in invalid_phrases:
            with self.subTest(phrase=phrase):
                response = _valid_response("telemetry:reaction-movement")
                response["in_depth_coaching"] = phrase
                with self.assertRaises(IntentMalformedOutputError):
                    IntentCoachingEngine(RecordingProvider(response)).evaluate_intent(
                        context,
                        "I was trying to escape.",
                        player_id="p1",
                        decision_id="r2:p1:t500",
                    )

    def test_backend_renders_public_prose_without_internal_tokens_or_ticks(self) -> None:
        selected = _decision("r2:p1:t500", "p1", 500, 2)
        selected["known_before_decision"] = [
            {
                "evidence_id": "health-at-contact",
                "tick": 500,
                "statement": (
                    "At tick 500, PLAYER_INTENT and contact_tick said player_01 "
                    "moved away from player_02 at replay coordinate 660."
                ),
            }
        ]
        result = IntentCoachingEngine(
            RecordingProvider(_valid_response("health-at-contact"))
        ).evaluate_intent(
            {"selected_decision": selected},
            "I wanted to reset.",
            player_id="p1",
            decision_id="r2:p1:t500",
        )

        public_text = " ".join(
            str(result[field])
            for field in (
                "intent_feasibility",
                "coordination_gap",
                "recommended_cs2_adjustment",
                "in_depth_coaching",
            )
        )
        self.assertNotIn("PLAYER_INTENT", public_text)
        self.assertNotIn("player_01", public_text)
        self.assertNotIn("player_02", public_text)
        self.assertNotIn("contact_tick", public_text)
        self.assertNotIn("replay coordinate", public_text)
        self.assertNotRegex(public_text.lower(), r"\btick\s*\d+\b")
        self.assertEqual(result["knowledge_cutoff_tick"], 660)

    def test_information_intent_receives_plain_contextual_coaching(self) -> None:
        replay = _bounded_replay()
        replay["damages"][0]["victim_place"] = "Banana"
        replay["ticks"][0]["place"] = "Banana"
        replay["ticks"][1].update(
            {"place": "Banana", "X": 100.1, "Y": 200.0, "Z": 10.0}
        )
        context = _production_result()
        context["_intent_source_replay"] = replay
        response = _valid_response("telemetry:contact-state")
        response["recommended_adjustment"] = "REASSESS_BEFORE_REENGAGING"
        response["evidence_claims"] = [
            {
                "evidence_id": "telemetry:contact-state",
                "supports": "recommended_cs2_adjustment",
            },
            {
                "evidence_id": "telemetry:reaction-movement",
                "supports": "in_depth_coaching",
            },
        ]

        result = IntentCoachingEngine(RecordingProvider(response)).evaluate_intent(
            context,
            "I just wanted information.",
            player_id="p1",
            decision_id="r2:p1:t500",
        )

        coaching = result["in_depth_coaching"]
        self.assertIn("You took first damage on Banana", coaching)
        self.assertIn("You remained almost stationary", coaching)
        self.assertIn("wanted to gather information", coaching)
        self.assertIn("shoulder or jiggle peek", coaching)
        for internal_word in (
            "deterministic",
            "threshold",
            "parser",
            "bounded",
            "units",
            "decision window",
        ):
            self.assertNotIn(internal_word, coaching.lower())

    def test_unclear_intent_asks_for_clarification_without_calling_provider(self) -> None:
        provider = RecordingProvider(AssertionError("provider must not be called"))
        result = IntentCoachingEngine(provider).evaluate_intent(
            _production_result(),
            "I had a plan.",
            player_id="p1",
            decision_id="r2:p1:t500",
        )

        self.assertEqual(provider.prompts, [])
        self.assertEqual(result["facts_referenced"], [])
        self.assertIn("Tell us whether you were trying", result["in_depth_coaching"])
        self.assertNotIn("first damage", result["in_depth_coaching"].lower())

    def test_provider_adjustment_must_match_the_stated_goal(self) -> None:
        response = _valid_response("decision:observed-action")
        response["recommended_adjustment"] = "CONTROLLED_REENGAGEMENT"

        with self.assertRaises(IntentMalformedOutputError):
            IntentCoachingEngine(RecordingProvider(response)).evaluate_intent(
                _production_result(),
                "I just wanted information.",
                player_id="p1",
                decision_id="r2:p1:t500",
            )

    def test_parser_labels_cannot_disguise_coordinates_aliases_or_schema_names(self) -> None:
        unsafe_labels = ("0500", "5 00", "5e2", "player-02", "player 02", "contactTick")
        for label in unsafe_labels:
            with self.subTest(label=label):
                replay = _bounded_replay()
                replay["damages"][0]["victim_place"] = label
                replay["ticks"][0]["place"] = label
                context = _production_result()
                context["_intent_source_replay"] = replay
                result = IntentCoachingEngine(
                    RecordingProvider(_valid_response("telemetry:contact-state"))
                ).evaluate_intent(
                    context,
                    "I wanted to reset.",
                    player_id="p1",
                    decision_id="r2:p1:t500",
                )

                public_text = result["in_depth_coaching"]
                self.assertNotIn(label, public_text)
                self.assertNotIn("500", public_text)


if __name__ == "__main__":
    unittest.main()
