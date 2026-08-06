"""Small synchronous adapter around Vercel Blob artifact storage.

The adapter is intentionally lazy: importing the backend does not require the
optional ``vercel`` package or Blob credentials.  Callers opt in by setting
``REDECIDE_STORAGE_BACKEND=blob``.  Local development and tests continue to use
the filesystem stores by default. Vercel's OIDC-only Blob connection is reached
through a private Next.js service binding that mints narrowly scoped URLs.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse

import httpx


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
    """Return whether durable Blob artifacts can be used by this process.

    Legacy tokens can be used directly by the Python SDK. New OIDC-only Vercel
    connections use the deployment-aware ``REDECIDE_BLOB_SERVICE_URL`` binding.
    Merely requesting Blob mode is not enough: without either credential path,
    local and standalone deployments safely keep their filesystem behavior.
    """

    requested = (
        os.getenv("REDECIDE_STORAGE_BACKEND", "filesystem").strip().lower()
        == "blob"
    )
    if not requested:
        return False
    return _legacy_blob_token() is not None or _blob_service_url() is not None


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


class _ServiceBindingBlobClient:
    """Use a private Vercel service to authorize direct Blob transfers."""

    _CONTENT_TYPE = "application/json"

    def __init__(self, service_url: str, *, http: httpx.Client | None = None) -> None:
        parsed = urlparse(service_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise BlobStorageConfigurationError(
                "REDECIDE_BLOB_SERVICE_URL must be an absolute HTTP(S) URL"
            )
        self.endpoint = f"{service_url.rstrip('/')}/service-internal/blob-artifacts"
        self.http = http or httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))

    @staticmethod
    def _pathname(locator: str) -> str:
        if locator.startswith(("https://", "http://")):
            return unquote(urlparse(locator).path.lstrip("/"))
        return locator.lstrip("/")

    def _ticket(
        self,
        operation: str,
        pathname: str,
        *,
        access: str,
        content_type: str | None = None,
        size: int | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "operation": operation,
            "pathname": pathname,
            "access": access,
        }
        if content_type is not None:
            payload["contentType"] = content_type
        if size is not None:
            payload["size"] = size
        try:
            response = self.http.post(self.endpoint, json=payload)
            response.raise_for_status()
            value = response.json().get("url")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise BlobStorageConfigurationError(
                "The private Blob authorization service could not issue a signed URL"
            ) from exc
        if not isinstance(value, str) or not value.startswith(("https://", "http://")):
            raise BlobStorageConfigurationError(
                "The private Blob authorization service returned an invalid URL"
            )
        return value

    def put(
        self,
        pathname: str,
        body: bytes,
        *,
        access: str,
        content_type: str,
        overwrite: bool,
    ) -> dict[str, str]:
        del overwrite  # The signer fixes overwrite=true for stable artifact keys.
        signed_url = self._ticket(
            "put",
            pathname,
            access=access,
            content_type=self._CONTENT_TYPE,
            size=len(body),
        )
        try:
            response = self.http.put(
                signed_url,
                content=body,
                headers={"Content-Type": self._CONTENT_TYPE},
            )
            response.raise_for_status()
            metadata = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise BlobStorageConfigurationError(
                "The JSON artifact could not be written to Vercel Blob"
            ) from exc
        url = metadata.get("url") if isinstance(metadata, Mapping) else None
        uploaded_pathname = (
            metadata.get("pathname") if isinstance(metadata, Mapping) else None
        )
        if not isinstance(url, str) or not isinstance(uploaded_pathname, str):
            raise BlobStorageConfigurationError(
                "Vercel Blob returned incomplete upload metadata"
            )
        return {"url": url, "pathname": uploaded_pathname}

    def get(self, locator: str, *, access: str) -> dict[str, Any] | None:
        pathname = self._pathname(locator)
        signed_url = self._ticket("get", pathname, access=access)
        try:
            response = self.http.get(signed_url)
        except httpx.HTTPError as exc:
            raise BlobStorageConfigurationError(
                "The JSON artifact could not be read from Vercel Blob"
            ) from exc
        if response.status_code == 404:
            return None
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise BlobStorageConfigurationError(
                "The JSON artifact could not be read from Vercel Blob"
            ) from exc
        return {"status_code": response.status_code, "stream": [response.content]}

    def url(self, locator: str, *, access: str) -> str:
        return self._ticket("get", self._pathname(locator), access=access)


class BlobArtifactStore:
    """JSON artifact persistence using a supported Vercel credential path.

    Legacy tokens use the official Python SDK directly. OIDC-only deployments
    ask the bound Next.js service for single-operation signed URLs, then transfer
    artifact bytes directly between FastAPI and Blob.
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
        legacy_token = _legacy_blob_token()
        if legacy_token is None:
            service_url = _blob_service_url()
            if service_url is not None:
                return _ServiceBindingBlobClient(service_url)
            raise BlobStorageConfigurationError(
                "Blob storage is enabled but neither a legacy Blob token nor the "
                "REDECIDE_BLOB_SERVICE_URL binding is configured"
            )
        try:
            from vercel.blob import BlobClient
        except ImportError as exc:  # pragma: no cover - depends on deployment env
            raise BlobStorageConfigurationError(
                "Blob storage is enabled but the 'vercel' package is not installed; "
                "add vercel>=0.5.0 to the backend runtime dependencies"
            ) from exc
        try:
            return BlobClient(token=legacy_token)
        except Exception as exc:  # pragma: no cover - depends on runtime credentials
            raise BlobStorageConfigurationError(
                "Blob storage is enabled but BlobClient could not initialize; "
                "configure the Vercel Blob connection or BLOB_READ_WRITE_TOKEN"
            ) from exc

    def _key(self, name: str) -> str:
        return f"{self.prefix}/{name.lstrip('/')}"

    def _locator(self, name_or_url: str) -> str:
        """Resolve relative artifact names without double-prefixing URLs or keys."""

        value = name_or_url.strip()
        if value.startswith(("https://", "http://")):
            return value
        if value == self.prefix or value.startswith(f"{self.prefix}/"):
            return value
        return self._key(value)

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
        locator = self._locator(name_or_url)
        result = self.client.get(locator, access=self.access)
        if result is None or _value(result, "status_code", 200) != 200:
            raise BlobStorageNotFound(f"Blob artifact not found: {name_or_url}")
        payload = json.loads(_read_stream(_value(result, "stream")))
        if not isinstance(payload, dict):
            raise ValueError(  # noqa: TRY004 - invalid persisted JSON shape
                "Blob JSON artifact must be an object"
            )
        return payload

    def url(self, name_or_url: str) -> str:
        signed_url = getattr(self.client, "url", None)
        if callable(signed_url):
            return str(signed_url(self._locator(name_or_url), access=self.access))
        metadata = self.client.head(self._locator(name_or_url))
        value = _value(metadata, "url")
        if not value:
            raise BlobStorageConfigurationError("Vercel Blob head returned no URL")
        return str(value)


def replay_blob_store() -> BlobArtifactStore:
    return BlobArtifactStore(prefix=os.getenv("REDECIDE_BLOB_REPLAY_PREFIX", "replays"))


def _legacy_blob_token() -> str | None:
    """Return a configured token understood by the current Python Blob SDK."""

    for name in ("BLOB_READ_WRITE_TOKEN", "VERCEL_BLOB_READ_WRITE_TOKEN"):
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _blob_service_url() -> str | None:
    value = os.getenv("REDECIDE_BLOB_SERVICE_URL")
    if value and value.strip():
        return value.strip()
    return None


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
