"""Unit tests for the opt-in Vercel Blob artifact adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from backend.app import analysis_store
from backend.replay_api import store as replay_store
from backend.storage.blob import BlobArtifactStore, BlobStorageNotFound


@dataclass
class _Blob:
    url: str
    pathname: str


@dataclass
class _GetResult:
    status_code: int
    stream: list[bytes]


class _FakeBlobClient:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, pathname: str, body: bytes, **_: object) -> _Blob:
        self.objects[pathname] = body
        return _Blob(
            url=f"https://example.blob/{pathname}",
            pathname=pathname,
        )

    def get(self, pathname: str, **_: object) -> _GetResult | None:
        body = self.objects.get(pathname)
        if body is None:
            return None
        return _GetResult(status_code=200, stream=[body])

    def head(self, pathname: str) -> _Blob:
        if pathname not in self.objects:
            raise BlobStorageNotFound(pathname)
        return _Blob(
            url=f"https://example.blob/{pathname}",
            pathname=pathname,
        )


def test_blob_store_round_trips_json() -> None:
    client = _FakeBlobClient()
    store = BlobArtifactStore(prefix="replays", client=client)

    ref = store.put_json("abc/manifest.json", {"status": "ready"})

    assert ref.pathname == "replays/abc/manifest.json"
    assert store.get_json("replays/abc/manifest.json") == {"status": "ready"}
    assert store.url("replays/abc/manifest.json") == ref.url


def test_replay_store_dispatches_to_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeBlobClient()
    monkeypatch.setenv("REDECIDE_STORAGE_BACKEND", "blob")
    monkeypatch.setattr(
        replay_store,
        "replay_blob_store",
        lambda: BlobArtifactStore(prefix="replays", client=client),
    )

    replay_id = "0123456789abcdef0123456789abcdef"
    replay_store.save_replay_manifest(replay_id, {"status": "ready"})
    assert replay_store.load_replay_manifest(replay_id) == {"status": "ready"}


def test_analysis_store_dispatches_to_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeBlobClient()
    monkeypatch.setenv("REDECIDE_STORAGE_BACKEND", "blob")
    monkeypatch.setattr(
        analysis_store,
        "analysis_blob_store",
        lambda: BlobArtifactStore(prefix="analysis", client=client),
    )

    analysis_store.save_analysis_state("analysis/one", {"phase": "ready"})
    analysis_store.save_analysis_result("analysis/one", {"score": 4})

    assert analysis_store.load_analysis_state("analysis/one") == {"phase": "ready"}
    assert analysis_store.load_analysis_result("analysis/one") == {"score": 4}


def test_blob_store_rejects_non_object_json() -> None:
    client = _FakeBlobClient()
    client.objects["replays/bad.json"] = json.dumps([1, 2]).encode()
    store = BlobArtifactStore(prefix="replays", client=client)

    with pytest.raises(ValueError, match="must be an object"):
        store.get_json("replays/bad.json")
