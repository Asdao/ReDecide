"""FastAPI service that converts one native CS2 demo into one UI JSON file."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Any, Mapping
from uuid import uuid4

from backend.replay_api.ingestion import (
    events_from_record as _events_from_record,  # noqa: F401 - compatibility alias
    first as _first,  # noqa: F401 - compatibility alias
    integer as _integer,  # noqa: F401 - compatibility alias
    load_native_demo as _ingest_load_native_demo,
    number as _number,  # noqa: F401 - compatibility alias
    players_from_ticks as _players_from_ticks,  # noqa: F401 - compatibility alias
    start_replay as _ingest_start_replay,
    visualization_payload as _ingest_visualization_payload,
)
from backend.replay_api.store import load_replay_manifest, visualization_path

try:
    from fastapi import FastAPI, File, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
except ImportError as exc:  # pragma: no cover - dependency boundary
    raise RuntimeError("FastAPI is required to run backend.replay_api.main") from exc


def create_app() -> FastAPI:
    app = FastAPI(title="RE:DECIDE Replay API", version="1.0")
    allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "REPLAY_API_ALLOWED_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/replay/upload", status_code=202)
    async def upload(file: UploadFile = File(...)) -> dict[str, Any]:
        """Parse once and return map/player metadata with artifacts ready."""

        filename, record = await _parse_upload(file)
        return _start_replay(record, filename)

    @app.get("/api/replay/{replay_id}/status")
    def replay_status(replay_id: str) -> dict[str, Any]:
        try:
            return load_replay_manifest(replay_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="replay not found") from exc

    @app.get("/api/replay/{replay_id}/json", response_model=None)
    def replay_json(replay_id: str) -> FileResponse | JSONResponse | RedirectResponse:
        try:
            manifest = load_replay_manifest(replay_id)
            path = visualization_path(replay_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="replay not found") from exc
        if not manifest.get("visualization_unlocked", False):
            return JSONResponse(
                status_code=403,
                content={"replay_id": replay_id, "status": "locked_until_coaching_complete"},
            )
        if isinstance(path, str):
            # Blob responses are served directly by Vercel's CDN, avoiding a
            # second Function invocation and the serverless response-size cap.
            source = Path(str(manifest.get("source") or "replay.dem"))
            return RedirectResponse(
                path,
                status_code=307,
                headers={
                    "Content-Disposition": f'attachment; filename="{source.stem}.replay.json"'
                },
            )
        if not path.is_file():
            if manifest.get("visualization_status") == "failed":
                raise HTTPException(status_code=422, detail="visualization JSON generation failed")
            return JSONResponse(
                status_code=202,
                content={"replay_id": replay_id, "status": manifest.get("visualization_status", "processing")},
            )
        source = Path(str(manifest.get("source") or "replay.dem"))
        return FileResponse(
            path,
            media_type="application/json",
            filename=f"{source.stem}.replay.json",
        )

    @app.post("/api/replay/convert", status_code=202)
    async def convert(file: UploadFile = File(...)) -> dict[str, Any]:
        """Compatibility alias for the player-first upload flow."""

        filename, record = await _parse_upload(file)
        return _start_replay(record, filename)

    return app


async def _parse_upload(file: UploadFile) -> tuple[str, Mapping[str, Any]]:
    filename = file.filename or ""
    if Path(filename).suffix.lower() != ".dem":
        raise HTTPException(status_code=415, detail="replay upload must be a .dem file")

    temporary_path = Path(tempfile.gettempdir()) / f"redecide-{uuid4().hex}.dem"
    try:
        with temporary_path.open("wb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                destination.write(chunk)
        from fastapi.concurrency import run_in_threadpool

        return filename, await run_in_threadpool(_load_native_demo, temporary_path)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - keep parser details out of the API
        raise HTTPException(status_code=422, detail="could not parse the uploaded demo") from exc
    finally:
        temporary_path.unlink(missing_ok=True)


def _replay_manifest(record: Mapping[str, Any], *, replay_id: str) -> dict[str, Any]:
    from backend.replay_api.ingestion import replay_manifest

    return replay_manifest(record, replay_id=replay_id)


def _start_replay(
    record: Mapping[str, Any],
    filename: str,
    executor: object | None = None,
) -> dict[str, Any]:
    return _ingest_start_replay(record, filename, executor)


def _finish_visualization(
    record: Mapping[str, Any], replay_id: str, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    from backend.replay_api.ingestion import finish_visualization

    finish_visualization(record, replay_id, manifest)


def _load_native_demo(path: Path) -> Mapping[str, Any]:
    return _ingest_load_native_demo(path)


def _visualization_payload(record: Mapping[str, Any], *, replay_id: str | None = None) -> dict[str, Any]:
    return _ingest_visualization_payload(record, replay_id=replay_id)


app = create_app()

__all__ = ["app", "create_app"]
