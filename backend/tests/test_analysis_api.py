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

import pytest


pytest.importorskip("fastapi")
pytest.importorskip("httpx")


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
    from fastapi.testclient import TestClient

    return TestClient(app)


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
    deadline = time.monotonic() + 5
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
