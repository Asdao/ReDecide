"""API regressions for exact, outcome-blind intent coaching."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.coach.pi_connector import PiCoachError, PiCoachTimeoutError
from backend.app.main import create_analysis_app
from backend.app.orchestration import AnalysisJob, AnalysisService


PLAYER_ID = "player-1"
FIRST_DECISION_ID = "r1:pplayer-1:t100"
SECOND_DECISION_ID = "r2:pplayer-1:t500"


class PromptProvider:
    """Deterministic provider double that preserves the production seam."""

    def __init__(self, response: str | Exception | None = None) -> None:
        self.response = response or json.dumps(
            {
                "intent_assessment": "NOT_ESTABLISHED",
                "coordination_assessment": "NOT_ESTABLISHED",
                "recommended_adjustment": "RESET_BEHIND_COVER",
                "evidence_claims": [
                    {
                        "evidence_id": "decision:observed-action",
                        "supports": "recommended_cs2_adjustment",
                    },
                    {
                        "evidence_id": "decision:observed-action",
                        "supports": "in_depth_coaching",
                    }
                ],
            }
        )
        self.prompts: list[str] = []

    def __call__(self, _pipeline_result: dict[str, Any]) -> dict[str, str]:
        return {
            "decision_id": "decision_001",
            "what_could_be_done_better": "Reset behind cover before re-engaging.",
        }

    def run_prompt(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _decision(
    decision_id: str,
    *,
    round_number: int,
    tick: int,
) -> dict[str, Any]:
    return {
        "decision_id": decision_id,
        "round_number": round_number,
        "player_id": PLAYER_ID,
        "opponent_id": "opponent-1",
        "decision_open_tick": tick,
        "contact_tick": tick,
        "action_close_tick": tick + 20,
        "event_category": "damage",
        "observed_action": "RESET_REPOSITION",
        "evidence": ["displacement_above_threshold"],
    }


def _completed_result(*, include_evidence: bool = True) -> dict[str, Any]:
    first = _decision(FIRST_DECISION_ID, round_number=1, tick=100)
    second = _decision(SECOND_DECISION_ID, round_number=2, tick=500)
    key_events: list[dict[str, Any]] = []
    if include_evidence:
        key_events.extend(
            [
                {
                    "event_id": "event-first-contact",
                    "round_number": 1,
                    "tick": 100,
                    "event_type": "damage",
                    "participant_ids": [PLAYER_ID, "opponent-1"],
                    "is_coaching_anchor": True,
                },
                {
                    "event_id": "event-second-contact",
                    "round_number": 2,
                    "tick": 490,
                    "event_type": "damage",
                    "participant_ids": [PLAYER_ID, "opponent-1"],
                    "is_coaching_anchor": True,
                },
                {
                    "event_id": "future-death-must-not-leak",
                    "round_number": 2,
                    "tick": 510,
                    "event_type": "kill",
                    "participant_ids": [PLAYER_ID, "opponent-1"],
                    "is_coaching_anchor": False,
                },
            ]
        )
    else:
        for decision in (first, second):
            decision["observed_action"] = "unknown"
            decision["evidence"] = ["no_action_window_observation"]
    return {
        "schema_version": "replay_analysis_v1",
        "selected_decision": first,
        "analyses": [
            {"selected_decision": first, "coach_analysis": {}},
            {"selected_decision": second, "coach_analysis": {}},
        ],
        "key_events": key_events,
        "win_estimator": {
            "timeline": [
                {"tick": 490, "ct_probability": 0.5, "t_probability": 0.5},
                {"tick": 525, "ct_probability": 0.1, "t_probability": 0.9},
            ]
        },
    }


def _client(
    tmp_path: Path,
    provider: PromptProvider,
    *,
    run_status: str = "complete",
    include_result: bool = True,
    include_evidence: bool = True,
) -> TestClient:
    service = AnalysisService(log_dir=tmp_path, coach_adapter=provider)
    analysis_id = "analysis-1"
    result = _completed_result(include_evidence=include_evidence)
    job = AnalysisJob(
        analysis_id=analysis_id,
        replay={"map": {"name": "de_inferno"}},
        log_path=tmp_path / "analysis-1.jsonl",
        status="complete" if run_status == "complete" else "coaching",
        selected_player_id=PLAYER_ID,
        result=result if include_result else None,
        player_runs={
            PLAYER_ID: {
                "run_id": "run-1",
                "status": run_status,
                "result": result if include_result else None,
                "error": None,
            }
        },
    )
    with service._jobs_lock:  # noqa: SLF001 - construct a restored job boundary
        service._jobs[analysis_id] = job  # noqa: SLF001
    return TestClient(create_analysis_app(service=service))


def _request(
    client: TestClient,
    *,
    analysis_id: str = "analysis-1",
    body_analysis_id: str | None = None,
    player_id: str = PLAYER_ID,
    decision_id: str = SECOND_DECISION_ID,
) -> Any:
    return client.post(
        f"/api/analysis/{analysis_id}/intent",
        json={
            "analysis_id": body_analysis_id or analysis_id,
            "player_id": player_id,
            "decision_id": decision_id,
            "intent_text": "I wanted to reset and wait for support.",
        },
    )


def test_endpoint_uses_exact_requested_decision_and_excludes_future_events(
    tmp_path: Path,
) -> None:
    provider = PromptProvider()
    response = _request(_client(tmp_path, provider))

    assert response.status_code == 200, response.text
    assert response.json()["decision_id"] == SECOND_DECISION_ID
    assert response.json()["knowledge_cutoff_tick"] == 520
    assert response.json()["facts_referenced"] == ["decision:observed-action"]
    assert len(provider.prompts) == 1
    assert "event-second-contact" in provider.prompts[0]
    assert FIRST_DECISION_ID not in provider.prompts[0]
    assert "event-first-contact" not in provider.prompts[0]
    assert "future-death-must-not-leak" not in provider.prompts[0]


@pytest.mark.parametrize(
    ("player_id", "decision_id"),
    [
        ("unknown-player", SECOND_DECISION_ID),
        (PLAYER_ID, "unknown-decision"),
        (PLAYER_ID, FIRST_DECISION_ID + "-wrong"),
    ],
)
def test_unknown_player_or_decision_is_not_coached(
    tmp_path: Path,
    player_id: str,
    decision_id: str,
) -> None:
    provider = PromptProvider()
    response = _request(
        _client(tmp_path, provider),
        player_id=player_id,
        decision_id=decision_id,
    )

    assert response.status_code == 404
    assert provider.prompts == []


def test_incomplete_player_run_returns_conflict_without_calling_provider(
    tmp_path: Path,
) -> None:
    provider = PromptProvider()
    response = _request(
        _client(
            tmp_path,
            provider,
            run_status="running",
            include_result=False,
        )
    )

    assert response.status_code == 409
    assert provider.prompts == []


def test_provider_failure_returns_service_unavailable_without_fake_coaching(
    tmp_path: Path,
) -> None:
    provider = PromptProvider(PiCoachError("provider failed"))
    response = _request(_client(tmp_path, provider))

    assert response.status_code == 503
    assert "in_depth_coaching" not in response.json()
    assert "line of sight" not in response.text.lower()


def test_provider_timeout_returns_gateway_timeout(tmp_path: Path) -> None:
    provider = PromptProvider(PiCoachTimeoutError("provider timed out"))
    response = _request(_client(tmp_path, provider))

    assert response.status_code == 504
    assert "in_depth_coaching" not in response.json()


def test_malformed_or_ungrounded_model_output_fails_closed(tmp_path: Path) -> None:
    provider = PromptProvider(
        json.dumps(
            {
                "intent_assessment": "NOT_ESTABLISHED",
                "coordination_assessment": "NOT_ESTABLISHED",
                "recommended_adjustment": "RESET_BEHIND_COVER",
                "evidence_claims": [
                    {
                        "evidence_id": "invented-fact",
                        "supports": "recommended_cs2_adjustment",
                    },
                    {
                        "evidence_id": "invented-fact",
                        "supports": "in_depth_coaching",
                    }
                ],
            }
        )
    )
    response = _request(_client(tmp_path, provider))

    assert response.status_code == 503


def test_no_citable_evidence_returns_unprocessable_without_provider_call(
    tmp_path: Path,
) -> None:
    provider = PromptProvider()
    response = _request(_client(tmp_path, provider, include_evidence=False))

    assert response.status_code == 422
    assert provider.prompts == []


def test_path_and_body_analysis_ids_must_match(tmp_path: Path) -> None:
    provider = PromptProvider()
    response = _request(
        _client(tmp_path, provider),
        body_analysis_id="different-analysis",
    )

    assert response.status_code == 400
    assert provider.prompts == []


def test_unknown_analysis_returns_not_found(tmp_path: Path) -> None:
    provider = PromptProvider()
    response = _request(
        _client(tmp_path, provider),
        analysis_id="missing-analysis",
    )

    assert response.status_code == 404
    assert provider.prompts == []
