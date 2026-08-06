"""Small synchronous adapter around Vercel's official Python Blob SDK.

The adapter is intentionally lazy: importing the backend does not require the
optional ``vercel`` package or Blob credentials.  Callers opt in by setting
``REDECIDE_STORAGE_BACKEND=blob``.  Local development and tests continue to use
the filesystem stores by default.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class BlobStorageConfigurationError(RuntimeError):
    """Raised when Blob mode cannot be initialized in the current runtime."""


class BlobStorageNotFound(FileNotFoundError):
    """Raised when a requested Blob object does not exist."""


@dataclass(frozen=True)
class BlobArtifactRef:
    """Stable metadata returned after uploading an artifact."""

    url: str
    pathname: str


def blob_storage_enabled() -> bool:
    """Return whether the process explicitly opted into Vercel Blob storage."""

    return os.getenv("REDECIDE_STORAGE_BACKEND", "filesystem").strip().lower() == "blob"


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _read_stream(stream: Any) -> bytes:
    """Read the SDK's synchronous stream while rejecting async clients clearly."""

    if stream is None:
        return b""
    if isinstance(stream, (bytes, bytearray, memoryview)):
        return bytes(stream)
    if hasattr(stream, "__aiter__"):
        raise BlobStorageConfigurationError(
            "BlobArtifactStore requires synchronous BlobClient; use BlobClient, "
            "not AsyncBlobClient"
        )
    try:
        return b"".join(bytes(chunk) for chunk in stream)
    except TypeError as exc:
        raise BlobStorageConfigurationError(
            "Vercel Blob SDK returned an unsupported stream type"
        ) from exc


class BlobArtifactStore:
    """JSON artifact persistence using Vercel's official Python SDK.

    The SDK currently requires a Blob read/write token for direct server-side
    operations.  ``BlobClient()`` is used without an explicit token so the SDK
    can resolve its supported runtime authentication (for example
    ``BLOB_READ_WRITE_TOKEN`` or Vercel OIDC).  A token may be supplied through
    ``BLOB_READ_WRITE_TOKEN`` when running outside Vercel.
    """

    def __init__(
        self,
        *,
        prefix: str,
        access: str | None = None,
        client: Any | None = None,
    ) -> None:
        if access is None:
            access = os.getenv("REDECIDE_BLOB_ACCESS", "public")
        if access not in {"public", "private"}:
            raise BlobStorageConfigurationError(
                "REDECIDE_BLOB_ACCESS must be 'public' or 'private'"
            )
        normalized = prefix.strip("/")
        if not normalized:
            raise BlobStorageConfigurationError("Blob artifact prefix cannot be empty")
        self.prefix = normalized
        self.access = access
        self.client = client or self._create_client()

    @staticmethod
    def _create_client() -> Any:
        try:
            from vercel.blob import BlobClient
        except ImportError as exc:  # pragma: no cover - depends on deployment env
            raise BlobStorageConfigurationError(
                "Blob storage is enabled but the 'vercel' package is not installed; "
                "add vercel>=0.5.0 to the backend runtime dependencies"
            ) from exc
        try:
            return BlobClient()
        except Exception as exc:  # pragma: no cover - depends on runtime credentials
            raise BlobStorageConfigurationError(
                "Blob storage is enabled but BlobClient could not initialize; "
                "configure the Vercel Blob connection or BLOB_READ_WRITE_TOKEN"
            ) from exc

    def _key(self, name: str) -> str:
        return f"{self.prefix}/{name.lstrip('/')}"

    def put_json(self, name: str, payload: Mapping[str, Any]) -> BlobArtifactRef:
        body = json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        uploaded = self.client.put(
            self._key(name),
            body,
            access=self.access,
            content_type="application/json; charset=utf-8",
            overwrite=True,
        )
        url = _value(uploaded, "url")
        pathname = _value(uploaded, "pathname", self._key(name))
        if not url or not pathname:
            raise BlobStorageConfigurationError("Vercel Blob put returned incomplete metadata")
        return BlobArtifactRef(url=str(url), pathname=str(pathname))

    def get_json(self, name_or_url: str) -> dict[str, Any]:
        result = self.client.get(name_or_url, access=self.access)
        if result is None or _value(result, "status_code", 200) != 200:
            raise BlobStorageNotFound(f"Blob artifact not found: {name_or_url}")
        payload = json.loads(_read_stream(_value(result, "stream")))
        if not isinstance(payload, dict):
            raise ValueError("Blob JSON artifact must be an object")
        return payload

    def url(self, name_or_url: str) -> str:
        metadata = self.client.head(name_or_url)
        value = _value(metadata, "url")
        if not value:
            raise BlobStorageConfigurationError("Vercel Blob head returned no URL")
        return str(value)


def replay_blob_store() -> BlobArtifactStore:
    return BlobArtifactStore(prefix=os.getenv("REDECIDE_BLOB_REPLAY_PREFIX", "replays"))


def analysis_blob_store() -> BlobArtifactStore:
    return BlobArtifactStore(prefix=os.getenv("REDECIDE_BLOB_ANALYSIS_PREFIX", "analysis"))


__all__ = [
    "BlobArtifactRef",
    "BlobArtifactStore",
    "BlobStorageConfigurationError",
    "BlobStorageNotFound",
    "analysis_blob_store",
    "blob_storage_enabled",
    "replay_blob_store",
]
