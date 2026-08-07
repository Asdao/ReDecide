"""Unit tests for the opt-in Vercel Blob artifact adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
import pytest

from backend.app import analysis_store
from backend.replay_api import store as replay_store
from backend.storage import blob as blob_module
from backend.storage.blob import (
    BlobArtifactStore,
    BlobStorageNotFound,
    _ServiceBindingBlobClient,
    blob_storage_enabled,
)


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
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "legacy-token")
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
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "legacy-token")
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


def test_oidc_only_blob_connection_uses_filesystem_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("VERCEL_BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("BLOB_STORE_ID", "store_123")
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "oidc-token")
    monkeypatch.setenv("REDECIDE_STORAGE_BACKEND", "blob")

    assert blob_storage_enabled() is False


def test_oidc_blob_connection_uses_service_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("VERCEL_BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("BLOB_STORE_ID", "store_123")
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "oidc-token")
    monkeypatch.setenv("REDECIDE_STORAGE_BACKEND", "blob")
    monkeypatch.setenv("REDECIDE_BLOB_SERVICE_URL", "https://frontend.internal")

    assert blob_storage_enabled() is True


def test_local_filesystem_default_ignores_service_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REDECIDE_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("REDECIDE_BLOB_SERVICE_URL", "http://localhost:3000")

    assert blob_storage_enabled() is False


def test_vercel_service_binding_enables_blob_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REDECIDE_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("VERCEL_BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("REDECIDE_BLOB_SERVICE_URL", "https://frontend.internal")

    assert blob_storage_enabled() is True


def test_vercel_can_explicitly_keep_filesystem_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("REDECIDE_BLOB_SERVICE_URL", "https://frontend.internal")
    monkeypatch.setenv("REDECIDE_STORAGE_BACKEND", "filesystem")

    assert blob_storage_enabled() is False


def test_blob_store_selects_service_binding_without_legacy_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[str] = []

    class FakeBindingClient:
        def __init__(self, service_url: str) -> None:
            created.append(service_url)

    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("VERCEL_BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("REDECIDE_BLOB_SERVICE_URL", "https://frontend.internal/")
    monkeypatch.setattr(blob_module, "_ServiceBindingBlobClient", FakeBindingClient)

    store = BlobArtifactStore(prefix="replays")

    assert isinstance(store.client, FakeBindingClient)
    assert created == ["https://frontend.internal/"]


def test_service_binding_transfers_json_directly_to_blob() -> None:
    requests: list[tuple[str, str, bytes]] = []
    pathname = "analysis/job/state.json"
    artifact = b'{"phase":"ready","marker":"artifact-body"}'

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        requests.append((request.method, str(request.url), body))
        if request.url.host == "frontend.internal":
            ticket = json.loads(body)
            return httpx.Response(
                200,
                json={
                    "url": f"https://blob.example/{ticket['operation']}",
                    "expiresAt": 9999999999999,
                },
            )
        if request.method == "PUT":
            return httpx.Response(
                200,
                json={"url": "https://blob.example/object", "pathname": pathname},
            )
        if request.method == "GET":
            return httpx.Response(200, content=artifact)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = _ServiceBindingBlobClient("https://frontend.internal", http=http)

    uploaded = client.put(
        pathname,
        artifact,
        access="private",
        content_type="application/json; charset=utf-8",
        overwrite=True,
    )
    downloaded = client.get(pathname, access="private")
    signed_url = client.url(pathname, access="private")

    assert uploaded == {"url": "https://blob.example/object", "pathname": pathname}
    assert downloaded == {"status_code": 200, "stream": [artifact]}
    assert signed_url == "https://blob.example/get"
    bridge_bodies = [body for _, url, body in requests if "frontend.internal" in url]
    assert bridge_bodies
    assert all(b"artifact-body" not in body for body in bridge_bodies)
    put_requests = [item for item in requests if item[0] == "PUT"]
    assert put_requests == [("PUT", "https://blob.example/put", artifact)]


def test_service_binding_retries_transient_blob_put() -> None:
    pathname = "analysis/job/state.json"
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.host == "frontend.internal":
            return httpx.Response(200, json={"url": "https://blob.example/put"})
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, text="temporarily unavailable")
        return httpx.Response(
            200,
            json={"url": "https://blob.example/object", "pathname": pathname},
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = _ServiceBindingBlobClient(
        "https://frontend.internal",
        http=http,
        sleep=delays.append,
    )

    uploaded = client.put(
        pathname,
        b'{"phase":"ready"}',
        access="public",
        content_type="application/json",
        overwrite=True,
    )

    assert uploaded["pathname"] == pathname
    assert attempts == 2
    assert delays == [0.1]


def test_blob_store_passes_legacy_token_to_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vercel_blob = pytest.importorskip(
        "vercel.blob",
        reason="legacy-token coverage requires the optional Vercel Python SDK",
    )

    captured: dict[str, str | None] = {}

    class FakeClient:
        def __init__(self, token: str | None = None) -> None:
            captured["token"] = token

    monkeypatch.setenv("BLOB_STORE_ID", "store_123")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "legacy-token")
    monkeypatch.setattr(vercel_blob, "BlobClient", FakeClient)

    BlobArtifactStore(prefix="replays")

    assert captured["token"] == "legacy-token"


def test_legacy_token_keeps_blob_enabled_with_connected_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDECIDE_STORAGE_BACKEND", "blob")
    monkeypatch.setenv("BLOB_STORE_ID", "store_123")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "legacy-token")

    assert blob_storage_enabled() is True
