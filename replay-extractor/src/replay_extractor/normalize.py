"""Convert parser-specific JSON records to the stable replay schema."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from .models import EventRecord, PlayerTick, ReplayMetadata, ReplayRecord, RoundRecord


SCHEMA_VERSION = 1


def normalize_record(raw: dict[str, Any], *, source_path: str | None = None) -> ReplayRecord:
    """Normalize one parsed record without mutating the input payload."""

    header = dict(raw.get("header") or {})
    match = dict(raw.get("match") or {})
    source = str(source_path or raw.get("source_path") or raw.get("demo_file") or "unknown")
    demo_file = str(raw.get("demo_file") or Path(source).name)
    parser = str(raw.get("parser") or "unknown")
    map_name = str(header.get("map_name") or match.get("map_name") or "unknown").lower()
    tick_rate = _number(header.get("tick_rate") or match.get("tick_rate"), 128.0)
    checksum = str(raw.get("checksum") or hashlib.sha256(_stable_json(raw).encode()).hexdigest())
    replay_id = str(raw.get("replay_id") or hashlib.sha256(f"{source}:{checksum}".encode()).hexdigest()[:24])
    metadata = ReplayMetadata(replay_id, source, demo_file, parser, map_name, tick_rate, checksum, header)

    rounds = tuple(_rounds(replay_id, raw.get("rounds") or []))
    events = tuple(_events(replay_id, raw))
    player_ticks = tuple(_ticks(replay_id, raw.get("ticks") or []))
    return ReplayRecord(metadata, rounds, events, player_ticks)


def _rounds(replay_id: str, rows: Iterable[dict[str, Any]]) -> Iterable[RoundRecord]:
    for row in rows:
        yield RoundRecord(
            replay_id,
            _integer(row.get("round_num")),
            _optional_integer(row.get("start") or row.get("start_tick")),
            _optional_integer(row.get("end") or row.get("official_end") or row.get("end_tick")),
            _side(row.get("winner")),
            _optional_text(row.get("reason")),
            _optional_integer(row.get("bomb_plant") or row.get("bomb_plant_tick")),
            _optional_text(row.get("bomb_site")),
        )


def _events(replay_id: str, raw: dict[str, Any]) -> Iterable[EventRecord]:
    sources: list[tuple[str, Iterable[dict[str, Any]]]] = [
        ("kill", raw.get("kills") or []),
        ("damage", raw.get("damages") or []),
        ("bomb", raw.get("bomb") or []),
    ]
    for event_type, rows in (raw.get("events") or {}).items():
        sources.append((str(event_type).lower(), rows or []))
    ordinal = 0
    for event_type, rows in sources:
        for row in rows:
            ordinal += 1
            payload = dict(row)
            yield EventRecord(
                replay_id,
                f"{replay_id}:evt:{ordinal}",
                _optional_integer(row.get("round_num")),
                _optional_integer(row.get("tick")),
                event_type,
                _identity(row, "attacker_steamid", "attacker_id"),
                _identity(row, "victim_steamid", "victim_id"),
                _identity(row, "steamid", "player_steamid", "actor_steamid"),
                _side(row.get("attacker_side") or row.get("side") or row.get("team_name")),
                _optional_text(row.get("bombsite") or row.get("site") or row.get("which_bomb_zone")),
                _optional_text(row.get("weapon")),
                payload,
            )


def _ticks(replay_id: str, rows: Iterable[dict[str, Any]]) -> Iterable[PlayerTick]:
    for ordinal, row in enumerate(rows):
        yield PlayerTick(
            replay_id,
            _integer(row.get("round_num")),
            _integer(row.get("tick")),
            _identity(row, "steamid", "steam_id", "player_steamid", "name", "player_name") or f"anonymous:{ordinal}",
            _optional_text(row.get("player_name") or row.get("name")),
            _side(row.get("team_name") or row.get("side")),
            _coordinate(row, "X", "x"),
            _coordinate(row, "Y", "y"),
            _coordinate(row, "Z", "z"),
            _optional_integer(row.get("health")),
            _optional_integer(row.get("armor_value") or row.get("armor")),
            _optional_bool(row.get("alive")),
            _optional_text(row.get("last_place_name") or row.get("zone")),
            dict(row),
        )


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _number(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _integer(value: Any) -> int:
    return int(_number(value, 0.0))


def _optional_integer(value: Any) -> int | None:
    return None if value is None else _integer(value)


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _identity(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _coordinate(row: dict[str, Any], *keys: str) -> float | None:
    value = next((row.get(key) for key in keys if row.get(key) is not None), None)
    return None if value is None else _number(value, 0.0)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() not in {"0", "false", "dead", "none"}


def _side(value: Any) -> str | None:
    text = str(value or "").lower()
    if text in {"ct", "counterterrorist", "counter-terrorist"}:
        return "ct"
    if text in {"t", "terrorist"}:
        return "t"
    return None
