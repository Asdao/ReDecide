"""Tests for the hosted sample's real replay-ingestion boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.sample_replay import BlobSampleReplay


def _record() -> dict[str, Any]:
    return {
        "demo_file": "seed.dem",
        "header": {"map_name": "de_ancient", "tick_rate": 64},
        "rounds": [{"round_num": 1, "start": 1, "end": 20}],
        "ticks": [{"steamid": "p1", "player_name": "Player One", "team_name": "CT"}],
        "damages": [],
    }


class FakeAnalysisService:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def prepare(self, replay: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        self.calls.append((replay, kwargs))
        return {
            "analysis_id": "analysis-sample-1",
            "status": "ready",
            "players_available": True,
        }


def _sample(tmp_path: Path, calls: list[str]) -> BlobSampleReplay:
    async def download(_url: str, destination: Path, _limit: int) -> None:
        calls.append("download")
        destination.write_bytes(b"seed")

    return BlobSampleReplay(
        url="https://store123.public.blob.vercel-storage.com/sample.dem",
        sample_id="sample-ancient",
        filename="sample.dem",
        downloader=download,
        loader=lambda _path: _record(),
        max_bytes=100,
        expected_bytes=None,
    )


def test_public_sample_selection_runs_ingestion_and_analysis(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("REDECIDE_REPLAY_STORE", str(tmp_path / "replays"))
    calls: list[str] = []
    service = FakeAnalysisService()
    client = TestClient(create_app(service=service, sample_replay=_sample(tmp_path, calls)))

    samples = client.get("/api/samples")
    assert samples.status_code == 200
    assert samples.json() == {
        "samples": [
            {
                "sample_id": "sample-ancient",
                "display_name": "3DMAX vs Falcons — Ancient",
                "description": "Ancient match sample prepared from the hosted replay.",
                "map": "de_ancient",
                "players": [],
                "recommended_player": None,
                "available": True,
            }
        ]
    }

    response = client.post("/api/analyze", json={"sample_id": "sample-ancient"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["sample_id"] == "sample-ancient"
    assert payload["replay_id"] == payload["manifest"]["replay_id"]
    assert payload["analysis"]["analysis_id"] == "analysis-sample-1"
    assert payload["manifest"]["visualization_status"] == "ready"
    assert calls == ["download"]
    assert service.calls[0][1]["source_replay_id"] == payload["replay_id"]


def test_public_sample_reuses_cached_artifacts_without_downloading(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("REDECIDE_REPLAY_STORE", str(tmp_path / "replays"))
    calls: list[str] = []
    service = FakeAnalysisService()
    sample = _sample(tmp_path, calls)
    client = TestClient(create_app(service=service, sample_replay=sample))

    first = client.post("/api/analyze", json={"sample_id": "sample-ancient"})
    assert first.status_code == 200

    def unexpected_download(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("cached sample should not download the raw seed")

    sample.downloader = unexpected_download  # type: ignore[assignment]
    second = client.post("/api/analyze", json={"sample_id": "sample-ancient"})
    assert second.status_code == 200, second.text
    assert second.json()["replay_id"] == first.json()["replay_id"]
    assert calls == ["download"]
