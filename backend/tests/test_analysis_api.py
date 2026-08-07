"""Two-stage API smoke test for the replay -> player -> coaching flow.

The test deliberately uses a tiny processed replay mapping instead of a native
``.dem`` file or a provider call.  It therefore exercises the transport and
job lifecycle deterministically while the replay and Pi connectors can evolve
independently.  If the API walking skeleton is not present yet, the module is
skipped so the existing contract/pipeline tests remain useful on a partial
checkout.
"""

from __future__ import annotations

import importlib
import json
import time
from typing import Any
from unittest.mock import patch

import pytest


pytest.importorskip("fastapi")
pytest.importorskip("httpx")


def _client_for_app(app: Any) -> Any:
    """Construct a TestClient lazily for optional FastAPI dependencies."""

    from fastapi.testclient import TestClient

    return TestClient(app)


def test_default_analysis_log_dir_uses_vercel_tmp(
    tmp_path: Any, monkeypatch: Any
) -> None:
    orchestration = importlib.import_module("backend.app.orchestration")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("REDECIDE_ANALYSIS_LOG_DIR", raising=False)
    monkeypatch.setattr(orchestration.tempfile, "gettempdir", lambda: str(tmp_path))

    service = orchestration.AnalysisService()

    assert service.log_dir == tmp_path / "redecide" / "analysis-logs"
    assert service.log_dir.is_dir()


def test_default_analysis_quota_is_ten(monkeypatch: Any) -> None:
    orchestration = importlib.import_module("backend.app.orchestration")
    monkeypatch.delenv("REDECIDE_ANALYSES_PER_PLAYER", raising=False)

    service = orchestration.AnalysisService()

    assert service.analyses_per_player == 10


def _load_client(tmp_path: Any) -> Any:
    """Return a TestClient for the application when the walking skeleton exists."""

    try:
        module = importlib.import_module("backend.app.main")
    except ModuleNotFoundError as exc:
        if exc.name in {"backend.app.main", "fastapi"}:
            pytest.skip("FastAPI walking skeleton is not implemented in this checkout")
        raise

    # Prefer a fresh service with a deterministic local coach adapter.  This
    # keeps the test independent of DeepSeek credentials and avoids sharing
    # the module-level in-memory job store across tests.
    create_app = getattr(module, "create_app", None)
    orchestration = importlib.import_module("backend.app.orchestration")
    service_type = getattr(orchestration, "AnalysisService", None)
    if create_app is not None and service_type is not None:
        service = service_type(
            log_dir=tmp_path,
            coach_adapter=lambda _result: {
                "decision_id": "decision_001",
                "what_could_be_done_better": (
                    "Break line of sight after first contact and wait for support."
                ),
            },
        )
        app = create_app(service=service)
    else:
        app = getattr(module, "app", None)
    if app is None:
        pytest.skip("backend.app.main does not expose an app instance")

    # Import lazily because older httpx/starlette combinations only fail when
    # TestClient is imported, and the rest of the repository does not require
    # this optional API test to run.
    return _client_for_app(app)


