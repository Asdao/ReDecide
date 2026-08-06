"""The bundled sample replay source used by the compatibility sample API.

The sample selector historically returned a frozen fixture packet.  The
hosted sample is a real native demo in Vercel Blob, so this module keeps its
transport concerns in one small boundary: download the allowlisted object,
parse it once, persist the replay artifacts, and hand the coaching branch to
``AnalysisService``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi.concurrency import run_in_threadpool

from backend.app.blob_import import (
    BlobFetchError,
    BlobTooLargeError,
    _download_public_blob,
    _max_blob_bytes,
    _validate_public_blob_url,
)
from backend.app.orchestration import AnalysisService
from backend.replay_api.ingestion import load_native_demo, start_replay
from backend.replay_api.store import load_coaching_replay, load_replay_manifest


DEFAULT_SAMPLE_ID = "3dmax-vs-falcons-m2-ancient"
DEFAULT_SAMPLE_URL = (
    "https://nfs2gaifpckeptib.public.blob.vercel-storage.com/"
    "3dmax-vs-falcons-m2-ancient.dem"
)
DEFAULT_SAMPLE_FILENAME = "3dmax-vs-falcons-m2-ancient.dem"
DEFAULT_SAMPLE_BYTES = 321_584_788
DEFAULT_SAMPLE_REPLAY_ID = "59a7b7145da41a0c86f60bb59cb6c033"


class SampleReplayError(RuntimeError):
    """Raised when the hosted sample cannot be prepared."""


BlobDownloader = Callable[[str, Path, int], Awaitable[None]]
ReplayLoader = Callable[[Path], Mapping[str, Any]]


class SampleReplayPreparation(Protocol):
    async def prepare(
        self, *, analysis: AnalysisService, sample_id: str
    ) -> dict[str, Any]: ...


class BlobSampleReplay:
    """Prepare the configured public Blob demo through the real replay flow."""

    def __init__(
        self,
        *,
        url: str | None = None,
        sample_id: str | None = None,
        filename: str | None = None,
        downloader: BlobDownloader | None = None,
        loader: ReplayLoader | None = None,
        max_bytes: int | None = None,
        expected_bytes: int | None = DEFAULT_SAMPLE_BYTES,
        replay_id: str | None = None,
    ) -> None:
        self.sample_id = (
            sample_id or os.getenv("REDECIDE_SAMPLE_ID", DEFAULT_SAMPLE_ID)
        ).strip()
        self.url = (url or os.getenv("REDECIDE_SAMPLE_BLOB_URL", DEFAULT_SAMPLE_URL)).strip()
        self.filename = (
            filename
            or os.getenv("REDECIDE_SAMPLE_FILENAME", DEFAULT_SAMPLE_FILENAME)
        ).strip()
        if not self.sample_id:
            raise ValueError("sample id cannot be empty")
        if not self.filename or Path(self.filename).name != self.filename:
            raise ValueError("sample filename must be a basename")
        if Path(self.filename).suffix.lower() != ".dem":
            raise ValueError("sample filename must end in .dem")
        _validate_public_blob_url(self.url)
        if Path(urlsplit(self.url).path).name != self.filename:
            raise ValueError("sample URL path must match the sample filename")
        self.downloader = downloader or self._download_seed
        self.loader = loader or load_native_demo
        self.max_bytes = max_bytes if max_bytes is not None else _max_blob_bytes()
        if self.max_bytes <= 0:
            raise ValueError("sample max_bytes must be positive")
        if expected_bytes is not None and expected_bytes > self.max_bytes:
            raise ValueError("expected sample size exceeds sample max_bytes")
        self.expected_bytes = expected_bytes
        self.replay_id = replay_id or (
            DEFAULT_SAMPLE_REPLAY_ID
            if self.sample_id == DEFAULT_SAMPLE_ID
            else hashlib.sha256(f"sample:{self.sample_id}".encode("utf-8")).hexdigest()[:32]
        )

    def summary(self) -> dict[str, Any]:
        """Return the stable GET /api/samples shape.

        Player identities are intentionally discovered from the native record
        during selection; the list endpoint must not download and parse a
        multi-hundred-megabyte demo on every page load.
        """

        return {
            "sample_id": self.sample_id,
            "display_name": "3DMAX vs Falcons — Ancient",
            "description": "Ancient match sample prepared from the hosted replay.",
            "map": "de_ancient",
            "players": [],
            "recommended_player": None,
            "available": True,
        }

    async def prepare(
        self, *, analysis: AnalysisService, sample_id: str
    ) -> dict[str, Any]:
        if sample_id != self.sample_id:
            raise SampleReplayError(f"Unknown sample_id: {sample_id}")

        temporary_path = (
            Path(tempfile.gettempdir()) / f"redecide-sample-{uuid4().hex}.dem"
        )
        try:
            cached = await run_in_threadpool(self._load_cached)
            if cached is not None:
                coaching_record, manifest = cached
                return await run_in_threadpool(
                    self._prepare_analysis,
                    coaching_record,
                    manifest,
                    analysis,
                )

            await self.downloader(self.url, temporary_path, self.max_bytes)
            if self.expected_bytes is not None and temporary_path.stat().st_size != self.expected_bytes:
                raise SampleReplayError("hosted sample size did not match the expected seed")
            return await run_in_threadpool(self._prepare_from_path, temporary_path, analysis)
        finally:
            temporary_path.unlink(missing_ok=True)

    async def _download_seed(self, url: str, destination: Path, max_bytes: int) -> None:
        await _download_public_blob(
            url,
            destination,
            max_bytes,
            expected_bytes=self.expected_bytes,
        )

    def _prepare_from_path(
        self, path: Path, analysis: AnalysisService
    ) -> dict[str, Any]:
        try:
            record = self.loader(path)
            if not isinstance(record, Mapping):
                raise TypeError("native demo loader returned a non-object record")
            manifest = start_replay(record, self.filename, replay_id=self.replay_id)
            return self._prepare_analysis(record, manifest, analysis)
        except (BlobFetchError, BlobTooLargeError):
            raise
        except SampleReplayError:
            raise
        except Exception as exc:  # noqa: BLE001 - sanitize parser/provider detail
            raise SampleReplayError("could not prepare the hosted sample replay") from exc

    def _load_cached(self) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Return the deterministic sample artifacts when they are complete."""

        try:
            manifest = load_replay_manifest(self.replay_id)
            coaching = load_coaching_replay(self.replay_id)
        except (FileNotFoundError, ValueError):
            return None
        if manifest.get("visualization_status") != "ready":
            return None
        return coaching, manifest

    def _prepare_analysis(
        self,
        coaching_record: Mapping[str, Any],
        manifest: Mapping[str, Any],
        analysis: AnalysisService,
    ) -> dict[str, Any]:
        replay_id = str(manifest["replay_id"])
        coaching_payload = dict(coaching_record)
        coaching_payload["replay_id"] = replay_id
        analysis_metadata = analysis.prepare(
            coaching_payload,
            source_replay_id=replay_id,
        )
        return {
            "sample_id": self.sample_id,
            "replay_id": replay_id,
            "manifest": dict(manifest),
            "analysis": analysis_metadata,
        }


__all__ = [
    "BlobSampleReplay",
    "DEFAULT_SAMPLE_FILENAME",
    "DEFAULT_SAMPLE_ID",
    "DEFAULT_SAMPLE_URL",
    "DEFAULT_SAMPLE_BYTES",
    "DEFAULT_SAMPLE_REPLAY_ID",
    "SampleReplayError",
    "SampleReplayPreparation",
]
