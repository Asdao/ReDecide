"""Focused tests for the standalone replay-to-JSON API."""

from __future__ import annotations

import importlib
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")


def test_vercel_replay_store_defaults_to_writable_temporary_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = importlib.import_module("backend.replay_api.store")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("REDECIDE_REPLAY_STORE", raising=False)

    assert store.replay_root() == Path(tempfile.gettempdir()) / "redecide" / "replays"


def test_visualization_payload_contains_all_players_positions_and_events() -> None:
    module = importlib.import_module("backend.replay_api.main")
    payload = module._visualization_payload(
        {
            "replay_id": "match-1",
            "demo_file": "match.dem",
            "header": {"map_name": "de_mirage", "tick_rate": 64},
            "rounds": [{"round_num": 1, "start": 10, "end": 100}],
            "ticks": [
                {"tick": 10, "steamid": "p1", "player_name": "A", "team_name": "CT", "X": 1},
                {"tick": 10, "steamid": "p2", "player_name": "B", "team_name": "T", "X": 2},
            ],
            "damages": [{"tick": 20, "attacker_steamid": "p1", "victim_steamid": "p2"}],
        }
    )

    assert payload["map"] == {"name": "de_mirage", "tick_rate": 64.0}
    assert {player["player_id"] for player in payload["players"]} == {"p1", "p2"}
    assert payload["ticks"][0]["X"] == 1
    assert payload["events"][0]["event"] == "damage"


def test_convert_parses_once_and_persists_two_branches(tmp_path: Any, monkeypatch: Any) -> None:
    module = importlib.import_module("backend.replay_api.main")
    monkeypatch.setenv("REDECIDE_REPLAY_STORE", str(tmp_path / "replays"))
    calls: list[Any] = []

    def load_once(path: Any) -> dict[str, Any]:
        calls.append(path)
        return {
            "demo_file": "match.dem",
            "header": {"map_name": "de_nuke", "tick_rate": 128},
            "ticks": [],
            "rounds": [],
            "damages": [],
        }

    monkeypatch.setattr(
        module,
        "_load_native_demo",
        load_once,
    )
    from fastapi.testclient import TestClient

    response = TestClient(module.create_app()).post(
        "/api/replay/convert",
        files={"file": ("match.dem", b"demo bytes", "application/octet-stream")},
    )

    assert response.status_code == 202
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["map"]["name"] == "de_nuke"
    assert len(calls) == 1
    replay_id = response.json()["replay_id"]
    artifact_dir = tmp_path / "replays" / replay_id
    assert (artifact_dir / "visualization.json").is_file()
    assert (artifact_dir / "coaching.json").is_file()


def test_upload_returns_players_before_full_visualization_json(tmp_path: Any, monkeypatch: Any) -> None:
    module = importlib.import_module("backend.replay_api.main")
    monkeypatch.setenv("REDECIDE_REPLAY_STORE", str(tmp_path / "replays"))
    monkeypatch.setattr(
        module,
        "_load_native_demo",
        lambda _path: {
            "demo_file": "match.dem",
            "header": {"map_name": "de_mirage", "tick_rate": 64},
            "rounds": [{"round_num": 1, "start": 10, "end": 100}],
            "ticks": [
                {"tick": 10, "steamid": "p1", "player_name": "A", "team_name": "CT", "X": 1},
                {"tick": 10, "steamid": "p2", "player_name": "B", "team_name": "T", "X": 2},
            ],
            "damages": [],
        },
    )
    from fastapi.testclient import TestClient

    client = TestClient(module.create_app())
    response = client.post(
        "/api/replay/upload",
        files={"file": ("match.dem", b"demo bytes", "application/octet-stream")},
    )

    assert response.status_code == 202
    manifest = response.json()
    assert {player["player_id"] for player in manifest["players"]} == {"p1", "p2"}
    assert manifest["coaching_status"] == "ready"
    replay_id = manifest["replay_id"]
    assert (tmp_path / "replays" / replay_id / "coaching.json").is_file()

    deadline = time.monotonic() + 2
    while True:
        status = client.get(f"/api/replay/{replay_id}/status")
        assert status.status_code == 200
        if status.json()["visualization_status"] == "ready":
            break
        assert time.monotonic() < deadline
        time.sleep(0.01)
    full_json = client.get(f"/api/replay/{replay_id}/json")
    assert full_json.status_code == 403
    from backend.replay_api.store import unlock_visualization

    unlock_visualization(replay_id)
    full_json = client.get(f"/api/replay/{replay_id}/json")
    assert full_json.status_code == 200
    assert full_json.json()["ticks"][0]["X"] == 1


def test_coaching_api_consumes_shared_coaching_branch(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("REDECIDE_REPLAY_STORE", str(tmp_path / "replays"))
    from backend.replay_api.store import save_replay_artifacts

    replay_id = "a" * 32
    coaching = {"replay_id": replay_id, "header": {}, "ticks": [], "rounds": []}
    save_replay_artifacts(replay_id, visualization={"replay_id": replay_id}, coaching=coaching)

    from fastapi.testclient import TestClient

    import backend.app.main as coaching_module

    captured: dict[str, Any] = {}

    class FakeService:
        def prepare(self, replay: Any, **_kwargs: Any) -> dict[str, Any]:
            captured["replay"] = replay
            return {"analysis_id": "analysis-1", "status": "processing"}

    response = TestClient(coaching_module.create_app(service=FakeService())).post(
        "/api/analysis/prepare",
        json={"replay_id": replay_id},
    )

    assert response.status_code == 202
    assert captured["replay"] == coaching
