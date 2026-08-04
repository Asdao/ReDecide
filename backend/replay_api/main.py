"""FastAPI service that converts one native CS2 demo into one UI JSON file."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Mapping
from uuid import uuid4

from backend.replay_api.store import (
    load_replay_manifest,
    save_coaching_artifact,
    save_replay_manifest,
    save_visualization_artifact,
    visualization_path,
)

try:
    from fastapi import FastAPI, File, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
except ImportError as exc:  # pragma: no cover - dependency boundary
    raise RuntimeError("FastAPI is required to run backend.replay_api.main") from exc


def create_app() -> FastAPI:
    app = FastAPI(title="RE:DECIDE Replay API", version="1.0")
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="replay-json")
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
        """Parse once and return map/player metadata before full JSON generation."""

        filename, record = await _parse_upload(file)
        return _start_replay(record, filename, executor)

    @app.get("/api/replay/{replay_id}/status")
    def replay_status(replay_id: str) -> dict[str, Any]:
        try:
            return load_replay_manifest(replay_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="replay not found") from exc

    @app.get("/api/replay/{replay_id}/json", response_model=None)
    def replay_json(replay_id: str) -> FileResponse | JSONResponse:
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
        return _start_replay(record, filename, executor)

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
    header = record.get("header") if isinstance(record.get("header"), Mapping) else {}
    ticks = [row for row in record.get("ticks", []) if isinstance(row, Mapping)]
    rounds = [
        {
            "round_num": _first(row, "round_num"),
            "start": _first(row, "start", "start_tick"),
            "end": _first(row, "end", "end_tick", "official_end"),
        }
        for row in record.get("rounds", [])
        if isinstance(row, Mapping)
    ]
    source = str(record.get("demo_file") or "replay.dem")
    return {
        "schema_version": "replay_manifest_v1",
        "replay_id": replay_id,
        "source": source,
        "map": {
            "name": str(header.get("map_name") or record.get("map_name") or "unknown"),
            "tick_rate": _number(header.get("tick_rate") or record.get("tick_rate"), 64.0),
        },
        "players": _players_from_ticks(ticks),
        "rounds": rounds,
        "visualization_status": "processing",
        "coaching_status": "ready",
        "visualization_unlocked": False,
    }


def _start_replay(
    record: Mapping[str, Any],
    filename: str,
    executor: ThreadPoolExecutor,
) -> dict[str, Any]:
    replay_id = uuid4().hex
    manifest = _replay_manifest(record, replay_id=replay_id)
    manifest["source"] = filename
    coaching_record = dict(record)
    coaching_record["replay_id"] = replay_id
    save_coaching_artifact(replay_id, coaching_record)
    save_replay_manifest(replay_id, manifest)
    executor.submit(_finish_visualization, record, replay_id, manifest)
    return manifest


def _finish_visualization(record: Mapping[str, Any], replay_id: str, manifest: Mapping[str, Any]) -> None:
    try:
        payload = _visualization_payload(record, replay_id=replay_id)
        save_visualization_artifact(replay_id, payload)
        completed = {**dict(manifest), "visualization_status": "ready"}
    except Exception:  # noqa: BLE001 - persist a safe status for polling clients
        completed = {
            **dict(manifest),
            "visualization_status": "failed",
            "visualization_error": "visualization JSON generation failed",
        }
    save_replay_manifest(replay_id, completed)


def _load_native_demo(path: Path) -> Mapping[str, Any]:
    """Use Blackbox's existing public native-demo loader."""

    from Blackbox.harness import load_replay_record

    record = load_replay_record(path)
    if not isinstance(record, Mapping):
        raise TypeError("native demo loader returned a non-object record")
    return record


def _visualization_payload(record: Mapping[str, Any], *, replay_id: str | None = None) -> dict[str, Any]:
    """Build the single JSON contract consumed by the 2D replay frontend."""

    header = record.get("header") if isinstance(record.get("header"), Mapping) else {}
    ticks = [row for row in record.get("ticks", []) if isinstance(row, Mapping)]
    rounds = [row for row in record.get("rounds", []) if isinstance(row, Mapping)]
    players = _players_from_ticks(ticks)
    events = _events_from_record(record)
    return {
        "schema_version": "replay_visualization_v1",
        "replay_id": replay_id or str(record.get("replay_id") or record.get("demo_file") or "replay"),
        "source": str(record.get("demo_file") or "replay.dem"),
        "map": {
            "name": str(header.get("map_name") or record.get("map_name") or "unknown"),
            "tick_rate": _number(header.get("tick_rate") or record.get("tick_rate"), 64.0),
        },
        "players": players,
        "rounds": rounds,
        "events": events,
        "ticks": ticks,
    }


def _players_from_ticks(ticks: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    players: dict[str, dict[str, Any]] = {}
    for tick in ticks:
        player_id = _first(tick, "steamid", "steam_id", "player_id", "player_name", "name")
        if player_id in (None, ""):
            continue
        key = str(player_id)
        player = players.setdefault(key, {"player_id": key, "display_name": None, "sides": []})
        player["display_name"] = player["display_name"] or _first(tick, "player_name", "name")
        side = _first(tick, "team_name", "team", "side")
        if side not in (None, "") and side not in player["sides"]:
            player["sides"].append(side)
    return sorted(players.values(), key=lambda item: (str(item.get("display_name") or ""), item["player_id"]))


def _events_from_record(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups: list[tuple[str, Any]] = [
        ("kill", record.get("kills", [])),
        ("damage", record.get("damages", [])),
        ("bomb", record.get("bomb", [])),
    ]
    extra = record.get("events")
    if isinstance(extra, Mapping):
        groups.extend((str(name), rows) for name, rows in extra.items())

    events: list[dict[str, Any]] = []
    for group_name, rows in groups:
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            event = dict(row)
            event.setdefault("event", group_name)
            events.append(event)
    return sorted(events, key=lambda item: (_integer(item.get("tick"), -1), str(item.get("event"))))


def _first(value: Mapping[str, Any], *keys: str) -> Any:
    return next((value.get(key) for key in keys if value.get(key) is not None), None)


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


app = create_app()

__all__ = ["app", "create_app"]