def _replay_json() -> dict[str, Any]:
    """Small JSON replay with two selectable players and one contact anchor."""

    return {
        "schema_version": 1,
        "replay_id": "api-flow-test",
        "demo_file": "api-flow-test.dem",
        "header": {"map_name": "de_mirage", "tick_rate": 64},
        "rounds": [{"round_num": 1, "start": 100, "end": 300, "winner": "CT"}],
        "damages": [
            {
                "round_num": 1,
                "tick": 164,
                "attacker_steamid": "t1",
                "victim_steamid": "ct1",
                "attacker_side": "T",
                "victim_side": "CT",
                "weapon": "ak47",
                "dmg_health": 20,
            }
        ],
        # Kills are markers only; first damage remains the coaching anchor.
        "kills": [
            {
                "round_num": 1,
                "tick": 240,
                "attacker_steamid": "t1",
                "victim_steamid": "ct1",
                "attacker_side": "T",
                "victim_side": "CT",
                "weapon": "ak47",
            }
        ],
        "ticks": [
            {
                "round_num": 1,
                "tick": 100,
                "steamid": "t1",
                "player_name": "T One",
                "team_name": "T",
                "health": 100,
                "alive": True,
                "X": 1,
                "Y": 1,
            },
            {
                "round_num": 1,
                "tick": 100,
                "steamid": "ct1",
                "player_name": "CT One",
                "team_name": "CT",
                "health": 100,
                "alive": True,
                "X": 2,
                "Y": 2,
            },
            {
                "round_num": 1,
                "tick": 164,
                "steamid": "t1",
                "player_name": "T One",
                "team_name": "T",
                "health": 100,
                "alive": True,
                "X": 1,
                "Y": 1,
            },
            {
                "round_num": 1,
                "tick": 164,
                "steamid": "ct1",
                "player_name": "CT One",
                "team_name": "CT",
                "health": 80,
                "alive": True,
                "X": 2,
                "Y": 2,
            },
        ],
    }


def _two_player_replay_json() -> dict[str, Any]:
    """Replay fixture with two coachable players so repeated runs can differ."""

    return {
        "schema_version": 1,
        "replay_id": "api-flow-test-two-players",
        "demo_file": "api-flow-test-two-players.dem",
        "header": {"map_name": "de_mirage", "tick_rate": 64},
        "rounds": [
            {"round_num": 1, "start": 100, "end": 300, "winner": "CT"},
            {"round_num": 2, "start": 400, "end": 620, "winner": "T"},
        ],
        "damages": [
            {
                "round_num": 1,
                "tick": 164,
                "attacker_steamid": "t1",
                "victim_steamid": "ct1",
                "attacker_side": "T",
                "victim_side": "CT",
                "weapon": "ak47",
                "dmg_health": 20,
            },
            {
                "round_num": 2,
                "tick": 464,
                "attacker_steamid": "ct1",
                "victim_steamid": "t1",
                "attacker_side": "CT",
                "victim_side": "T",
                "weapon": "m4a1",
                "dmg_health": 18,
            },
        ],
        "kills": [
            {
                "round_num": 1,
                "tick": 240,
                "attacker_steamid": "t1",
                "victim_steamid": "ct1",
                "attacker_side": "T",
                "victim_side": "CT",
                "weapon": "ak47",
            },
            {
                "round_num": 2,
                "tick": 540,
                "attacker_steamid": "ct1",
                "victim_steamid": "t1",
                "attacker_side": "CT",
                "victim_side": "T",
                "weapon": "m4a1",
            },
        ],
        "ticks": [
            {
                "round_num": 1,
                "tick": 100,
                "steamid": "t1",
                "player_name": "T One",
                "team_name": "T",
                "health": 100,
                "alive": True,
                "X": 1,
                "Y": 1,
            },
            {
                "round_num": 1,
                "tick": 100,
                "steamid": "ct1",
                "player_name": "CT One",
                "team_name": "CT",
                "health": 100,
                "alive": True,
                "X": 2,
                "Y": 2,
            },
            {
                "round_num": 1,
                "tick": 164,
                "steamid": "t1",
                "player_name": "T One",
                "team_name": "T",
                "health": 100,
                "alive": True,
                "X": 1,
                "Y": 1,
            },
            {
                "round_num": 1,
                "tick": 164,
                "steamid": "ct1",
                "player_name": "CT One",
                "team_name": "CT",
                "health": 80,
                "alive": True,
                "X": 2,
                "Y": 2,
            },
            {
                "round_num": 2,
                "tick": 400,
                "steamid": "t1",
                "player_name": "T One",
                "team_name": "T",
                "health": 100,
                "alive": True,
                "X": 3,
                "Y": 3,
            },
            {
                "round_num": 2,
                "tick": 400,
                "steamid": "ct1",
                "player_name": "CT One",
                "team_name": "CT",
                "health": 100,
                "alive": True,
                "X": 4,
                "Y": 4,
            },
            {
                "round_num": 2,
                "tick": 464,
                "steamid": "t1",
                "player_name": "T One",
                "team_name": "T",
                "health": 82,
                "alive": True,
                "X": 3,
                "Y": 3,
            },
            {
                "round_num": 2,
                "tick": 464,
                "steamid": "ct1",
                "player_name": "CT One",
                "team_name": "CT",
                "health": 100,
                "alive": True,
                "X": 4,
                "Y": 4,
            },
        ],
    }


