"""Transport-independent replay ingestion and artifact generation.

This module owns the shared flow used by HTTP uploads and Blob imports:
loading a native demo record, creating the replay manifest, persisting the
coaching branch, and generating the visualization branch inside the request.
Transport adapters should only validate/download bytes and then call these
functions.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.replay_api.store import (
    save_coaching_artifact,
    save_replay_manifest,
    save_visualization_artifact,
)


def load_native_demo(path: Path) -> Mapping[str, Any]:
    """Load one native demo through the replay engine's public loader."""

    from backend.replay_engine.harness import load_replay_record

    record = load_replay_record(path)
    if not isinstance(record, Mapping):
        raise TypeError("native demo loader returned a non-object record")
    return record


def start_replay(
    record: Mapping[str, Any],
    filename: str,
    executor: object | None = None,
    *,
    replay_id: str | None = None,
) -> dict[str, Any]:
    """Persist a complete replay and return its ready manifest.

    ``executor`` is retained as an ignored compatibility argument for callers
    from the original background-processing implementation.  Vercel Functions
    may be frozen as soon as a response is returned, so visualization must be
    generated within the request before this function returns.
    """

    replay_id = replay_id or uuid4().hex
    manifest = replay_manifest(record, replay_id=replay_id)
    manifest["source"] = filename
    coaching_record = dict(record)
    coaching_record["replay_id"] = replay_id
    save_coaching_artifact(replay_id, coaching_record)
    save_replay_manifest(replay_id, manifest)
    return finish_visualization(record, replay_id, manifest)


def finish_visualization(
    record: Mapping[str, Any], replay_id: str, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    """Generate and persist visualization JSON, recording a safe failure state."""

    try:
        payload = visualization_payload(record, replay_id=replay_id)
        save_visualization_artifact(replay_id, payload)
        completed = {**dict(manifest), "visualization_status": "ready"}
    except Exception:  # noqa: BLE001 - persist a safe status for polling clients
        completed = {
            **dict(manifest),
            "visualization_status": "failed",
            "visualization_error": "visualization JSON generation failed",
        }
    save_replay_manifest(replay_id, completed)
    return completed


def replay_manifest(record: Mapping[str, Any], *, replay_id: str) -> dict[str, Any]:
    """Build the lightweight manifest used by the replay API."""

    header = record.get("header") if isinstance(record.get("header"), Mapping) else {}
    ticks = visualization_ticks(record.get("ticks", []))
    rounds = [
        {
            "round_num": first(row, "round_num"),
            "start": first(row, "start", "start_tick"),
            "end": first(row, "end", "end_tick", "official_end"),
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
            "name": str(
                header.get("map_name") or record.get("map_name") or "unknown"
            ),
            "tick_rate": number(
                header.get("tick_rate") or record.get("tick_rate"), 64.0
            ),
        },
        "players": players_from_ticks(ticks),
        "rounds": rounds,
        "visualization_status": "processing",
        "coaching_status": "ready",
        "visualization_unlocked": False,
    }


def visualization_payload(
    record: Mapping[str, Any], *, replay_id: str | None = None
) -> dict[str, Any]:
    """Build the JSON contract consumed by the 2D replay frontend."""

    header = record.get("header") if isinstance(record.get("header"), Mapping) else {}
    ticks = visualization_ticks(record.get("ticks", []))
    rounds = [row for row in record.get("rounds", []) if isinstance(row, Mapping)]
    return {
        "schema_version": "replay_visualization_v1",
        "replay_id": replay_id
        or str(record.get("replay_id") or record.get("demo_file") or "replay"),
        "source": str(record.get("demo_file") or "replay.dem"),
        "map": {
            "name": str(
                header.get("map_name") or record.get("map_name") or "unknown"
            ),
            "tick_rate": number(
                header.get("tick_rate") or record.get("tick_rate"), 64.0
            ),
        },
        "players": players_from_ticks(ticks),
        "rounds": rounds,
        "events": events_from_record(record),
        "ticks": ticks,
    }


def visualization_ticks(value: Any) -> list[dict[str, Any]]:
    """Return player snapshots with a supported CT/T side only.

    Demo parsers can emit spectator/admin rows with no team assignment. Those
    rows are not renderable by the frontend replay contract, so remove them at
    the artifact boundary and canonicalize supported aliases to ``ct``/``t``.
    """

    ticks: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return ticks
    for row in value:
        if not isinstance(row, Mapping):
            continue
        side = team_side(row)
        if side is None:
            continue
        normalized = dict(row)
        normalized["side"] = side
        ticks.append(normalized)
    return ticks


def team_side(value: Mapping[str, Any]) -> str | None:
    """Normalize parser team aliases to the two playable CS sides."""

    for key in ("side", "team_name", "team"):
        raw = value.get(key)
        if raw is None or not str(raw).strip():
            continue
        side = str(raw).strip().lower().replace("_", "").replace("-", "").replace(" ", "")
        if side in {"ct", "counterterrorist"}:
            return "ct"
        if side in {"t", "terrorist", "terrorists"}:
            return "t"
    return None


def players_from_ticks(ticks: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    players: dict[str, dict[str, Any]] = {}
    for tick in ticks:
        player_id = first(
            tick, "steamid", "steam_id", "player_id", "player_name", "name"
        )
        if player_id in (None, ""):
            continue
        key = str(player_id)
        player = players.setdefault(
            key, {"player_id": key, "display_name": None, "sides": []}
        )
        player["display_name"] = player["display_name"] or first(tick, "player_name", "name")
        side = team_side(tick)
        if side is not None and side not in player["sides"]:
            player["sides"].append(side)
    return sorted(
        players.values(),
        key=lambda item: (str(item.get("display_name") or ""), item["player_id"]),
    )


def events_from_record(record: Mapping[str, Any]) -> list[dict[str, Any]]:
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
    return sorted(
        events,
        key=lambda item: (integer(item.get("tick"), -1), str(item.get("event"))),
    )


def first(value: Mapping[str, Any], *keys: str) -> Any:
    return next((value.get(key) for key in keys if value.get(key) is not None), None)


def number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "events_from_record",
    "finish_visualization",
    "first",
    "integer",
    "load_native_demo",
    "number",
    "players_from_ticks",
    "replay_manifest",
    "start_replay",
    "team_side",
    "visualization_payload",
    "visualization_ticks",
]
