from __future__ import annotations

import unittest

from backend.app.coach.intent_claims import (
    IntentClaimValidationError,
    ProviderEvidenceClaim,
    build_public_evidence_summary,
    render_public_evidence_summary,
    validate_evidence_claims,
)


class IntentClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = [
            {
                "evidence_id": "telemetry:contact-state",
                "statement": "Your health changed from 100 to 72 at contact",
            },
            {
                "evidence_id": "telemetry:reaction-movement",
                "statement": "PLAYER_INTENT was followed by movement from player_01 away from player_02",
            },
            {
                "evidence_id": "telemetry:teammate-spacing",
                "statement": "player_03 was 280 units away",
            },
        ]

    def test_validates_claims_and_uses_authoritative_order(self) -> None:
        claims = validate_evidence_claims(
            [
                {
                    "evidence_id": "telemetry:reaction-movement",
                    "supports": "in_depth_coaching",
                },
                {
                    "evidence_id": "telemetry:contact-state",
                    "supports": "intent_feasibility",
                },
            ],
            self.evidence,
        )

        self.assertEqual(
            [claim.evidence_id for claim in claims],
            ["telemetry:contact-state", "telemetry:reaction-movement"],
        )

    def test_rejects_unknown_duplicate_pairs_and_blank_evidence_ids(self) -> None:
        invalid_claims = [
            [{"evidence_id": "unknown", "supports": "intent_feasibility"}],
            [
                {
                    "evidence_id": "telemetry:contact-state",
                    "supports": "intent_feasibility",
                },
                {
                    "evidence_id": "telemetry:contact-state",
                    "supports": "intent_feasibility",
                },
            ],
            [{"evidence_id": "   ", "supports": "intent_feasibility"}],
        ]
        for claims in invalid_claims:
            with self.subTest(claims=claims):
                with self.assertRaises(IntentClaimValidationError):
                    validate_evidence_claims(claims, self.evidence)

    def test_one_evidence_item_may_support_distinct_public_fields(self) -> None:
        claims = validate_evidence_claims(
            [
                {
                    "evidence_id": "telemetry:reaction-movement",
                    "supports": "intent_feasibility",
                },
                {
                    "evidence_id": "telemetry:reaction-movement",
                    "supports": "in_depth_coaching",
                },
            ],
            self.evidence,
        )

        self.assertEqual(
            [claim.supports for claim in claims],
            ["intent_feasibility", "in_depth_coaching"],
        )

    def test_schema_forbids_provider_authored_factual_text(self) -> None:
        with self.assertRaises(IntentClaimValidationError):
            validate_evidence_claims(
                [
                    {
                        "evidence_id": "telemetry:contact-state",
                        "supports": "intent_feasibility",
                        "claim": "The provider says this happened.",
                    }
                ],
                self.evidence,
            )

    def test_public_summary_uses_server_statement_not_provider_content(self) -> None:
        summary = build_public_evidence_summary(
            [
                {
                    "evidence_id": "telemetry:reaction-movement",
                    "supports": "recommended_cs2_adjustment",
                }
            ],
            self.evidence,
        )

        self.assertEqual(
            summary,
            "Replay evidence: your stated intent was followed by movement from you away from the opponent.",
        )
        self.assertNotIn("telemetry:", summary)
        self.assertNotIn("PLAYER_INTENT", summary)
        self.assertNotIn("player_", summary)

    def test_public_summary_redacts_raw_ids_and_remaining_internal_labels(self) -> None:
        claim = ProviderEvidenceClaim(
            evidence_id="safe-id", supports="in_depth_coaching"
        )
        grounded = validate_evidence_claims(
            [claim.model_dump()],
            [
                {
                    "evidence_id": "safe-id",
                    "statement": (
                        "STEAM_PLAYER_ID 76561198000000001 supports "
                        "decision:observed-action"
                    ),
                }
            ],
        )

        summary = render_public_evidence_summary(grounded)

        self.assertNotIn("76561198000000001", summary)
        self.assertNotIn("STEAM_PLAYER_ID", summary)
        self.assertNotIn("decision:observed-action", summary)

    def test_public_summary_preserves_legitimate_cs2_labels(self) -> None:
        summary = build_public_evidence_summary(
            [
                {
                    "evidence_id": "safe-id",
                    "supports": "in_depth_coaching",
                }
            ],
            {
                "safe-id": "The player held M4A1_S on DE_DUST2 for the CT_SIDE setup"
            },
        )

        self.assertIn("M4A1_S", summary)
        self.assertIn("DE_DUST2", summary)
        self.assertIn("CT_SIDE", summary)

    def test_rejects_invalid_authoritative_evidence(self) -> None:
        claims = [
            {
                "evidence_id": "duplicate",
                "supports": "intent_feasibility",
            }
        ]
        invalid_evidence = [
            [{"evidence_id": "", "statement": "known"}],
            [{"evidence_id": "duplicate", "statement": ""}],
            [
                {"evidence_id": "duplicate", "statement": "first"},
                {"evidence_id": "duplicate", "statement": "second"},
            ],
        ]
        for evidence in invalid_evidence:
            with self.subTest(evidence=evidence):
                with self.assertRaises(IntentClaimValidationError):
                    validate_evidence_claims(claims, evidence)

    def test_summary_limit_must_be_a_positive_integer(self) -> None:
        grounded = validate_evidence_claims(
            [
                {
                    "evidence_id": "telemetry:contact-state",
                    "supports": "intent_feasibility",
                }
            ],
            self.evidence,
        )
        for invalid_limit in (0, -1, True, 1.5):
            with self.subTest(max_items=invalid_limit):
                with self.assertRaises(IntentClaimValidationError):
                    render_public_evidence_summary(grounded, max_items=invalid_limit)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