def _no_candidate_replay_json() -> dict[str, Any]:
    """Replay fixture with players but no decision candidates for them."""

    return {
        "schema_version": 1,
        "replay_id": "api-flow-test-no-candidates",
        "demo_file": "api-flow-test-no-candidates.dem",
        "header": {"map_name": "de_mirage", "tick_rate": 64},
        "rounds": [{"round_num": 1, "start": 100, "end": 300, "winner": "CT"}],
        "damages": [],
        "kills": [],
        "ticks": [
            {
                "round_num": 1,
                "tick": 100,
                "steamid": "t1",
                "player_name": "T One",
                "team_name": "T",
                "health": 100,
                "alive": True,
                "X": 1,
                "Y": 1,
            },
            {
                "round_num": 1,
                "tick": 100,
                "steamid": "ct1",
                "player_name": "CT One",
                "team_name": "CT",
                "health": 100,
                "alive": True,
                "X": 2,
                "Y": 2,
            },
            {
                "round_num": 1,
                "tick": 164,
                "steamid": "t1",
                "player_name": "T One",
                "team_name": "T",
                "health": 100,
                "alive": True,
                "X": 1,
                "Y": 1,
            },
            {
                "round_num": 1,
                "tick": 164,
                "steamid": "ct1",
                "player_name": "CT One",
                "team_name": "CT",
                "health": 100,
                "alive": True,
                "X": 2,
                "Y": 2,
            },
        ],
    }


