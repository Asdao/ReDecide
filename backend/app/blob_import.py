"""Disabled-by-default Vercel Blob import transport.

The browser may upload a large demo directly to a public Vercel Blob store and
send its URL here. This module downloads only allowlisted Vercel Blob hosts,
then reuses the existing native-demo parser and replay artifact flow.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
import os
from pathlib import Path
import tempfile
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.replay_api.ingestion import load_native_demo as _load_native_demo
from backend.replay_api.ingestion import start_replay as _start_replay


PUBLIC_BLOB_HOST_SUFFIX = ".public.blob.vercel-storage.com"
DEFAULT_MAX_BLOB_BYTES = 1024 * 1024 * 1024
class BlobFetchError(RuntimeError):
    """Raised when an allowlisted Blob object cannot be downloaded."""


class BlobTooLargeError(BlobFetchError):
    """Raised when a Blob object exceeds the configured hard byte limit."""


class BlobImportRequest(BaseModel):
    """Transport shape for importing one already-uploaded public Blob."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    filename: str = Field(min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_source(self) -> "BlobImportRequest":
        if "/" in self.filename or "\\" in self.filename:
            raise ValueError("filename must not contain a path")
        if Path(self.filename).suffix.lower() != ".dem":
            raise ValueError("filename must end in .dem")
        _validate_public_blob_url(self.url)
        return self


BlobDownloader = Callable[[str, Path, int], Awaitable[None]]
ReplayLoader = Callable[[Path], Mapping[str, Any]]


def blob_import_enabled() -> bool:
    """Return whether the optional public route should be registered."""

    return os.getenv("REDECIDE_BLOB_IMPORT_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def create_blob_import_router(
    *,
    downloader: BlobDownloader | None = None,
    loader: ReplayLoader | None = None,
    executor: object | None = None,
) -> APIRouter:
    """Create the optional router with injectable boundaries for tests.

    ``executor`` remains accepted for compatibility with older callers, but
    is intentionally not used: replay visualization now completes before the
    import request returns.
    """

    router = APIRouter()
    fetch_blob = downloader or _download_public_blob
    load_demo = loader or _load_native_demo

    @router.post("/api/replay/import-url", status_code=202)
    async def import_blob(request: BlobImportRequest) -> dict[str, Any]:
        temporary_path = (
            Path(tempfile.gettempdir()) / f"redecide-blob-{uuid4().hex}.dem"
        )
        try:
            await fetch_blob(request.url, temporary_path, _max_blob_bytes())
            record = await run_in_threadpool(load_demo, temporary_path)
            if not isinstance(record, Mapping):
                raise TypeError("native demo loader returned a non-object record")
            return _start_replay(
                record,
                request.filename,
                executor,
            )
        except BlobTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except BlobFetchError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - keep parser details private
            raise HTTPException(
                status_code=422,
                detail="could not parse the imported demo",
            ) from exc
        finally:
            temporary_path.unlink(missing_ok=True)

    return router


async def _download_public_blob(url: str, destination: Path, max_bytes: int) -> None:
    """Stream one allowlisted public Vercel Blob to a bounded local file."""

    _validate_public_blob_url(url)
    timeout = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            async with client.stream(
                "GET",
                url,
                headers={"Accept-Encoding": "identity"},
            ) as response:
                if response.status_code != 200:
                    raise BlobFetchError("Vercel Blob download failed")
                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        declared_size = int(content_length)
                    except ValueError:
                        declared_size = None
                    if declared_size is not None and declared_size > max_bytes:
                        raise BlobTooLargeError("Vercel Blob exceeds the upload limit")

                received = 0
                with destination.open("wb") as output:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        received += len(chunk)
                        if received > max_bytes:
                            raise BlobTooLargeError(
                                "Vercel Blob exceeds the upload limit"
                            )
                        output.write(chunk)
    except BlobFetchError:
        raise
    except httpx.HTTPError as exc:
        raise BlobFetchError("Vercel Blob could not be reached") from exc


def _validate_public_blob_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid Vercel Blob URL") from exc

    hostname = (parsed.hostname or "").lower().rstrip(".")
    valid_host = (
        hostname.endswith(PUBLIC_BLOB_HOST_SUFFIX)
        and len(hostname) > len(PUBLIC_BLOB_HOST_SUFFIX)
    )
    if (
        parsed.scheme.lower() != "https"
        or not valid_host
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.fragment
    ):
        raise ValueError("url must be a public Vercel Blob HTTPS URL")


def _max_blob_bytes() -> int:
    raw_value = os.getenv(
        "REDECIDE_BLOB_MAX_BYTES",
        str(DEFAULT_MAX_BLOB_BYTES),
    )
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_MAX_BLOB_BYTES
    return value if value > 0 else DEFAULT_MAX_BLOB_BYTES


__all__ = [
    "BlobImportRequest",
    "blob_import_enabled",
    "create_blob_import_router",
]
