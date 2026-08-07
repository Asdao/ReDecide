"""Tests for the hosted sample's real replay-ingestion boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.sample_replay import QUICK_SAMPLE_ID, BlobSampleReplay


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


def _sample(
    tmp_path: Path,
    calls: list[str],
    *,
    cache_version: str | None = None,
    expected_sha256: str | None = None,
) -> BlobSampleReplay:
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
        expected_sha256=expected_sha256,
        cache_version=cache_version,
    )


def test_public_sample_selection_runs_ingestion_and_analysis(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("REDECIDE_REPLAY_STORE", str(tmp_path / "replays"))
    calls: list[str] = []
    service = FakeAnalysisService()
    client = TestClient(
        create_app(service=service, sample_replay=_sample(tmp_path, calls))
    )

    samples = client.get("/api/samples")
    assert samples.status_code == 200
    assert samples.json() == {
        "samples": [
            {
                "sample_id": "sample-ancient",
                "display_name": "3DMAX vs Falcons",
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


def test_sample_cache_version_changes_the_deterministic_replay_id(
    tmp_path: Path,
) -> None:
    first = _sample(tmp_path, [], cache_version="pipeline-v1")
    second = _sample(tmp_path, [], cache_version="pipeline-v2")

    assert first.replay_id != second.replay_id
    assert first.cache_fingerprint != second.cache_fingerprint


def test_sample_ignores_cached_artifacts_with_stale_metadata(
    tmp_path: Path, monkeypatch: Any
) -> None:
    replay_root = tmp_path / "replays"
    monkeypatch.setenv("REDECIDE_REPLAY_STORE", str(replay_root))
    calls: list[str] = []
    sample = _sample(tmp_path, calls, cache_version="pipeline-v2")
    client = TestClient(
        create_app(service=FakeAnalysisService(), sample_replay=sample)
    )

    first = client.post("/api/analyze", json={"sample_id": sample.sample_id})
    assert first.status_code == 200, first.text
    coaching_path = replay_root / sample.replay_id / "coaching.json"
    coaching = json.loads(coaching_path.read_text(encoding="utf-8"))
    coaching["_sample_cache"]["cache_version"] = "pipeline-v1"
    coaching_path.write_text(json.dumps(coaching), encoding="utf-8")

    second = client.post("/api/analyze", json={"sample_id": sample.sample_id})

    assert second.status_code == 200, second.text
    assert calls == ["download", "download"]
    repaired = json.loads(coaching_path.read_text(encoding="utf-8"))
    assert repaired["_sample_cache"] == sample.cache_metadata


def test_sample_rejects_a_seed_with_the_wrong_digest(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("REDECIDE_REPLAY_STORE", str(tmp_path / "replays"))
    sample = _sample(tmp_path, [], expected_sha256="0" * 64)
    client = TestClient(
        create_app(service=FakeAnalysisService(), sample_replay=sample)
    )

    response = client.post("/api/analyze", json={"sample_id": sample.sample_id})

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "hosted sample digest did not match the expected seed"
    )


def test_public_sample_catalog_supports_selecting_the_quick_hosted_demo(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("REDECIDE_REPLAY_STORE", str(tmp_path / "replays"))
    calls: list[str] = []
    service = FakeAnalysisService()
    primary = _sample(tmp_path, calls)

    async def download_quick(_url: str, destination: Path, _limit: int) -> None:
        calls.append("download-quick")
        destination.write_bytes(b"quick seed")

    quick = BlobSampleReplay(
        url="https://store123.public.blob.vercel-storage.com/quick.dem",
        sample_id="sample-ancient-20mb",
        filename="quick.dem",
        display_name="3DMAX vs Falcons LITE",
        downloader=download_quick,
        loader=lambda _path: _record(),
        max_bytes=100,
        expected_bytes=None,
    )
    client = TestClient(create_app(service=service, sample_replay=(primary, quick)))

    samples = client.get("/api/samples")
    assert samples.status_code == 200
    assert [sample["sample_id"] for sample in samples.json()["samples"]] == [
        "sample-ancient",
        "sample-ancient-20mb",
    ]
    assert [sample["display_name"] for sample in samples.json()["samples"]] == [
        "3DMAX vs Falcons",
        "3DMAX vs Falcons LITE",
    ]

    response = client.post("/api/analyze", json={"sample_id": "sample-ancient-20mb"})
    assert response.status_code == 200, response.text
    assert response.json()["sample_id"] == "sample-ancient-20mb"
    assert calls == ["download-quick"]


def test_quick_hosted_demo_is_only_listed_on_vercel(monkeypatch: Any) -> None:
    service = FakeAnalysisService()

    monkeypatch.delenv("VERCEL", raising=False)
    local_samples = TestClient(create_app(service=service)).get("/api/samples")
    assert [sample["sample_id"] for sample in local_samples.json()["samples"]] == [
        "3dmax-vs-falcons-m2-ancient"
    ]

    monkeypatch.setenv("VERCEL", "1")
    vercel_samples = TestClient(create_app(service=service)).get("/api/samples")
    assert [sample["sample_id"] for sample in vercel_samples.json()["samples"]] == [
        "3dmax-vs-falcons-m2-ancient",
        QUICK_SAMPLE_ID,
    ]