def _prepare_and_wait_for_players(
    client: Any, replay: dict[str, Any] | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """Submit the fixture and wait for the asynchronous selector to be ready."""

    prepared = client.post(
        "/api/analysis/prepare",
        json={"replay": replay or _replay_json()},
    )
    assert prepared.status_code in (200, 202), prepared.text
    analysis_id = prepared.json()["analysis_id"]
    deadline = time.monotonic() + 20
    while True:
        response = client.get(f"/api/analysis/{analysis_id}/players")
        if response.status_code == 200:
            return analysis_id, response.json()["players"]
        assert response.status_code == 202, response.text
        assert time.monotonic() < deadline, "player selector did not become ready"
        time.sleep(0.01)


def test_json_prepare_player_selection_and_output(tmp_path: Any) -> None:
    """Simulate one JSON upload, selector choice, coaching, and log retrieval."""

    client = _load_client(tmp_path)

    prepared = client.post("/api/analysis/prepare", json={"replay": _replay_json()})
    assert prepared.status_code in (200, 202), prepared.text
    prepared_body = prepared.json()
    analysis_id = prepared_body["analysis_id"]
    assert prepared_body["status"] in {"prepared", "processing", "ready"}

    # Preparation is deliberately asynchronous so the same job can stream
    # progress to the UI.  Wait for the selector, without uploading again.
    deadline = time.monotonic() + 20
    while True:
        players_response = client.get(f"/api/analysis/{analysis_id}/players")
        if players_response.status_code == 200:
            break
        assert players_response.status_code == 202, players_response.text
        assert time.monotonic() < deadline, "player selector did not become ready"
        time.sleep(0.01)
    players_body = players_response.json()
    players = players_body["players"]
    assert {player["display_name"] for player in players} == {"CT One", "T One"}
    selected = next(player for player in players if player["display_name"] == "T One")
    assert selected["player_id"] == "t1"
    assert selected["decision_ids"]

    run = client.post(
        f"/api/analysis/{analysis_id}/run",
        # The UI's second input is the selected display name.  The API also
        # exposes the stable player_id in the selector for callers that need
        # to disambiguate duplicate names.
        json={"player_name": selected["display_name"]},
    )
    assert run.status_code in (200, 202), run.text

    result = client.get(f"/api/analysis/{analysis_id}/result")
    assert result.status_code == 200, result.text
    result_body = result.json()
    assert result_body["selected_decision"]["player_id"] == selected["player_id"]
    assert result_body["selected_decision"]["player_name"] == "T One"
    assert result_body["coach_analysis"]["player_name"] == "T One"
    assert result_body["coach_analysis"]["player_id"] == "t1"
    assert result_body["win_estimator"]["scope"] == "global_team_probability"
    assert result_body["win_estimator"]["filtered_by_player"] is False
    assert all(
        event["event_id"] in selected["event_ids"]
        for event in result_body.get("events", [])
        if event.get("participant_ids") and "t1" in event["participant_ids"]
    )

    progress_stream = client.get(f"/api/analysis/{analysis_id}/events")
    assert progress_stream.status_code == 200, progress_stream.text
    assert "event: complete" in progress_stream.text

    logs = client.get(f"/api/analysis/{analysis_id}/logs")
    assert logs.status_code == 200, logs.text
    assert logs.headers.get("content-type", "").startswith("text/plain")
    lines = [line for line in logs.text.splitlines() if line.strip()]
    assert lines, "the API must persist at least one JSONL progress/log record"
    records = [json.loads(line) for line in lines]
    assert all(record.get("analysis_id") == analysis_id for record in records)
    progress = [record["progress"] for record in records if "progress" in record]
    assert progress == sorted(progress)
    assert records[-1]["stage"] in {"complete", "completed"}
    assert (tmp_path / f"{analysis_id}.jsonl").is_file()


def test_default_fastapi_app_constructs_the_pi_adapter() -> None:
    """The production app fills the coach adapter slot by default."""

    module = importlib.import_module("backend.app.main")
    sentinel = object()
    with (
        patch.object(module, "PiCoachAdapter", return_value=sentinel) as adapter_type,
        patch.object(module, "AnalysisService") as service_type,
    ):
        module.create_app()
    adapter_type.assert_called_once_with()
    service_type.assert_called_once_with(coach_adapter=sentinel)


def test_health_and_unknown_analysis_routes_have_stable_http_errors(tmp_path: Any) -> None:
    client = _load_client(tmp_path)

    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/analysis/missing").status_code == 404
    assert client.get("/api/analysis/missing/players").status_code == 404
    assert client.post("/api/analysis/missing/run", json={"player_id": "t1"}).status_code == 404
    assert client.get("/api/analysis/missing/result").status_code == 404
    assert client.get("/api/analysis/missing/logs").status_code == 404
    assert client.get("/api/analysis/missing/events").status_code == 404


def test_prepare_rejects_non_object_replay_payload(tmp_path: Any) -> None:
    client = _load_client(tmp_path)

    response = client.post("/api/analysis/prepare", json={"replay": []})

    assert response.status_code == 422


def test_player_selection_requires_one_valid_player_and_accepts_stable_id(tmp_path: Any) -> None:
    client = _load_client(tmp_path)
    analysis_id, players = _prepare_and_wait_for_players(client)
    selected = next(player for player in players if player["decision_ids"])

    missing = client.post(f"/api/analysis/{analysis_id}/run", json={})
    assert missing.status_code == 422
    unknown = client.post(
        f"/api/analysis/{analysis_id}/run", json={"player_id": "not-a-player"}
    )
    assert unknown.status_code == 422

    run = client.post(
        f"/api/analysis/{analysis_id}/run",
        json={"player_id": selected["player_id"]},
    )
    assert run.status_code == 200, run.text
    assert run.json()["selected_decision"]["player_id"] == selected["player_id"]


def test_repeated_player_runs_keep_results_scoped_to_each_selection(
    tmp_path: Any,
) -> None:
    calls: list[str] = []

    def adapter(payload: dict[str, Any]) -> dict[str, str]:
        player_id = payload["selected_decision"]["player_id"]
        calls.append(player_id)
        return {
            "decision_id": "decision_001",
            "what_could_be_done_better": f"Coach feedback for {player_id}.",
        }

    orchestration = importlib.import_module("backend.app.orchestration")
    service = orchestration.AnalysisService(
        log_dir=tmp_path,
        coach_adapter=adapter,
    )
    module = importlib.import_module("backend.app.main")
    client = _client_for_app(module.create_app(service=service))
    analysis_id, players = _prepare_and_wait_for_players(client, _two_player_replay_json())
    players_with_candidates = [player for player in players if player["decision_ids"]]
    assert len(players_with_candidates) >= 2, players

    player_a, player_b = players_with_candidates[:2]

    run_a = client.post(
        f"/api/analysis/{analysis_id}/run",
        json={"player_id": player_a["player_id"]},
    )
    assert run_a.status_code == 200, run_a.text
    body_a = run_a.json()
    result_a = client.get(f"/api/analysis/{analysis_id}/result")
    assert result_a.status_code == 200, result_a.text

    run_b = client.post(
        f"/api/analysis/{analysis_id}/run",
        json={"player_id": player_b["player_id"]},
    )
    assert run_b.status_code == 200, run_b.text
    body_b = run_b.json()
    result_b = client.get(f"/api/analysis/{analysis_id}/result")
    assert result_b.status_code == 200, result_b.text
    historical_a = client.get(
        f"/api/analysis/{analysis_id}/result",
        params={"player_id": player_a["player_id"]},
    )
    assert historical_a.status_code == 200, historical_a.text

    assert calls == [player_a["player_id"], player_b["player_id"]]
    assert body_a["selected_decision"]["player_id"] == player_a["player_id"]
    assert result_a.json()["selected_decision"]["player_id"] == player_a["player_id"]
    assert body_b["selected_decision"]["player_id"] == player_b["player_id"]
    assert result_b.json()["selected_decision"]["player_id"] == player_b["player_id"]
    assert historical_a.json()["selected_decision"]["player_id"] == player_a["player_id"]
    assert body_a["coach_analysis"]["decision_id"] != body_b["coach_analysis"]["decision_id"]
    assert body_a["coach_analysis"]["player_id"] == player_a["player_id"]
    assert body_b["coach_analysis"]["player_id"] == player_b["player_id"]


def test_final_result_is_not_available_before_player_selection(tmp_path: Any) -> None:
    client = _load_client(tmp_path)
    analysis_id, _players = _prepare_and_wait_for_players(client)

    response = client.get(f"/api/analysis/{analysis_id}/result")

    assert response.status_code == 202


def test_fastapi_passes_selected_player_result_to_adapter_and_merges_output(
    tmp_path: Any,
) -> None:
    captured: dict[str, Any] = {}

    def adapter(payload: dict[str, Any]) -> dict[str, str]:
        captured.update(payload)
        return {
            "decision_id": "decision_001",
            "what_could_be_done_better": "Reset behind cover before re-engaging.",
        }

    orchestration = importlib.import_module("backend.app.orchestration")
    service = orchestration.AnalysisService(log_dir=tmp_path, coach_adapter=adapter)
    module = importlib.import_module("backend.app.main")
    client = _client_for_app(module.create_app(service=service))
    analysis_id, players = _prepare_and_wait_for_players(client)
    selected = next(player for player in players if player["decision_ids"])

    response = client.post(
        f"/api/analysis/{analysis_id}/run",
        json={"player_id": selected["player_id"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert captured["selected_decision"]["player_id"] == selected["player_id"]
    assert all(
        selected["player_id"] in event.get("participant_ids", [])
        for event in captured.get("events", [])
    )
    assert captured["win_estimator"]["filtered_by_player"] is False
    assert body["coach_analysis"]["source"] == "pi"
    assert body["coach_analysis"]["decision_id"] == body["selected_decision"]["decision_id"]
    assert body["coach_analysis"]["what_could_be_done_better"].startswith("Reset")
    assert body["replay_outcome"]["eventual_winner"] == "CT"
    assert body["replay_outcome"]["round_score"] == {"CT": 1, "T": 0}


def test_adapter_failure_is_exposed_as_service_unavailable_and_failed_job(
    tmp_path: Any,
) -> None:
    def failing_adapter(_payload: dict[str, Any]) -> dict[str, str]:
        raise RuntimeError("provider unavailable")

    orchestration = importlib.import_module("backend.app.orchestration")
    service = orchestration.AnalysisService(log_dir=tmp_path, coach_adapter=failing_adapter)
    module = importlib.import_module("backend.app.main")
    client = _client_for_app(module.create_app(service=service))
    analysis_id, players = _prepare_and_wait_for_players(client)
    selected = next(player for player in players if player["decision_ids"])

    run = client.post(
        f"/api/analysis/{analysis_id}/run",
        json={"player_id": selected["player_id"]},
    )

    assert run.status_code == 503
    assert run.json()["detail"] == "coaching analysis failed"
    metadata = client.get(f"/api/analysis/{analysis_id}")
    assert metadata.json()["status"] == "failed"
    result = client.get(f"/api/analysis/{analysis_id}/result")
    assert result.status_code == 500


def test_safe_pi_adapter_failure_reason_is_preserved(tmp_path: Any) -> None:
    from backend.app.coach.pi_connector import PiCoachError

    def failing_adapter(_payload: dict[str, Any]) -> dict[str, str]:
        raise PiCoachError("agent-harness dependencies are not installed")

    orchestration = importlib.import_module("backend.app.orchestration")
    service = orchestration.AnalysisService(log_dir=tmp_path, coach_adapter=failing_adapter)
    module = importlib.import_module("backend.app.main")
    client = _client_for_app(module.create_app(service=service))
    analysis_id, players = _prepare_and_wait_for_players(client)
    selected = next(player for player in players if player["decision_ids"])

    run = client.post(
        f"/api/analysis/{analysis_id}/run",
        json={"player_id": selected["player_id"]},
    )

    assert run.status_code == 503
    assert run.json()["detail"] == (
        "coaching analysis failed: agent-harness dependencies are not installed"
    )


def test_player_without_decision_candidates_returns_clear_422(tmp_path: Any) -> None:
    client = _load_client(tmp_path)
    analysis_id, players = _prepare_and_wait_for_players(
        client, _no_candidate_replay_json()
    )
    selected = next(player for player in players if not player["decision_ids"])

    run = client.post(
        f"/api/analysis/{analysis_id}/run",
        json={"player_id": selected["player_id"]},
    )

    assert run.status_code == 422, run.text
    assert run.json()["detail"] == "selected player has no first-contact decision candidate"


def test_preparation_failure_logs_the_internal_exception_but_keeps_public_state_safe(
    tmp_path: Any, caplog: Any
) -> None:
    def failing_pipeline(_replay: dict[str, Any]) -> Any:
        raise ValueError("specific parser invariant failed")
        yield  # pragma: no cover - makes this callable an iterator pipeline

    orchestration = importlib.import_module("backend.app.orchestration")
    service = orchestration.AnalysisService(
        log_dir=tmp_path, pipeline=failing_pipeline
    )

    with caplog.at_level("ERROR", logger="backend.app.orchestration"):
        metadata = service.prepare({"replay_id": "cached-sample"})

    analysis_id = metadata["analysis_id"]
    assert metadata["status"] == "failed"
    assert service.get_job(analysis_id).error == "replay preparation failed"
    assert "specific parser invariant failed" in caplog.text
    assert "specific parser invariant failed" not in service.logs(analysis_id)
    assert '"message":"replay preparation failed"' in service.logs(analysis_id)
