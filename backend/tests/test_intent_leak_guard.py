from __future__ import annotations

import unittest

from backend.app.coach.intent_leak_guard import (
    FORBIDDEN_INTERNAL_TOKENS,
    PublicCoachingProseError,
    PublicProseViolationKind,
    validate_public_coaching_payload,
    validate_public_coaching_prose,
)


class IntentLeakGuardTests(unittest.TestCase):
    def test_rejects_every_internal_prompt_or_schema_token_case_insensitively(self) -> None:
        for token in FORBIDDEN_INTERNAL_TOKENS:
            with self.subTest(token=token):
                with self.assertRaises(PublicCoachingProseError) as raised:
                    validate_public_coaching_prose(
                        f"The model repeated `{token.lower()}`.",
                        field_name="in_depth_coaching",
                    )

                violation = raised.exception.violation
                self.assertEqual(violation.field_name, "in_depth_coaching")
                self.assertEqual(violation.kind, PublicProseViolationKind.INTERNAL_TOKEN)

    def test_rejects_exact_tick_coordinates_in_common_forms(self) -> None:
        unsafe = (
            "At tick 500, move back.",
            "At TICK: 61387 you took damage.",
            "Review tick #88113 before the next game.",
            "The anchor is tick number 42.",
            "The event happened at t=500.",
            "Use the state at T = 61387.",
            "The decision tick was 500.",
            "Contact occurred at tick-500.",
            "Contact occurred at tick +500.",
            "Use the state at t:500.",
            "Use the state at t 500.",
            "Review the 500th tick.",
        )
        for prose in unsafe:
            with self.subTest(prose=prose):
                with self.assertRaises(PublicCoachingProseError) as raised:
                    validate_public_coaching_prose(prose)
                self.assertEqual(
                    raised.exception.violation.kind,
                    PublicProseViolationKind.EXACT_TICK,
                )

    def test_rejects_residual_aliases_and_disguised_known_coordinates(self) -> None:
        unsafe_aliases = ("player_02", "player_2", "player_01_backup")
        for alias in unsafe_aliases:
            with self.subTest(alias=alias):
                with self.assertRaises(PublicCoachingProseError):
                    validate_public_coaching_prose(f"The output mentioned {alias}.")

        with self.assertRaises(PublicCoachingProseError) as raised:
            validate_public_coaching_prose(
                "The replay coordinate was 61387.",
                forbidden_replay_coordinates={61387, 61547},
            )
        self.assertEqual(
            raised.exception.violation.kind,
            PublicProseViolationKind.EXACT_TICK,
        )

    def test_allows_ordinary_numbers_and_tick_durations(self) -> None:
        safe = (
            "You had 35 health and 92 armor after contact.",
            "Move 200 units toward hard cover.",
            "Wait 2 seconds before re-peeking.",
            "The reaction window lasts 160 ticks.",
            "Use a two-stage reset after taking 20 damage.",
        )
        for prose in safe:
            with self.subTest(prose=prose):
                self.assertEqual(validate_public_coaching_prose(prose), prose)

    def test_payload_guard_checks_public_prose_but_not_structured_cutoff(self) -> None:
        payload = {
            "intent_feasibility": "Your plan was plausible.",
            "coordination_gap": "The available evidence does not confirm a callout.",
            "recommended_cs2_adjustment": "Reset behind cover.",
            "in_depth_coaching": "Confirm support before the next peek.",
            "knowledge_cutoff_tick": 61387,
            "facts_referenced": ["telemetry:contact-state"],
        }

        validate_public_coaching_payload(payload)

        payload["coordination_gap"] = "DECISION_CONTEXT was incomplete."
        with self.assertRaises(PublicCoachingProseError) as raised:
            validate_public_coaching_payload(payload)
        self.assertEqual(raised.exception.violation.field_name, "coordination_gap")

    def test_rejects_non_string_values_in_a_public_prose_field(self) -> None:
        with self.assertRaises(PublicCoachingProseError) as raised:
            validate_public_coaching_payload({"in_depth_coaching": 500})

        self.assertEqual(
            raised.exception.violation.kind,
            PublicProseViolationKind.INVALID_TYPE,
        )


if __name__ == "__main__":
    unittest.main()
