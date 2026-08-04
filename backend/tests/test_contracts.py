"""Focused tests for the frozen RE:DECIDE version 1.0 contracts."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from backend.app.contracts import (
    AnalysisResponse,
    AnalyzeJsonRequest,
    AnalyzeRequest,
    DecisionCard,
    DecisionPacket,
    IntentInput,
)


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with (FIXTURES / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class ContractFixtureTests(unittest.TestCase):
    def test_valid_fixtures_match_frozen_contracts(self) -> None:
        packet = DecisionPacket.model_validate(
            load_fixture("decision_packet.valid.json")
        )
        intent = IntentInput.model_validate(load_fixture("intent.valid.json"))
        card = DecisionCard.model_validate(load_fixture("decision_card.valid.json"))
        request = AnalyzeJsonRequest.model_validate(
            load_fixture("analyze_json_request.valid.json")
        )

        self.assertEqual(packet.schema_version, "1.0")
        self.assertEqual(intent.tag.value, "TAKE_DUEL")
        self.assertEqual(card.decision_id, packet.decision_id)
        self.assertEqual(request.decision_packet.decision_id, packet.decision_id)
        self.assertTrue(
            set(card.facts_used).issubset(packet.available_evidence_ids())
        )

    def test_rejects_fact_after_decision_open_tick(self) -> None:
        payload = load_fixture("decision_packet.valid.json")
        payload["known_before_decision"][0]["tick"] = (
            payload["decision_open_tick"] + 1
        )

        with self.assertRaisesRegex(ValidationError, "after decision_open_tick"):
            DecisionPacket.model_validate(payload)

    def test_rejects_action_window_that_closes_before_it_opens(self) -> None:
        payload = load_fixture("decision_packet.valid.json")
        payload["action_close_tick"] = payload["decision_open_tick"] - 1

        with self.assertRaisesRegex(ValidationError, "at or after"):
            DecisionPacket.model_validate(payload)

    def test_rejects_duplicate_evidence_ids(self) -> None:
        payload = load_fixture("decision_packet.valid.json")
        duplicate = deepcopy(payload["known_before_decision"][0])
        payload["known_before_decision"].append(duplicate)

        with self.assertRaisesRegex(ValidationError, "must be unique"):
            DecisionPacket.model_validate(payload)

    def test_rejects_unknown_observed_action_label(self) -> None:
        payload = load_fixture("decision_packet.valid.json")
        payload["observed_action"]["label"] = "PLAYER_DIED"

        with self.assertRaises(ValidationError):
            DecisionPacket.model_validate(payload)

    def test_rejects_future_outcome_field(self) -> None:
        payload = load_fixture("decision_packet.valid.json")
        payload["round_winner"] = "CT"

        with self.assertRaisesRegex(
            ValidationError, "Extra inputs are not permitted"
        ):
            DecisionPacket.model_validate(payload)

    def test_rejects_wrong_schema_version(self) -> None:
        payload = load_fixture("decision_packet.valid.json")
        payload["schema_version"] = "2.0"

        with self.assertRaises(ValidationError):
            DecisionPacket.model_validate(payload)

    def test_rejects_confidence_outside_unit_interval(self) -> None:
        payload = load_fixture("decision_card.valid.json")
        payload["confidence"] = 1.01

        with self.assertRaises(ValidationError):
            DecisionCard.model_validate(payload)

    def test_rejects_unknown_intent_tag(self) -> None:
        payload = load_fixture("intent.valid.json")
        payload["tag"] = "WIN_ROUND"

        with self.assertRaises(ValidationError):
            IntentInput.model_validate(payload)

    def test_analyze_request_requires_exactly_one_source(self) -> None:
        with self.assertRaisesRegex(ValidationError, "exactly one"):
            AnalyzeRequest.model_validate(
                {
                    "sample_id": "fixture-mirage-01",
                    "analysis_id": "sample:fixture-mirage-01",
                }
            )

    def test_analyze_json_normalizes_blank_intent_text(self) -> None:
        payload = load_fixture("analyze_json_request.valid.json")
        payload["intent"]["text"] = "   "

        request = AnalyzeJsonRequest.model_validate(payload)

        self.assertIsNone(request.intent.text)

    def test_analyze_json_rejects_long_intent_text(self) -> None:
        payload = load_fixture("analyze_json_request.valid.json")
        payload["intent"]["text"] = "x" * 241

        with self.assertRaisesRegex(ValidationError, "240 characters"):
            AnalyzeJsonRequest.model_validate(payload)

    def test_analysis_response_rejects_unsupported_fact_reference(self) -> None:
        packet = load_fixture("decision_packet.valid.json")
        card = load_fixture("decision_card.valid.json")
        card["facts_used"].append("E999")

        with self.assertRaisesRegex(ValidationError, "unsupported evidence IDs"):
            AnalysisResponse.model_validate(
                {"decision_packet": packet, "decision_card": card}
            )


if __name__ == "__main__":
    unittest.main()
