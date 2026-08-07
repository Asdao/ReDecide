"""Tests for the transport-independent replay ingestion boundary."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from backend.replay_api.ingestion import (
    replay_manifest,
    start_replay,
    visualization_payload,
)
from backend.replay_api.store import load_replay_manifest


def _record() -> dict[str, Any]:
    return {
        "demo_file": "source.dem",
        "header": {"map_name": "de_nuke", "tick_rate": 128},
        "rounds": [{"round_num": 1, "start_tick": 5, "official_end": 25}],
        "ticks": [{"steamid": "p1", "player_name": "One", "team_name": "CT"}],
        "damages": [{"tick": 10, "attacker_steamid": "p1"}],
    }


def test_ingestion_builders_preserve_replay_contract() -> None:
    record = _record()
    manifest = replay_manifest(record, replay_id="a" * 32)
    payload = visualization_payload(record, replay_id="a" * 32)

    assert manifest["map"] == {"name": "de_nuke", "tick_rate": 128.0}
    assert manifest["rounds"] == [{"round_num": 1, "start": 5, "end": 25}]
    assert payload["events"][0]["event"] == "damage"


def test_visualization_drops_unassigned_player_snapshots() -> None:
    record = _record()
    record["ticks"] = [
        {"tick": 10, "steamid": "p1", "player_name": "One", "team_name": "CT"},
        {"tick": 10, "steamid": "spectator", "player_name": "Admin", "team_name": None},
        {"tick": 20, "steamid": "p2", "player_name": "Two", "side": "terrorist"},
    ]

    payload = visualization_payload(record, replay_id="a" * 32)

    assert [tick["steamid"] for tick in payload["ticks"]] == ["p1", "p2"]
    assert [tick["side"] for tick in payload["ticks"]] == ["ct", "t"]
    assert {player["player_id"] for player in payload["players"]} == {"p1", "p2"}


def test_start_replay_persists_coaching_and_manifest(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("REDECIDE_REPLAY_STORE", str(tmp_path / "replays"))
    with ThreadPoolExecutor(max_workers=1) as executor:
        manifest = start_replay(_record(), "uploaded.dem", executor)

    replay_id = manifest["replay_id"]
    persisted = load_replay_manifest(replay_id)
    assert persisted["source"] == "uploaded.dem"
    assert (tmp_path / "replays" / replay_id / "coaching.json").is_file()
