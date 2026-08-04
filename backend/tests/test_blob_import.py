"""Tests for the disabled-by-default public Vercel Blob import route."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


PUBLIC_BLOB_URL = (
    "https://store123.public.blob.vercel-storage.com/replays/match-abc.dem"
)


def test_blob_import_is_absent_until_enabled(monkeypatch: Any) -> None:
    monkeypatch.delenv("REDECIDE_BLOB_IMPORT_ENABLED", raising=False)

    from backend.app.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/api/replay/import-url",
        json={"url": PUBLIC_BLOB_URL, "filename": "match.dem"},
    )

    assert response.status_code == 404
    assert "/api/replay/import-url" not in client.get("/openapi.json").json()["paths"]


def test_enabled_blob_import_reuses_normal_replay_flow(
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("REDECIDE_BLOB_IMPORT_ENABLED", "true")
    monkeypatch.setenv("REDECIDE_REPLAY_STORE", str(tmp_path / "replays"))

    import backend.app.blob_import as blob_import

    async def fake_download(_url: str, destination: Any, _limit: int) -> None:
        destination.write_bytes(b"demo bytes")

    def fake_loader(_path: Any) -> dict[str, Any]:
        return {
            "demo_file": "temporary-name.dem",
            "header": {"map_name": "de_mirage", "tick_rate": 64},
            "rounds": [{"round_num": 1, "start": 10, "end": 100}],
            "ticks": [
                {
                    "tick": 10,
                    "steamid": "p1",
                    "player_name": "Player One",
                    "team_name": "CT",
                }
            ],
            "damages": [],
        }

    monkeypatch.setattr(blob_import, "_download_public_blob", fake_download)
    monkeypatch.setattr(blob_import, "_load_native_demo", fake_loader)

    from backend.app.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/api/replay/import-url",
        json={"url": PUBLIC_BLOB_URL, "filename": "original-match.dem"},
    )

    assert response.status_code == 202, response.text
    manifest = response.json()
    assert manifest["source"] == "original-match.dem"
    assert manifest["map"]["name"] == "de_mirage"
    assert manifest["players"][0]["player_id"] == "p1"
    assert (tmp_path / "replays" / manifest["replay_id"] / "coaching.json").is_file()


def test_blob_import_rejects_non_vercel_and_private_urls(monkeypatch: Any) -> None:
    monkeypatch.setenv("REDECIDE_BLOB_IMPORT_ENABLED", "true")

    from backend.app.main import create_app

    client = TestClient(create_app())
    for url in (
        "https://example.com/match.dem",
        "http://store123.public.blob.vercel-storage.com/match.dem",
        "https://store123.private.blob.vercel-storage.com/match.dem",
    ):
        response = client.post(
            "/api/replay/import-url",
            json={"url": url, "filename": "match.dem"},
        )
        assert response.status_code == 422
