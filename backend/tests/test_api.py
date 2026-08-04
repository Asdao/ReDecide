"""Walking-skeleton API tests for the two-stage RE:DECIDE flow."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from backend.app.main import app


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with (FIXTURES / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class ApiWalkingSkeletonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_health_exposes_fixture_mode(self) -> None:
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["mode"], "fixture")

    def test_openapi_exposes_only_the_walking_skeleton_paths(self) -> None:
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        paths = set(response.json()["paths"])
        self.assertEqual(
            paths,
            {
                "/api/health",
                "/api/samples",
                "/api/analyze",
                "/api/analyze-json",
            },
        )

    def test_samples_expose_aliases_before_analysis(self) -> None:
        response = self.client.get("/api/samples")

        self.assertEqual(response.status_code, 200)
        sample = response.json()["samples"][0]
        self.assertEqual(sample["sample_id"], "fixture-mirage-01")
        self.assertEqual(sample["players"], ["PlayerA"])
        self.assertTrue(sample["available"])

    def test_analyze_without_player_requests_player_selection(self) -> None:
        response = self.client.post(
            "/api/analyze", json={"sample_id": "fixture-mirage-01"}
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["stage"], "PLAYER_SELECTION_REQUIRED")
        self.assertEqual(payload["players"], ["PlayerA"])
        self.assertIsNone(payload["decision_packet"])
        self.assertIsNone(payload["neutral_summary"])

    def test_analyze_with_player_returns_neutral_packet_before_intent(self) -> None:
        response = self.client.post(
            "/api/analyze",
            json={"sample_id": "fixture-mirage-01", "player": "PlayerA"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["stage"], "INTENT_REQUIRED")
        self.assertEqual(
            payload["decision_packet"]["decision_type"], "POST_CONTACT_RESET"
        )
        self.assertNotIn("verdict", payload)
        self.assertNotIn("decision_card", payload)

    def test_analysis_id_can_continue_player_selection(self) -> None:
        response = self.client.post(
            "/api/analyze",
            json={
                "analysis_id": "sample:fixture-mirage-01",
                "player": "PlayerA",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stage"], "INTENT_REQUIRED")

    def test_analyze_json_requires_intent_and_returns_packet_plus_card(self) -> None:
        request_payload = load_fixture("analyze_json_request.valid.json")
        response = self.client.post("/api/analyze-json", json=request_payload)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["decision_packet"]["decision_id"],
            payload["decision_card"]["decision_id"],
        )
        available_ids = {
            item["evidence_id"]
            for item in payload["decision_packet"]["known_before_decision"]
        } | set(payload["decision_packet"]["observed_action"]["evidence_ids"])
        self.assertTrue(
            set(payload["decision_card"]["facts_used"]).issubset(available_ids)
        )

    def test_analyze_json_rejects_missing_intent(self) -> None:
        request_payload = load_fixture("analyze_json_request.valid.json")
        request_payload.pop("intent")

        response = self.client.post("/api/analyze-json", json=request_payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["error"]["code"], "CONTRACT_VALIDATION_FAILED"
        )
        self.assertFalse(response.json()["error"]["retryable"])

    def test_analyze_json_rejects_future_evidence(self) -> None:
        request_payload = load_fixture("analyze_json_request.valid.json")
        packet = request_payload["decision_packet"]
        packet["known_before_decision"][0]["tick"] = (
            packet["decision_open_tick"] + 1
        )

        response = self.client.post("/api/analyze-json", json=request_payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["error"]["code"], "CONTRACT_VALIDATION_FAILED"
        )

    def test_player_not_found_returns_typed_error(self) -> None:
        response = self.client.post(
            "/api/analyze",
            json={"sample_id": "fixture-mirage-01", "player": "EnemyName"},
        )

        self.assertEqual(response.status_code, 404)
        error = response.json()["error"]
        self.assertEqual(error["code"], "PLAYER_NOT_FOUND")
        self.assertFalse(error["retryable"])

    def test_noncanonical_packet_fails_safely_in_fixture_mode(self) -> None:
        request_payload = deepcopy(
            load_fixture("analyze_json_request.valid.json")
        )
        request_payload["decision_packet"]["decision_id"] = "other-decision"

        response = self.client.post("/api/analyze-json", json=request_payload)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "MODEL_UNAVAILABLE")

    def test_tampered_canonical_packet_fails_safely_in_fixture_mode(self) -> None:
        request_payload = deepcopy(
            load_fixture("analyze_json_request.valid.json")
        )
        request_payload["decision_packet"]["known_before_decision"][0][
            "value"
        ] = 99

        response = self.client.post("/api/analyze-json", json=request_payload)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "MODEL_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
